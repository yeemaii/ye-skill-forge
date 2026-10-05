"""Check report side effects, release depth, and inactive example delivery."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.lifecycle import install_simulate, package_skill, tree_sha256
from core.package import validate_package
from core.review import review_skill
from core.skill_utils import load_skill
from scripts.materialize_example import materialize_example


class ReviewExampleTests(unittest.TestCase):
    def test_local_review_writes_only_one_aggregate_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("note-cleanup", Path(temp) / "notes")
            before = tree_sha256(root)
            report = review_skill(root)
            self.assertEqual(report["profile"], "local")
            self.assertEqual({p.name for p in (root / "reports").iterdir()}, {"review.json", "review.md"})
            self.assertEqual(tree_sha256(root), before)
            self.assertFalse(report["behavior_verified"])
            self.assertEqual(next(g for g in report["gates"] if g["key"] == "structure")["status"], "checked")
            self.assertNotIn("registry", {g["key"] for g in report["gates"]})
            trigger = next(g for g in report["gates"] if g["key"] == "trigger")
            self.assertEqual(trigger["status"], "checked")
            self.assertIsNone(trigger["details"]["metrics"]["trigger_precision"])

    def test_readonly_family_review_keeps_child_findings_without_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("research-package", Path(temp) / "research")
            child = root / "skills/source-triage/SKILL.md"
            child.write_text("broken", encoding="utf-8")
            report = review_skill(root, persist=False)
            self.assertFalse(report["ok"])
            self.assertFalse(list(root.rglob("reports")))
            self.assertTrue(any(g["key"] == "structure" and g["findings"] for g in report["gates"]))

    def test_family_aggregates_all_children_and_writes_no_child_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("research-package", Path(temp) / "research")
            report = review_skill(root)
            children = next(g["children"] for g in report["gates"] if g["key"] == "children")
            self.assertEqual({c["name"] for c in children}, {"router", "source-triage", "evidence-synthesis"})
            self.assertTrue(all(c["gates"] for c in children))
            self.assertEqual(list(root.rglob("reports")), [root / "reports"])

    def test_production_checks_and_malformed_cases_are_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("incident-diagnosis", Path(temp) / "diagnosis")
            report = review_skill(root, profile="production", persist=False)
            self.assertTrue(any(g["key"] == "behavior" and g["status"] == "warn" for g in report["gates"]))
            self.assertTrue(any(g["key"] == "trigger" and g["status"] == "warn" for g in report["gates"]))
            (root / "evals/trigger_cases.json").write_text("not json", encoding="utf-8")
            self.assertFalse(review_skill(root, profile="local", persist=False)["ok"])

    def test_family_review_checks_root_output_and_supplied_trigger_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("research-package", Path(temp) / "research")
            report = review_skill(root, persist=False)
            output = next(g for g in report["gates"] if g["key"] == "output")
            self.assertEqual(output["status"], "checked")
            self.assertGreater(output["details"]["cases"], 0)
            self.assertFalse(list(root.rglob("reports")))
            cases = root / "evals/output/cases.json"
            original = cases.read_bytes()
            cases.write_text("not json", encoding="utf-8")
            self.assertFalse(review_skill(root, persist=False)["ok"])
            cases.write_bytes(original)
            (root / "evals/trigger_cases.json").write_text("not json", encoding="utf-8")
            self.assertFalse(review_skill(root, persist=False)["ok"])

    def test_cli_no_report_and_strict_release_have_distinct_depth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("note-cleanup", Path(temp) / "notes")
            command = [sys.executable, str(ROOT / "scripts/ye.py")]
            audit = subprocess.run(command + ["review", str(root), "--no-report"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertFalse((root / "reports").exists())
            release = subprocess.run(command + ["release-check", str(root), "--strict"], capture_output=True, text=True, encoding="utf-8")
            result = json.loads(release.stdout)
            self.assertEqual(release.returncode, 2)
            self.assertEqual(result["review"]["profile"], "distribution")
            self.assertTrue(any(g["key"] == "registry" for g in result["review"]["gates"]))

    def test_examples_are_inactive_in_the_engine_archive(self):
        self.assertFalse(list((ROOT / "examples").rglob("SKILL.md")))
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "engine"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("reports", "__pycache__", "dist"))
            archive = package_skill(copy, Path(temp) / "dist")
            with zipfile.ZipFile(archive["archive"]) as handle:
                active = [name for name in handle.namelist() if Path(name).name == "SKILL.md"]
                self.assertEqual(active, ["SKILL.md"])
                self.assertTrue(any(name.endswith("SKILL.example.md") for name in handle.namelist()))
            self.assertTrue(install_simulate(copy, archive["archive"])["ok"])

    def test_install_rejects_undeclared_nested_active_skills_even_with_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("note-cleanup", Path(temp) / "notes")
            nested = root / "examples/unintended"
            nested.mkdir(parents=True)
            shutil.copy2(root / "SKILL.md", nested / "SKILL.md")
            archive = package_skill(root, Path(temp) / "dist")
            self.assertFalse(install_simulate(root, archive["archive"])["ok"])

    def test_family_rejects_undeclared_entries_but_ignores_local_build_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = materialize_example("research-package", Path(temp) / "research")
            build = root / "dist/codex"
            build.mkdir(parents=True)
            shutil.copy2(root / "router/SKILL.md", build / "SKILL.md")
            self.assertTrue(validate_package(root)["ok"])
            extra = root / "examples/unintended"
            extra.mkdir(parents=True)
            shutil.copy2(root / "router/SKILL.md", extra / "SKILL.md")
            validation = validate_package(root)
            self.assertFalse(validation["ok"])
            self.assertTrue(any(f["code"] == "undeclared-entry" and f["path"] == "examples/unintended/SKILL.md" for f in validation["findings"]))
            self.assertFalse(review_skill(root, persist=False)["ok"])
            archive = package_skill(root, Path(temp) / "dist")
            self.assertFalse(install_simulate(root, archive["archive"])["ok"])

    def test_materialization_rejects_non_runnable_comparison_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "comparison"
            with self.assertRaises(ValueError):
                materialize_example("note-cleanup-improvement", output)
            self.assertFalse(output.exists())

    def test_materialization_preserves_source_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            original = (ROOT / "examples/note-cleanup/SKILL.example.md").read_bytes()
            root = materialize_example("note-cleanup", Path(temp) / "notes")
            self.assertEqual(load_skill(root)[2]["name"], "note-cleanup")
            self.assertEqual((root / "SKILL.md").read_bytes(), original)
            self.assertEqual((ROOT / "examples/note-cleanup/SKILL.example.md").read_bytes(), original)
            with self.assertRaises(FileExistsError):
                materialize_example("note-cleanup", root)
            with self.assertRaises(ValueError):
                materialize_example("../methods", Path(temp) / "bad")
            with self.assertRaises(ValueError):
                materialize_example("note-cleanup", ROOT / "examples/test-copy")


if __name__ == "__main__":
    unittest.main()
