#!/usr/bin/env python3
"""Turn observed usage feedback into a reviewable improvement proposal."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.feedback_parser import FeedbackParser
from core.cli import configure_console
from core.skill_utils import is_within, resolve_skill_dir


RECOMMENDATIONS = {
    "output_too_verbose": ("Output contract", "Specify a shorter default and keep detail conditional.", "Compare both versions on the same representative input."),
    "output_too_brief": ("Output contract", "Name the missing sections or decisions the output must include.", "Check the revised output against a completeness checklist."),
    "output_format": ("Output contract", "Clarify required sections, ordering, and formatting constraints.", "Validate one normal case and one incomplete-input case."),
    "missing_feature": ("Workflow or boundary", "Decide whether this capability belongs in the skill; update scope and workflow only if it serves the recurring job.", "Add a representative case and a nearby out-of-scope case."),
    "trigger_false_positive": ("Description and boundaries", "Tighten the trigger and add an explicit nearby request that must not route here.", "Re-run positive and negative trigger cases."),
    "trigger_false_negative": ("Description and examples", "Add the missed user phrasing when it represents the skill's existing job.", "Re-run positive and near-neighbor trigger cases."),
    "trigger_accuracy": ("Description and boundaries", "Inspect the exact user request and distinguish it from neighboring skills.", "Add the observed request and its closest negative case."),
    "performance": ("Workflow", "Remove repeated work or add a deterministic helper only when it reduces real cost.", "Compare steps and resource use on the same input."),
    "boundary_unclear": ("Boundaries", "State when to use this skill and which adjacent tasks should stay out of scope.", "Review near-neighbor prompts for ambiguous routing."),
    "general": ("Relevant section", "Locate the instruction that produced the reported behavior and make the smallest change that addresses it.", "Replay the reported case and a regression case."),
}


def collect_feedback(args):
    inputs = []
    if args.feedback:
        inputs.append(args.feedback)
    for file_path in args.feedback_file:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Feedback file not found: {path}")
        if path.stat().st_size > 1_000_000:
            raise ValueError(f"Feedback file exceeds the 1 MB limit: {path}")
        inputs.append(path.read_text(encoding="utf-8-sig"))

    if not inputs and sys.stdin.isatty():
        print("Enter feedback. Finish with a line containing EOF.")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip().upper() == "EOF":
                break
            lines.append(line)
        if lines:
            inputs.append("\n".join(lines))
    if not inputs:
        raise ValueError("Provide --feedback, --feedback-file, or interactive input.")
    return inputs


def build_proposals(feedback):
    proposals = []
    seen = set()
    for issue in feedback.get("issues", []):
        issue_type = issue.get("type", "general")
        title, change, verification = RECOMMENDATIONS.get(issue_type, RECOMMENDATIONS["general"])
        key = (issue_type, issue.get("description", "").strip().casefold())
        if key in seen:
            continue
        seen.add(key)
        proposals.append({
            "type": issue_type,
            "title": title,
            "observation": issue.get("description", ""),
            "recommended_change": change,
            "verification": verification,
        })
    for suggestion in feedback.get("suggestions", []):
        key = ("suggestion", suggestion.casefold())
        if key not in seen:
            seen.add(key)
            proposals.append({
                "type": "user_suggestion",
                "title": "Review user suggestion",
                "observation": suggestion,
                "recommended_change": "Check that the suggestion supports the skill's recurring job and does not weaken an existing boundary.",
                "verification": "Add a representative case before treating the change as verified.",
            })
    return proposals


def render_report(skill_path, feedback, proposals):
    lines = [
        "# Skill Improvement Proposal",
        "",
        f"- Target: `{skill_path}`",
        f"- Created: {datetime.now(timezone.utc).replace(microsecond=0).isoformat()}",
        "- Status: proposal only; no skill files were changed",
        "",
        "## Observed issues",
    ]
    if feedback.get("issues"):
        lines.extend(f"- **{item.get('type', 'general')}**: {item.get('description', '')}" for item in feedback["issues"])
    else:
        lines.append("- No issue statements were detected. Review the source feedback manually.")

    lines.extend(["", "## Behaviors to preserve"])
    lines.extend(f"- {item}" for item in feedback.get("good", []))
    if not feedback.get("good"):
        lines.append("- None were identified; ask the skill owner which successful behaviors must remain unchanged.")

    lines.extend(["", "## Proposed changes"])
    if proposals:
        for index, item in enumerate(proposals, 1):
            lines.extend([
                f"{index}. **{item['title']}** ({item['type']})",
                f"   - Observation: {item['observation']}",
                f"   - Change: {item['recommended_change']}",
                f"   - Verification: {item['verification']}",
            ])
    else:
        lines.append("- No actionable proposal was generated. Inspect the original feedback and target skill together.")

    lines.extend([
        "",
        "## Evidence limits",
        "This helper classifies text with rules. It does not judge correctness, edit the target skill, or measure improvement. Apply selected changes with an authoring agent, then run the listed checks and review the diff.",
        "",
    ])
    return "\n".join(lines)


def write_report(skill_path, report_path, content):
    root = resolve_skill_dir(skill_path)
    target = Path(report_path).expanduser()
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    if not is_within(target, root):
        raise ValueError("Report path must stay inside the target skill directory")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing report: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return target


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", help="Target skill directory")
    parser.add_argument("--feedback", help="Feedback text")
    parser.add_argument("--feedback-file", action="append", default=[], help="Feedback file; may be repeated")
    parser.add_argument("--report", help="Optional new report path, relative to the skill directory")
    args = parser.parse_args()

    try:
        root = resolve_skill_dir(args.skill_path)
        feedback_inputs = collect_feedback(args)
        feedback = FeedbackParser().parse(feedback_inputs, base_dir=root)
        proposals = build_proposals(feedback)
        report = render_report(root, feedback, proposals)
        if args.report:
            report_path = write_report(root, args.report, report)
            print(f"Proposal written to {report_path}")
        else:
            print(report)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
