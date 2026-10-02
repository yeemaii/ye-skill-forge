"""对意图、组合、交付和本地进化的关键失败边界做回归。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.evolution import apply_evolution, build_evidence_packet, record_evolution, rollback_evolution
from core.feedback_parser import FeedbackParser
from core.intent import clarify
from core.lifecycle import compile_targets, install_simulate, output_eval, package_skill, tree_sha256, trigger_eval, trust_audit
from core.package import create_package_scaffold, route_eval, validate_package
from core.review import review_skill
from scripts.create import create_package


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def brief():
    return {"name": "source-notes", "root_problem": "整理来源时反复丢失引用", "root_confirmed": True, "recurring_job": "把资料整理为保留引用的笔记", "inputs": ["原始资料"], "outputs": ["引用笔记"], "boundaries": ["不写无来源结论"], "success_signals": ["事实均有引用"], "triggers": ["整理这些资料为引用笔记"], "near_neighbors": ["编写小说故事"]}


class MetaTests(unittest.TestCase):
    def test_linear_stages_do_not_force_a_skill_family(self):
        data = brief()
        data["components"] = ["读取", "整理", "校验"]
        self.assertEqual(clarify(data)["design_pattern"], "workflow-pack")
        data["composition"] = {"children": ["collect", "synthesize"], "router": "router"}
        self.assertEqual(clarify(data)["design_pattern"], "skill-family")

    def test_ready_design_does_not_wait_for_optional_fields(self):
        data = brief()
        result = clarify(data)
        self.assertEqual(result["next_action"], "design")
        self.assertIn("target_user", result["missing"])
        self.assertEqual(result["questions"], [])
        self.assertLessEqual(len(clarify({"idea": "研究助手"}, 99)["questions"]), 2)
        self.assertFalse(clarify({"root_confirmed": True})["root_confirmed"])

    def test_generation_consumes_intent_and_keeps_real_trigger_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "notes"
            create_package(brief(), root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["design"]["root_confirmed"])
            self.assertEqual(manifest["design"]["next_action"], "design")
            cases = json.loads((root / "evals/trigger_cases.json").read_text(encoding="utf-8"))
            self.assertEqual(cases["positive"], brief()["triggers"])
            self.assertEqual(cases["negative"], brief()["near_neighbors"])
            self.assertEqual(manifest["capabilities"], [])
            self.assertEqual(manifest["license"], "")

    def test_cli_refuses_unready_generation_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "notes"
            command = [sys.executable, str(ROOT / "scripts/ye.py"), "create", "Notes", "--slug", "notes", "--job", "整理资料", "--require-ready", "--output-dir", str(target)]
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(json.loads(completed.stdout)["ok"])
            self.assertFalse(target.exists())

    def test_create_ready_gate_matches_raw_intent_without_scaffold_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            data = brief()
            data.pop("boundaries")
            data.pop("success_signals")
            brief_file = Path(temp) / "brief.json"
            write_json(brief_file, data)
            target = Path(temp) / "notes"
            command = [sys.executable, str(ROOT / "scripts/ye.py"), "create", "Notes", "--slug", "notes", "--brief-file", str(brief_file), "--require-ready", "--output-dir", str(target)]
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            result = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(result["intent"]["blocking_missing"], clarify(data)["blocking_missing"])
            self.assertEqual(result["intent"]["next_action"], "clarify")
            self.assertFalse(target.exists())

    def test_package_rejects_escaped_paths_and_malformed_contracts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("family", root, ["alpha", "beta"])
            path = root / "package.json"
            original = json.loads(path.read_text(encoding="utf-8"))
            for changes in ({"router": "../other"}, {"children": [{"name": "external", "path": "../other"}]}, {"shared": ["../private.txt"]}, {"contracts": []}, {"contracts": {"handoff": {"input": "", "output": "result", "state": "context"}}}):
                with self.subTest(changes=changes):
                    write_json(path, {**original, **changes})
                    self.assertFalse(validate_package(root)["ok"])

    def test_route_cases_validate_rejection_conflict_and_sequences(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("family", root, ["alpha", "beta"])
            cases = [{"input": "任务 A", "expected": "alpha"}, {"input": "任务 B", "expected": "beta"}, {"input": "无关任务", "expected": "out-of-scope"}, {"input": "不确定任务", "expected": "clarify"}, {"input": "先 A 再 B", "expected": ["alpha", "beta"]}]
            write_json(root / "evals/route_cases.json", cases)
            result = route_eval(root)
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["counts"]["sequence"], 1)
            self.assertIsNone(result["metrics"]["routing_accuracy"])
            for invalid in ([None], [{"input": "missing target"}], [{"input": "unknown", "expected": "ghost"}], cases + [{"input": "任务 A", "expected": "beta"}]):
                with self.subTest(invalid=invalid):
                    write_json(root / "evals/route_cases.json", invalid)
                    self.assertFalse(route_eval(root)["ok"])

    def test_package_review_and_install_cannot_ignore_router_or_children(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("family", root, ["alpha"])
            write_json(root / "evals/route_cases.json", [{"input": "A", "expected": "alpha"}])
            result = review_skill(root)
            self.assertTrue(result["ok"])
            self.assertIn("children", {gate["key"] for gate in result["gates"]})
            self.assertGreater(result["warnings"], 0)
            (root / "skills/alpha/SKILL.md").unlink()
            self.assertFalse(review_skill(root)["ok"])
            archive = package_skill(root, Path(temp) / "dist")
            self.assertFalse(install_simulate(root, archive["archive"])["ok"])

    def test_compile_preserves_single_skill_resources_and_refuses_stale_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "notes"
            create_package(brief(), root)
            (root / "references").mkdir()
            (root / "references/schema.md").write_text("引用结构", encoding="utf-8")
            output = Path(temp) / "targets"
            compile_targets(root, output, ["generic"])
            self.assertTrue((output / "generic/references/schema.md").is_file())
            with self.assertRaises(FileExistsError):
                compile_targets(root, output, ["generic"])
            with self.assertRaises(ValueError):
                compile_targets(root, root / "custom-build", ["generic"])

    def test_distribution_excludes_private_local_files_and_preserves_templates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "notes"
            create_package(brief(), root)
            excluded = [".env", ".env.local", ".venv/lib/private.txt", ".vscode/settings.json", ".idea/workspace.xml"]
            for name in excluded:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("local state", encoding="utf-8")
            (root / ".env.example").write_text("HOST=localhost\n", encoding="utf-8")
            compile_targets(root, Path(temp) / "targets", ["generic"])
            archive = package_skill(root, Path(temp) / "dist")
            with zipfile.ZipFile(archive["archive"]) as handle:
                entries = handle.namelist()
                self.assertIn(".env.example", entries)
                for name in excluded:
                    self.assertNotIn(name, entries)
                    self.assertFalse((Path(temp) / "targets/generic" / name).exists())

    def test_secret_config_blocks_compilation_and_packaging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "notes"
            create_package(brief(), root)
            write_json(root / "config.json", {"api_key": "fake-secret-for-regression"})
            self.assertFalse(trust_audit(root)["ok"])
            with self.assertRaises(ValueError):
                package_skill(root, Path(temp) / "dist")
            with self.assertRaises(ValueError):
                compile_targets(root, Path(temp) / "targets", ["generic"])

    def test_env_templates_allow_placeholders_and_block_unquoted_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "notes"
            create_package(brief(), root)
            env_file = root / ".env.example"
            env_file.write_text('API_KEY=\nACCESS_TOKEN=${ACCESS_TOKEN}\nDB_PASSWORD="<YOUR_PASSWORD>"\nSECRET=your-secret\n', encoding="utf-8")
            self.assertTrue(trust_audit(root)["ok"])
            self.assertTrue(package_skill(root, Path(temp) / "safe-dist")["ok"])
            for content in ("API_KEY=fake-not-a-real-credential\n", "export ACCESS_TOKEN=another-fake-credential # sample\n", "DB_PASSWORD='not-a-real-password'\n"):
                with self.subTest(content=content):
                    env_file.write_text(content, encoding="utf-8")
                    self.assertFalse(trust_audit(root)["ok"])
                    with self.assertRaises(ValueError):
                        package_skill(root, Path(temp) / "unsafe-dist")
                    with self.assertRaises(ValueError):
                        compile_targets(root, Path(temp) / "unsafe-targets", ["generic"])

    def test_manifest_style_package_install_checks_entire_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("family", root, ["alpha"])
            write_json(root / "evals/route_cases.json", [{"input": "A", "expected": "alpha"}])
            (root / "package.json").rename(root / "manifest.json")
            good = package_skill(root, Path(temp) / "good-dist")
            self.assertTrue(install_simulate(root, good["archive"])["ok"])
            (root / "skills/alpha/SKILL.md").unlink()
            broken = package_skill(root, Path(temp) / "broken-dist")
            self.assertFalse(install_simulate(root, broken["archive"])["ok"])

    def test_invalid_eval_cases_block_review_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "notes"
            create_package(brief(), root)
            trigger_file = root / "evals/trigger_cases.json"
            for value in (123, "not a case list", [None], [" "]):
                with self.subTest(value=value):
                    write_json(trigger_file, {"positive": value, "negative": ["创作小说"]})
                    report = trigger_eval(root)
                    self.assertFalse(report["ok"])
                    self.assertEqual(report["status"], "invalid")
            completed = subprocess.run([sys.executable, str(ROOT / "scripts/ye.py"), "review", str(root)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(json.loads(completed.stdout)["ok"])
            self.assertNotIn("Traceback", completed.stderr)
            output_file = root / "evals/output/cases.jsonl"
            output_file.parent.mkdir()
            for content in ("not JSON\n", '{"input":"材料"}\n'):
                output_file.write_text(content, encoding="utf-8")
                report = output_eval(root)
                self.assertFalse(report["ok"])
                self.assertEqual(report["status"], "invalid")
            output_file.write_text('{"input":"材料","expected":"引用笔记"}\n', encoding="utf-8")
            self.assertTrue(output_eval(root)["ok"])

    def evolution_fixture(self, temp):
        root = Path(temp) / "notes"
        create_package(brief(), root)
        feedback = FeedbackParser().parse("问题：遗漏引用。好的：保留原文事实。")
        packet = record_evolution(root, build_evidence_packet(root, feedback))["path"]
        original = (root / "SKILL.md").read_bytes()
        plan = Path(temp) / "changes.json"
        write_json(plan, {"source_sha256": tree_sha256(root), "changes": [{"path": "SKILL.md", "content": original.decode("utf-8") + "\n核对每项事实的引用。\n"}]})
        preview = apply_evolution(root, packet, plan)
        evidence = Path(temp) / "replay.json"
        write_json(evidence, {"source_sha256": preview["source_sha256"], "candidate_sha256": preview["candidate_sha256"], "judge_mode": "same-context-agent", "cases": [{"kind": kind, "input": "测试请求", "expected": "预期契约", "observed": "回放输出", "passed": True} for kind in ("observed-failure", "near-neighbor", "preserved-success")]})
        return root, packet, plan, evidence, original

    def test_evolution_previews_applies_and_restores_exact_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root, packet, plan, evidence, original = self.evolution_fixture(temp)
            self.assertEqual((root / "SKILL.md").read_bytes(), original)
            result = apply_evolution(root, packet, plan, evidence, apply=True)
            self.assertTrue(result["applied"])
            self.assertEqual(result["deployment_status"], "provisional")
            self.assertEqual(result["judge_mode"], "same-context-agent")
            self.assertNotEqual((root / "SKILL.md").read_bytes(), original)
            rollback_evolution(root, result["rollback_record"])
            self.assertEqual((root / "SKILL.md").read_bytes(), original)

    def test_evolution_rejects_missing_replay_stale_source_and_escaped_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root, packet, plan, _evidence, original = self.evolution_fixture(temp)
            with self.assertRaises(ValueError):
                apply_evolution(root, packet, plan, apply=True)
            data = json.loads(plan.read_text(encoding="utf-8"))
            data["changes"][0]["path"] = "../outside.md"
            write_json(plan, data)
            with self.assertRaises(ValueError):
                apply_evolution(root, packet, plan)
            self.assertEqual((root / "SKILL.md").read_bytes(), original)
            (root / "SKILL.md").write_bytes(original + b"\nnew local edit\n")
            with self.assertRaises(ValueError):
                apply_evolution(root, packet, plan)
            self.assertFalse((Path(temp) / "outside.md").exists())

    def test_rollback_preserves_changes_made_after_application(self):
        with tempfile.TemporaryDirectory() as temp:
            root, packet, plan, evidence, _original = self.evolution_fixture(temp)
            result = apply_evolution(root, packet, plan, evidence, apply=True)
            skill_file = root / "SKILL.md"
            after = skill_file.read_bytes() + b"\nsubsequent edit\n"
            skill_file.write_bytes(after)
            with self.assertRaises(ValueError):
                rollback_evolution(root, result["rollback_record"])
            self.assertEqual(skill_file.read_bytes(), after)

    def test_self_edit_requires_its_explicit_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            data = brief()
            data["name"] = "ye-skill-forge"
            root = Path(temp) / "engine-copy"
            create_package(data, root)
            packet = record_evolution(root, build_evidence_packet(root, FeedbackParser().parse("问题：错误拆分工作流")))["path"]
            plan = Path(temp) / "changes.json"
            write_json(plan, {"source_sha256": tree_sha256(root), "changes": [{"path": "SKILL.md", "content": (root / "SKILL.md").read_text(encoding="utf-8") + "\n同一职责的步骤使用一个入口。\n"}]})
            with self.assertRaisesRegex(ValueError, "allow-self-edit"):
                apply_evolution(root, packet, plan, apply=True)

    def test_strict_library_release_blocks_missing_behavior_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "notes"
            data = brief()
            data.update({"maturity_tier": "library", "author": "Tester", "license": "MIT"})
            create_package(data, root)
            write_json(root / "evals/output/cases.json", {"cases": [{"input": "来源文本", "expected": "引用笔记"}]})
            completed = subprocess.run([sys.executable, str(ROOT / "scripts/ye.py"), "release-check", str(root)], capture_output=True, text=True, encoding="utf-8")
            result = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(result["ok"])
            self.assertTrue(result["strict"])
            self.assertFalse(result["review"]["behavior_verified"])
            self.assertEqual(next(gate for gate in result["review"]["gates"] if gate["key"] == "behavior")["status"], "warn")


if __name__ == "__main__":
    unittest.main()
