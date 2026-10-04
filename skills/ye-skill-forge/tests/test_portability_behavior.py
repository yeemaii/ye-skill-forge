"""Verify discoverable artifacts and honest evidence without running agents."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.behavior import compare_evidence, summarize_evidence
from core.generator import generate_interface
from core.lifecycle import build_skill_ir, compile_targets, install_simulate, package_manifest, package_skill, record_behavior_evidence, tree_sha256, upgrade_check
from core.package import create_package_scaffold, validate_package
from core.review import review_skill
from core.skill_utils import validate_skill
from scripts.create import create_package


def make_skill(root):
    create_package({
        "name": "source-notes", "job": "Preserve source quotations in notes",
        "description": "Organize research notes while preserving original quotations and citations.",
        "workflow_steps": ["Read sources", "Check citations"],
        "input_description": "Source text", "output_format": "Cited notes",
        "exclusions": ["No unsupported claims"], "quality_standards": "Citations match the source",
        "author": "Tester", "license": "MIT",
    }, root)


def evidence(source_hash, statuses=("passed", "passed")):
    suite = [
        {"id": "normal", "input": "Organize source text", "expected": "Cited notes"},
        {"id": "missing", "input": "Organize absent text", "expected": "Ask for text"},
    ]
    return {
        "schema_version": "2", "source_sha256": source_hash,
        "judge_mode": "human-review", "environment": {"client": "test-client", "model": "test-model"},
        "suite": suite,
        "cases": [{**case, "status": status, **({"reason": "Client unavailable"} if status == "not-run" else {"observed": "Actual output"})} for case, status in zip(suite, statuses)],
    }


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


class PortabilityBehaviorTests(unittest.TestCase):
    def test_npm_package_json_does_not_turn_single_skill_into_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            make_skill(root)
            (root / "package.json").write_text(json.dumps({"name": "source-notes", "dependencies": {"example": "1.0.0"}}), encoding="utf-8")
            result = compile_targets(root, Path(temp) / "build", ["generic"])
            self.assertEqual(result["targets"][0]["children"], [])
            self.assertEqual(result["targets"][0]["entry_name"], "source-notes")
            self.assertEqual(package_manifest(root)["created_by"], "ye-skill-forge")
            self.assertTrue(review_skill(root)["ok"])
            archive = package_skill(root, Path(temp) / "archives")
            self.assertTrue(install_simulate(root, archive["archive"])["ok"])

    def test_existing_package_entry_uses_root_ui_and_router_native_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("research-workbench", root, ["collect"])
            (root / "SKILL.md").write_text("---\nname: research-workbench\ndescription: Package entry for research workbench tasks.\n---\n# Entry\n\n## Workflow\nRead router.\n", encoding="utf-8")
            (root / "agents").mkdir()
            (root / "agents/interface.yaml").write_text(yaml.safe_dump({"interface": {"display_name": "Root entry", "short_description": "Root package entry for research workbench", "default_prompt": "Use $research-workbench to route this request."}}), encoding="utf-8")
            (root / "router/assets").mkdir(parents=True)
            (root / "router/agents").mkdir(parents=True)
            (root / "router/assets/icon.png").write_bytes(b"icon")
            (root / "router/agents/interface.yaml").write_text(yaml.safe_dump(generate_interface({"name": "research-workbench-router", "shell": "powershell"})), encoding="utf-8")
            (root / "router/agents/openai.yaml").write_text(yaml.safe_dump({"interface": {"display_name": "Router", "icon_small": "assets/icon.png"}, "policy": {"allow_implicit_invocation": False}, "dependencies": {"tools": ["router-tool"]}}), encoding="utf-8")
            self.assertTrue(validate_package(root)["ok"])
            result = compile_targets(root, Path(temp) / "build", ["codex"])
            self.assertEqual(result["targets"][0]["execution"]["shell"], "powershell")
            target = Path(temp) / "build/codex"
            native = yaml.safe_load((target / "agents/openai.yaml").read_text(encoding="utf-8"))
            self.assertEqual(native["interface"]["display_name"], "Root entry")
            self.assertEqual(native["interface"]["default_prompt"], "Use $research-workbench to route this request.")
            self.assertEqual(native["policy"]["allow_implicit_invocation"], False)
            self.assertEqual(native["dependencies"]["tools"], ["router-tool"])
            self.assertEqual(native["interface"]["icon_small"], "router/assets/icon.png")
            self.assertTrue((target / "router/assets/icon.png").is_file())

            (root / "agents/interface.yaml").unlink()
            (root / "router/agents/interface.yaml").write_text(yaml.safe_dump({"interface": {"display_name": "Router fallback", "short_description": "Route research requests using the family", "default_prompt": "Use $research-workbench-router", "icon_small": "assets/icon.png"}}), encoding="utf-8")
            compile_targets(root, Path(temp) / "fallback", ["codex"])
            native = yaml.safe_load((Path(temp) / "fallback/codex/agents/openai.yaml").read_text(encoding="utf-8"))
            self.assertEqual(native["interface"]["icon_small"], "router/assets/icon.png")
            self.assertFalse(native["policy"]["allow_implicit_invocation"])

            root_native = root / "agents/openai.yaml"
            original = b'interface:\n  display_name: "Custom native"\npolicy:\n  allow_implicit_invocation: true\n'
            root_native.write_bytes(original)
            compile_targets(root, Path(temp) / "root-native", ["codex"])
            self.assertEqual((Path(temp) / "root-native/codex/agents/openai.yaml").read_bytes(), original)

    def test_unconsumed_native_metadata_is_preserved_without_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            make_skill(root)
            native = root / "agents/openai.yaml"
            original = b"interface: [invalid-yaml\n"
            native.write_bytes(original)
            compile_targets(root, Path(temp) / "build", ["codex", "claude-code", "generic"])
            for platform in ("codex", "claude-code", "generic"):
                self.assertEqual((Path(temp) / "build" / platform / "agents/openai.yaml").read_bytes(), original)

    def test_thin_entry_inherits_router_native_policy_dependencies_and_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("research-workbench", root, ["collect"])
            (root / "router/agents").mkdir()
            (root / "router/assets").mkdir()
            (root / "router/assets/icon.png").write_bytes(b"icon")
            config = {"interface": {"display_name": "Router", "short_description": "Route research requests using the family", "default_prompt": "Use $research-workbench-router", "icon_small": "./assets/icon.png"}, "policy": {"allow_implicit_invocation": False}, "dependencies": {"tools": [{"type": "mcp", "value": "test-tool"}]}}
            file = root / "router/agents/openai.yaml"
            file.write_text(yaml.safe_dump(config), encoding="utf-8")
            original = file.read_bytes()
            compile_targets(root, Path(temp) / "build", ["codex"])
            target = Path(temp) / "build/codex"
            native = yaml.safe_load((target / "agents/openai.yaml").read_text(encoding="utf-8"))
            self.assertEqual(native["policy"], config["policy"])
            self.assertEqual(native["dependencies"], config["dependencies"])
            self.assertEqual(native["interface"]["icon_small"], "router/assets/icon.png")
            self.assertEqual(native["interface"]["default_prompt"], "Use $research-workbench to complete the requested task.")
            self.assertEqual((target / "router/agents/openai.yaml").read_bytes(), original)

    def test_invalid_or_mismatched_package_root_blocks_review_and_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("research-workbench", root, ["collect"])
            save(root / "evals/route_cases.json", [{"input": "Collect sources", "expected": "collect"}, {"input": "Unrelated request", "expected": "out-of-scope"}, {"input": "Ambiguous request", "expected": "clarify"}])
            self.assertTrue(validate_package(root)["ok"])
            for text in ("# No frontmatter\n", "---\nname: different-name\ndescription: Read the research Router to complete requests.\n---\n# Entry\nRead Router.\n"):
                with self.subTest(text=text):
                    (root / "SKILL.md").write_text(text, encoding="utf-8")
                    self.assertFalse(validate_package(root)["ok"])
                    self.assertFalse(review_skill(root)["ok"])
                    archive = package_skill(root, Path(temp) / "archives")
                    self.assertFalse(install_simulate(root, archive["archive"])["ok"])

    def test_manifest_family_can_include_unrelated_npm_package_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("research-workbench", root, ["collect"])
            (root / "package.json").rename(root / "manifest.json")
            router = root / "router/SKILL.md"
            router.write_text(router.read_text(encoding="utf-8").replace("../package.json", "../manifest.json"), encoding="utf-8")
            save(root / "package.json", {"name": "script-dependencies", "dependencies": {}})
            save(root / "evals/route_cases.json", [{"input": "Collect sources", "expected": "collect"}, {"input": "Unrelated request", "expected": "out-of-scope"}, {"input": "Ambiguous request", "expected": "clarify"}])
            self.assertTrue(validate_package(root)["ok"])
            self.assertEqual(package_manifest(root)["name"], "research-workbench")
            compile_targets(root, Path(temp) / "build", ["generic"])
            target = Path(temp) / "build/generic"
            self.assertTrue(validate_package(target)["ok"])
            archive = package_skill(target, Path(temp) / "archives")
            self.assertTrue(install_simulate(target, archive["archive"])["ok"])

    def test_ye_distribution_includes_license_without_licensing_user_skills(self):
        with tempfile.TemporaryDirectory() as temp:
            source_license_existed = (ROOT / "LICENSE").exists()
            source_license = (ROOT.parents[1] / "LICENSE").read_bytes()
            compile_targets(ROOT, Path(temp) / "engine", ["generic"])
            self.assertEqual((Path(temp) / "engine/generic/LICENSE").read_bytes(), source_license)
            archive = package_skill(ROOT, Path(temp) / "engine-archives")
            with zipfile.ZipFile(archive["archive"]) as handle:
                self.assertEqual(handle.read("LICENSE"), source_license)
            self.assertEqual((ROOT / "LICENSE").exists(), source_license_existed)
            user = Path(temp) / "user"
            make_skill(user)
            compile_targets(user, Path(temp) / "user-build", ["generic"])
            self.assertFalse((Path(temp) / "user-build/generic/LICENSE").exists())

    def test_upgrade_check_normalizes_legacy_platform_aliases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skill"
            root.mkdir()
            (root / "manifest.json").write_text(json.dumps({"name": "skill", "version": "2.2.0", "owner": "Ye", "license": "MIT", "review_cadence": "quarterly", "target_platforms": ["codex", "claude-code", "generic"]}), encoding="utf-8")
            previous = Path(temp) / "previous.json"
            previous.write_text(json.dumps({"version": "2.1.0", "target_platforms": ["openai", "claude", "generic", "agent-skills-compatible", "vscode"]}), encoding="utf-8")
            result = upgrade_check(root, previous)
            self.assertTrue(result["ok"])
            self.assertEqual(result["recommended"], "patch-or-minor")
            current = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            current["target_platforms"].remove("codex")
            save(root / "manifest.json", current)
            self.assertFalse(upgrade_check(root, previous)["ok"])

    def test_adapters_preserve_resources_and_native_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            make_skill(root)
            (root / "references").mkdir()
            (root / "references/source.md").write_text("Quoted source", encoding="utf-8")
            config = {"interface": {"display_name": "Existing"}, "policy": {"allow_implicit_invocation": False}, "dependencies": {"tools": []}}
            native = root / "agents/openai.yaml"
            native.write_text(yaml.safe_dump(config), encoding="utf-8")
            original = native.read_bytes()
            original_source = (root / "SKILL.md").read_bytes()
            result = compile_targets(root, Path(temp) / "build", ["codex", "claude-code", "generic"])
            for adapter in result["targets"]:
                target = Path(temp) / "build" / adapter["target"]
                self.assertEqual((target / "SKILL.md").read_bytes(), original_source)
                self.assertEqual((target / "agents/openai.yaml").read_bytes(), original)
                self.assertTrue((target / "references/source.md").is_file())
                self.assertFalse(adapter["runtime_behavior_verified"])
                self.assertFalse(adapter["execution"]["scheduler_included"])
                self.assertEqual(adapter["execution"]["shell"], "environment")

    def test_codex_generates_ui_metadata_without_opt_out(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            make_skill(root)
            result = compile_targets(root, Path(temp) / "build", ["codex", "openai"])
            for target in ("codex", "openai"):
                config = yaml.safe_load((Path(temp) / "build" / target / "agents/openai.yaml").read_text(encoding="utf-8"))
                self.assertIn("$source-notes", config["interface"]["default_prompt"])
                self.assertNotIn("policy", config)
                self.assertNotIn("compatibility", config)
            self.assertEqual(result["targets"][1]["platform"], "codex")
            self.assertFalse((root / "agents/openai.yaml").exists())

    def test_family_has_root_entry_and_all_relative_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "family"
            create_package_scaffold("research-workbench", root, ["collect", "synthesize"])
            (root / "shared").mkdir()
            (root / "shared/schema.md").write_text("Shared schema", encoding="utf-8")
            (root / "router/agents").mkdir()
            (root / "router/agents/interface.yaml").write_text(yaml.safe_dump({"interface": {"display_name": "Research", "short_description": "Route research tasks to reusable methods", "default_prompt": "Use $research-workbench-router"}}), encoding="utf-8")
            result = compile_targets(root, Path(temp) / "build", ["codex", "claude-code", "generic"])
            for adapter in result["targets"]:
                target = Path(temp) / "build" / adapter["target"]
                self.assertTrue(validate_package(target)["ok"])
                self.assertFalse(any(item["severity"] == "error" for item in validate_skill(target)))
                text = (target / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("router/SKILL.md", text)
                self.assertTrue((target / "skills/collect/SKILL.md").is_file())
                self.assertTrue((target / "shared/schema.md").is_file())
                self.assertFalse(adapter["child_discovery_required"])
                self.assertEqual(adapter["entry_name"], "research-workbench")
                if adapter["platform"] == "codex":
                    interface = yaml.safe_load((target / "agents/openai.yaml").read_text(encoding="utf-8"))["interface"]
                    self.assertEqual(interface["default_prompt"], "Use $research-workbench to complete the requested task.")
            self.assertFalse((root / "SKILL.md").exists())

    def test_interface_is_not_bound_to_powershell(self):
        self.assertEqual(generate_interface({"name": "notes"})["compatibility"]["execution"]["shell"], "environment")
        self.assertEqual(generate_interface({"name": "notes", "shell": "bash"})["compatibility"]["execution"]["shell"], "bash")

    def test_adapter_reports_existing_shell_requirement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            make_skill(root)
            file = root / "agents/interface.yaml"
            config = yaml.safe_load(file.read_text(encoding="utf-8"))
            config["compatibility"]["execution"]["shell"] = "powershell"
            file.write_text(yaml.safe_dump(config), encoding="utf-8")
            original = file.read_bytes()
            result = compile_targets(root, Path(temp) / "build", ["generic"])
            self.assertEqual(result["targets"][0]["execution"]["shell"], "powershell")
            self.assertEqual((Path(temp) / "build/generic/agents/interface.yaml").read_bytes(), original)

    def test_repository_examples_compile_package_and_install(self):
        with tempfile.TemporaryDirectory() as temp:
            for example in ("note-cleanup", "research-package"):
                root = Path(temp) / example
                shutil.copytree(ROOT / "examples" / example, root)
                output = Path(temp) / (example + "-targets")
                compile_targets(root, output, ["codex", "claude-code", "generic"])
                for platform in ("codex", "claude-code", "generic"):
                    target = output / platform
                    archive = package_skill(target, Path(temp) / (example + "-" + platform))
                    self.assertTrue(install_simulate(target, archive["archive"])["ok"])
                    if example == "research-package":
                        self.assertTrue((target / "shared/evidence-schema.md").is_file())
                        self.assertTrue((target / "skills/evidence-synthesis/SKILL.md").is_file())
                        ir = build_skill_ir(target)
                        self.assertEqual(ir["contract"]["child_count"], 2)
                        self.assertTrue(ir["contract"]["has_router"])
                        self.assertEqual(ir["source"], "SKILL.md")

    def test_failed_record_is_stored_and_blocks_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            make_skill(root)
            record = evidence(tree_sha256(root), ("passed", "failed"))
            file = Path(temp) / "run.json"
            save(file, record)
            result = record_behavior_evidence(root, file)
            self.assertTrue(result["ok"])
            self.assertFalse(result["behavior_verified"])
            self.assertEqual(result["counts"]["failed"], 1)
            self.assertEqual(result["pass_rate"], 0.5)
            stored = json.loads((root / "reports/behavior_evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["cases"], record["cases"])
            review = review_skill(root)
            self.assertFalse(review["ok"])
            self.assertEqual(next(item for item in review["gates"] if item["key"] == "behavior")["status"], "block")

    def test_not_run_is_not_a_failure_or_success(self):
        result = summarize_evidence(evidence("a" * 64, ("passed", "not-run")))
        self.assertTrue(result["ok"])
        self.assertFalse(result["behavior_verified"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["pass_rate"], 1)
        self.assertEqual(result["completion_rate"], 0.5)
        self.assertEqual(result["counts"]["executed"], 1)

    def test_denominator_cannot_drop_or_duplicate_cases(self):
        record = evidence("a" * 64)
        record["cases"].pop()
        self.assertFalse(summarize_evidence(record)["ok"])
        record = evidence("a" * 64)
        record["cases"].append(record["cases"][0])
        self.assertFalse(summarize_evidence(record)["ok"])
        record = evidence("a" * 64)
        record["cases"][0]["expected"] = "Easier condition"
        self.assertFalse(summarize_evidence(record)["ok"])

    def test_comparison_reports_regression_despite_equal_pass_rates(self):
        baseline = evidence("a" * 64, ("passed", "failed"))
        candidate = evidence("b" * 64, ("failed", "passed"))
        result = compare_evidence(baseline, candidate)
        self.assertTrue(result["ok"])
        self.assertEqual(result["fixed"], ["missing"])
        self.assertEqual(result["regressed"], ["normal"])
        legacy_flags = evidence("c" * 64)
        for case in legacy_flags["cases"]:
            case["status"] = None
            case["passed"] = True
        self.assertEqual(compare_evidence(baseline, legacy_flags)["fixed"], ["missing"])
        candidate["environment"]["model"] = "another-model"
        self.assertFalse(compare_evidence(baseline, candidate)["ok"])
        self.assertFalse(compare_evidence(baseline, evidence("b" * 64, ("passed", "not-run")))["ok"])

    def test_cli_comparison_is_read_only_and_does_not_schedule(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "baseline.json"
            candidate = Path(temp) / "candidate.json"
            save(baseline, evidence("a" * 64, ("failed", "passed")))
            save(candidate, evidence("b" * 64))
            command = [sys.executable, "-B", str(ROOT / "scripts/ye.py"), "behavior-compare", "--baseline-file", str(baseline), "--candidate-file", str(candidate)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["fixed"], ["normal"])
            self.assertEqual(sorted(item.name for item in Path(temp).iterdir()), ["baseline.json", "candidate.json"])

    def test_malformed_records_return_findings(self):
        for key in ("schema_version", "judge_mode"):
            record = evidence("a" * 64)
            record[key] = []
            self.assertFalse(summarize_evidence(record)["ok"])
        record = evidence("a" * 64)
        record["cases"][0]["status"] = {}
        self.assertFalse(summarize_evidence(record)["ok"])


if __name__ == "__main__":
    unittest.main()
