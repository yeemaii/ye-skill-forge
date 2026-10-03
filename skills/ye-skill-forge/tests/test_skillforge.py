import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.feedback_parser import FeedbackParser
from core.intent import clarify
from core.package import create_package_scaffold, handoff_check, route_eval, validate_package
from core.evolution import build_evidence_packet, record_evolution, evolution_summary
from core.generator import generate_frontmatter, generate_interface, generate_manifest, generate_skill, save_skill
from core.skill_utils import load_skill, validate_skill
from scripts.create import create_package
from scripts.evaluate import evaluate_skill
from scripts.improve import build_proposals, render_report, write_report


def sample_data():
    return {
        "name": "note-cleanup",
        "display_name": "Note Cleanup",
        "author": "A: Ye",
        "job": "Turn rough meeting notes into a recap",
        "description": 'Organize notes and preserve decisions, including values such as "unknown".',
        "template": "standard",
        "input_description": "Meeting notes or transcript",
        "output_format": "Markdown sections",
        "workflow_steps": ["Read all notes", "Extract decisions", "Check every claim against source"],
        "exclusions": ["Do not invent owners or dates"],
        "quality_standards": "- Preserve source facts",
    }


def create_sample(root, with_cases=False):
    data = sample_data()
    body = generate_skill(data, data["template"])
    content = generate_frontmatter(data) + body
    target = root / data["name"]
    save_skill(content, generate_manifest(data), target, generate_interface(data))
    if with_cases:
        cases = target / "evals"
        cases.mkdir()
        (cases / "trigger_cases.json").write_text('{"positive": ["organize notes"], "negative": ["write an email"]}', encoding="utf-8")
    return target


