#!/usr/bin/env python3
"""Run structural checks and a transparent, non-semantic skill checklist."""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cli import configure_console
from core.skill_utils import load_skill, validate_skill


RUBRIC = (
    ("workflow", re.compile(r"(?im)^#{1,6} .*?(workflow|工作流|流程|步骤|生命周期)"), "Add a concise, ordered workflow."),
    ("input-output", re.compile(r"(?im)^#{1,6} .*?(input|output|输入|输出|交付)"), "Define accepted inputs and the required output."),
    ("boundaries", re.compile(r"(?im)^#{1,6} .*?(boundar|scope|exclusion|边界|范围|非目标|门禁)"), "State nearby requests that should remain out of scope."),
    ("verification", re.compile(r"(?im)^#{1,6} .*?(quality|verif|validation|check|质量|验证|检查|证据)"), "Describe observable quality checks and recovery steps."),
)


def evaluate_skill(skill_path):
    findings = validate_skill(skill_path)
    try:
        root, _skill_file, metadata, _frontmatter, body = load_skill(skill_path)
    except (FileNotFoundError, ValueError, yaml.YAMLError):
        return {"path": str(skill_path), "structural_findings": findings, "checklist": [], "manual_review": []}

    description = metadata.get("description", "")
    checklist = [{
        "area": "description",
        "status": "pass" if isinstance(description, str) and len(description.strip()) >= 20 else "review",
        "evidence": f"{len(description.strip()) if isinstance(description, str) else 0} characters",
        "suggestion": "Describe the recurring job and recognizable trigger cases." if not isinstance(description, str) or len(description.strip()) < 20 else "Check semantic clarity and nearby-skill overlap manually.",
    }]
    for area, pattern, suggestion in RUBRIC:
        matched = bool(pattern.search(body))
        checklist.append({
            "area": area,
            "status": "pass" if matched else "review",
            "evidence": "matching section heading found" if matched else "no matching section heading found",
            "suggestion": suggestion if not matched else "Review whether the section contains concrete, testable instructions.",
        })

    eval_root = root / "evals"
    cases = []
    if eval_root.is_dir():
        cases = [p for p in eval_root.rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".jsonl", ".yaml", ".yml"}]
    checklist.append({
        "area": "evaluation-cases",
        "status": "present" if cases else "review",
        "evidence": f"{len(cases)} case file(s) found; execution was not checked" if cases else "no case files found under evals/",
        "suggestion": "Add representative positive, negative, and near-neighbor cases before claiming trigger accuracy." if not cases else "Run the cases and inspect false positives and false negatives.",
    })

    return {
        "path": str(root),
        "structural_findings": findings,
        "checklist": checklist,
        "manual_review": [
            "Does the skill solve a recurring job rather than a one-off request?",
            "Are its trigger and exclusions semantically distinct from neighboring skills?",
            "Do sample runs produce the required output without inventing evidence?",
        ],
        "limitations": "This static checklist does not measure semantic trigger accuracy, output quality, or user impact.",
    }


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", help="Path to the skill directory")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Return failure if any checklist item needs review")
    args = parser.parse_args()
    report = evaluate_skill(args.skill_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(f"Static skill review: {report['path']}")
        for finding in report["structural_findings"]:
            print(f"[{finding['severity'].upper()}] {finding['code']}: {finding['message']}")
        for item in report["checklist"]:
            print(f"[{item['status'].upper()}] {item['area']}: {item['evidence']}")
            print(f"  {item['suggestion']}")
        for question in report["manual_review"]:
            print(f"[MANUAL] {question}")
        if report.get("limitations"):
            print(f"Limit: {report['limitations']}")

    errors = any(item["severity"] == "error" for item in report["structural_findings"])
    needs_review = any(item["status"] == "review" for item in report["checklist"])
    return 1 if errors or (args.strict and needs_review) else 0


if __name__ == "__main__":
    raise SystemExit(main())
