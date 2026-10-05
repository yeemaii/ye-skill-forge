import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.generator import generate_frontmatter, generate_interface, generate_manifest, generate_skill, save_skill
from core.lifecycle import compile_targets, install_simulate, package_skill, registry_audit, skill_ir, telemetry_event, trust_audit, trigger_eval


class LifecycleTests(unittest.TestCase):
    def create_skill(self, root, maturity="scaffold"):
        data = {
            "name": "demo-skill",
            "display_name": "示例 skill",
            "job": "把输入材料整理为结构化结果",
            "description": "当用户要整理输入材料时，将材料转为保留来源事实的结构化结果。",
            "template": "standard",
            "workflow_steps": ["读取输入", "按契约输出"],
            "exclusions": ["不执行一次性业务任务"],
            "quality_standards": "- 保留来源事实",
            "author": "测试",
            "maturity_tier": maturity,
            "root_problem": "材料整理反复丢失可核查事实",
            "root_confirmed": True,
            "target_user": "材料整理者",
            "trigger_examples": ["整理材料"],
            "near_neighbors": ["写邮件"],
            "success_signals": ["每项事实可追溯"],
            "license": "MIT",
        }
        target = root / "demo-skill"
        save_skill(generate_frontmatter(data) + generate_skill(data), generate_manifest(data), target, generate_interface(data))
        manifest_path = target / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["maturity_tier"] = maturity
        manifest["owner"] = "测试"
        manifest["review_cadence"] = "quarterly"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        evals = target / "evals"
        evals.mkdir()
        (evals / "trigger_cases.json").write_text(json.dumps({"positive": ["整理材料"], "negative": ["写邮件"], "near_neighbor": ["直接执行"]}, ensure_ascii=False), encoding="utf-8")
        output_dir = evals / "output"
        output_dir.mkdir()
        (output_dir / "cases.jsonl").write_text('{"input": "会议记录", "expected": "结构化纪要"}\n', encoding="utf-8")
        return target

    def test_core_reports_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.create_skill(Path(temp))
            self.assertTrue(skill_ir(root)["contract"]["has_workflow"])
            trigger_report = trigger_eval(root)
            self.assertTrue(trigger_report["ok"])
            self.assertIsNone(trigger_report["metrics"]["trigger_precision"])
            self.assertIn("尚未执行", trigger_report["metrics"]["reason"])
            self.assertTrue(trust_audit(root)["ok"])
            compiled = compile_targets(root, Path(temp) / "targets", ["generic", "openai"])
            self.assertEqual(len(compiled["targets"]), 2)
            packaged = package_skill(root, Path(temp) / "dist", True)
            self.assertTrue(packaged["ok"])
            telemetry_event(root, "script_run", "accepted", command="test")
            repackaged = package_skill(root, Path(temp) / "dist-with-telemetry", True)
            self.assertTrue(repackaged["ok"])
            with zipfile.ZipFile(repackaged["archive"]) as archive:
                self.assertFalse(any(name.startswith(".ye/") for name in archive.namelist()))
            installed = install_simulate(root, Path(temp) / "dist")
            self.assertTrue(installed["ok"], installed)
            self.assertTrue(registry_audit(root)["ok"])

    def test_trust_scan_surfaces_secret_pattern(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.create_skill(Path(temp))
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "bad.py").write_text("API_KEY = '123456789abcdef'\n", encoding="utf-8")
            report = trust_audit(root)
            self.assertFalse(report["ok"])
            self.assertTrue(any(item["code"] == "secret-pattern" for item in report["findings"]))

    def test_release_check_emits_one_json_document(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.create_skill(Path(temp))
            package_dir = Path(temp) / "dist"
            command = [
                sys.executable,
                str(ROOT / "scripts" / "ye.py"),
                "release-check",
                str(root),
                "--package-dir",
                str(package_dir),
            ]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertTrue(result["ok"])
            self.assertEqual(result["review"]["profile"], "distribution")
            self.assertEqual(result["review"]["decision"], "review")
            self.assertFalse(result["review"]["behavior_verified"])


if __name__ == "__main__":
    unittest.main()