class SkillForgeTests(unittest.TestCase):
    def test_intent_keeps_root_unconfirmed_and_limits_questions(self):
        result = clarify({"idea": "做一个研究资料 skill"})
        self.assertEqual(result["next_action"], "clarify")
        self.assertEqual(result["questions"][0]["field"], "root_problem")
        self.assertLessEqual(len(result["questions"]), 2)

    def test_intent_selects_skill_family_for_composition(self):
        result = clarify({
            "root_problem": "减少研究流程中的返工",
            "root_confirmed": True,
            "target_user": "研究员",
            "job": "处理资料",
            "inputs": ["资料"],
            "outputs": ["证据表"],
            "boundaries": ["不替用户下结论"],
            "success_signals": ["每条结论可追溯"],
            "components": ["检索", "综合"],
            "composition": {"router": "router"},
        })
        self.assertEqual(result["design_pattern"], "skill-family")

    def test_skill_package_checks_router_children_and_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "research-pack"
            router = root / "router"
            child = root / "skills" / "research-notes"
            router.mkdir(parents=True)
            child.mkdir(parents=True)
            router.joinpath("SKILL.md").write_text("---\nname: research-router\ndescription: Route research tasks.\n---\n# Router\n\n## Workflow\nRoute only.\n", encoding="utf-8")
            create_sample(root / "seed")
            source = root / "seed" / "note-cleanup"
            for path in source.iterdir():
                if path.is_file():
                    child.joinpath(path.name).write_bytes(path.read_bytes())
            manifest = {
                "package_type": "skill-family",
                "name": "research-pack",
                "router": "router",
                "children": [{"name": "note-cleanup", "path": "skills/research-notes"}],
                "shared": [],
                "contracts": {"handoff": {"input": "request", "output": "result", "state": "context"}},
                "routing": {"rules": [{"target": "note-cleanup", "when": "整理研究笔记"}]},
            }
            root.joinpath("package.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            root.joinpath("evals").mkdir()
            root.joinpath("evals/route_cases.json").write_text(json.dumps([{"input": "整理研究笔记", "expected": "note-cleanup"}], ensure_ascii=False), encoding="utf-8")
            self.assertTrue(validate_package(root)["ok"])
            self.assertTrue(route_eval(root)["ok"])
            self.assertTrue(handoff_check(root)["ok"])

    def test_package_scaffold_is_atomic_and_structurally_checkable(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "demo-family"
            created = create_package_scaffold("demo-family", target, ["alpha", "beta"])
            self.assertTrue(created["ok"])
            self.assertTrue(validate_package(target)["ok"])
            with self.assertRaises(FileExistsError):
                create_package_scaffold("demo-family", target, ["alpha"])

    def test_evolution_records_proposal_without_editing_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = create_sample(Path(temp))
            before = (root / "SKILL.md").read_text(encoding="utf-8")
            feedback = FeedbackParser().parse("问题：输出太啰嗦")
            packet = build_evidence_packet(root, feedback, [{"type": "output_too_verbose"}])
            recorded = record_evolution(root, packet)
            self.assertTrue(recorded["ok"])
            self.assertEqual(packet["deployment_status"], "provisional")
            self.assertIn("nearest_assets", packet)
            self.assertIn(packet["asset_action"], {"create", "merge", "discard"})
            self.assertEqual((root / "SKILL.md").read_text(encoding="utf-8"), before)
            self.assertEqual(evolution_summary(root)["records"], 1)

    def test_generated_frontmatter_is_valid_yaml_with_quoted_values(self):
        data = sample_data()
        parsed = yaml.safe_load(generate_frontmatter(data).split("---", 2)[1])
        self.assertEqual(parsed["name"], data["name"])
        self.assertEqual(parsed["description"], data["description"])
        self.assertEqual(parsed["metadata"]["author"], data["author"])

    def test_manifest_maps_compact_input_output_fields(self):
        manifest = generate_manifest(sample_data())
        self.assertEqual(manifest["design"]["inputs"], ["Meeting notes or transcript"])
        self.assertEqual(manifest["design"]["outputs"], ["Markdown sections"])

    def test_each_template_resolves_placeholders(self):
        data = sample_data()
        for template in ("minimal", "standard", "advanced"):
            with self.subTest(template=template):
                rendered = generate_skill(data, template)
                self.assertNotIn("{skill_name}", rendered)
                self.assertNotIn("{quality_standards}", rendered)
                self.assertIn("## Workflow", rendered)

    def test_save_creates_manifest_and_interface(self):
        with tempfile.TemporaryDirectory() as temp:
            target = create_sample(Path(temp))
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertEqual(json.loads((target / "manifest.json").read_text(encoding="utf-8"))["name"], "note-cleanup")
            interface = yaml.safe_load((target / "agents" / "interface.yaml").read_text(encoding="utf-8"))
            self.assertEqual(interface["interface"]["display_name"], "Note Cleanup")

    def test_save_refuses_to_overwrite_existing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "existing"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                save_skill("new", {}, target)
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_create_package_produces_a_valid_skill(self):
        data = sample_data()
        with tempfile.TemporaryDirectory() as temp:
            paths, findings = create_package(data, Path(temp) / data["name"])
            self.assertTrue(Path(paths[0]).is_file())
            self.assertFalse([item for item in findings if item["severity"] == "error"], findings)

    def test_generated_scaffold_is_marked_until_domain_method_is_filled(self):
        with tempfile.TemporaryDirectory() as temp:
            findings = create_package(sample_data(), Path(temp) / "sample")[1]
            self.assertTrue(any(item["code"] == "scaffold-content" and item["severity"] == "warning" for item in findings), findings)

    def test_create_package_refuses_to_write_into_its_source(self):
        target = ROOT / "tests" / "must-not-be-created"
        with self.assertRaises(ValueError):
            create_package(sample_data(), target)
        self.assertFalse(target.exists())

    def test_advanced_template_requires_real_architecture_and_roles(self):
        data = sample_data()
        data["template"] = "advanced"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                create_package(data, Path(temp) / data["name"])

    def test_validator_accepts_generated_package(self):
        with tempfile.TemporaryDirectory() as temp:
            target = create_sample(Path(temp))
            findings = validate_skill(target)
            self.assertFalse([item for item in findings if item["severity"] == "error"], findings)
            self.assertEqual(load_skill(target)[2]["name"], "note-cleanup")

    def test_validator_rejects_invalid_declared_compatibility_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp:
            target = create_sample(Path(temp))
            interface_path = target / "agents" / "interface.yaml"
            interface = yaml.safe_load(interface_path.read_text(encoding="utf-8"))
            interface["compatibility"]["execution"]["shell"] = "cmd"
            interface_path.write_text(yaml.safe_dump(interface, sort_keys=False), encoding="utf-8")
            findings = validate_skill(target)
            self.assertTrue(any(item["code"] == "compatibility-shell" for item in findings), findings)

    def test_validator_reports_malformed_frontmatter(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / "SKILL.md").write_text("# Missing frontmatter\n", encoding="utf-8")
            findings = validate_skill(target)
            self.assertTrue(any(item["code"] == "skill-file" for item in findings))

    def test_static_evaluator_does_not_claim_behavioral_accuracy(self):
        with tempfile.TemporaryDirectory() as temp:
            target = create_sample(Path(temp), with_cases=True)
            report = evaluate_skill(target)
            case_check = next(item for item in report["checklist"] if item["area"] == "evaluation-cases")
            self.assertEqual(case_check["status"], "present")
            self.assertIn("execution was not checked", case_check["evidence"])
            self.assertIn("does not measure semantic trigger accuracy", report["limitations"])

    def test_feedback_proposal_does_not_claim_application_or_measured_gains(self):
        feedback = FeedbackParser().parse("问题：触发太宽")
        report = render_report(ROOT, feedback, build_proposals(feedback))
        self.assertIn("proposal only; no skill files were changed", report)
        self.assertIn("does not judge correctness", report)
        self.assertIn("edit the target skill", report)
        self.assertNotIn("10-15%", report)

    def test_improvement_report_stays_inside_target_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = create_sample(root)
            report_path = write_report(target, "reports/proposal.md", "proposal")
            self.assertEqual(report_path.read_text(encoding="utf-8"), "proposal")
            with self.assertRaises(FileExistsError):
                write_report(target, "reports/proposal.md", "replacement")
            with self.assertRaises(ValueError):
                write_report(target, "../outside.md", "outside")

    def test_feedback_parser_classifies_and_preserves_good_practice(self):
        parser = FeedbackParser()
        parsed = parser.parse("问题：输出太啰嗦。好的：保留原文事实。")
        self.assertEqual(len(parsed["issues"]), 1)
        self.assertEqual(parsed["issues"][0]["type"], "output_too_verbose")
        self.assertEqual(parsed["good"], ["保留原文事实"])
        compact = FeedbackParser().parse("问题：输出太啰嗦 好的：保留原文事实")
        self.assertEqual(len(compact["issues"]), 1)
        self.assertEqual(compact["good"], ["保留原文事实"])
        unlabelled = FeedbackParser().parse("输出太啰嗦")
        self.assertEqual(unlabelled["issues"][0]["type"], "output_too_verbose")

    def test_feedback_file_reference_cannot_escape_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "skill"
            root.mkdir()
            (Path(temp) / "outside.txt").write_text("Problem: outside", encoding="utf-8")
            with self.assertRaises(ValueError):
                FeedbackParser().parse("@../outside.txt", base_dir=root)


if __name__ == "__main__":
    unittest.main()
