"""Risk-based checks with one aggregate report for a Skill or family."""

from pathlib import Path

from core.lifecycle import behavior_evidence, is_skill_package, package_manifest, registry_audit, skill_ir, trust_audit, trigger_eval, output_eval, write_report
from core.package import validate_package, route_eval, handoff_check
from core.skill_utils import validate_skill


PROFILES = {"scaffold": "local", "production": "production", "library": "distribution", "governed": "distribution"}


def review_skill(root, *, profile="auto", persist=True):
    root = Path(root).resolve()
    manifest = package_manifest(root)
    if profile == "auto":
        profile = PROFILES.get(manifest.get("maturity_tier"), "local")
    if profile not in {"local", "production", "distribution"}:
        raise ValueError(f"Unknown review profile: {profile}")
    is_package = is_skill_package(root)
    gates = []
    skipped = []

    def gate(key, status, evidence, **detail):
        gates.append({"key": key, "status": status, "evidence": evidence, **detail})

    def case_gate(key, result):
        status = "block" if result.get("status") == "invalid" else "checked" if result["ok"] else "warn"
        if profile == "local" and result.get("status") == "missing" and not result.get("files"):
            skipped.append({"key": key, "reason": "No cases supplied; local review does not require a benchmark suite"})
        else:
            gate(key, status, "supplied-case-structure;not-behavior", details=result)

    if is_package:
        structure = validate_package(root)
        findings = list(structure["findings"])
        members = [{"path": structure.get("router"), **structure.get("router_result", {})}] + structure.get("children", [])
        for member in members:
            findings.extend({**item, "path": member.get("path")} for item in member.get("findings", []) if item["severity"] == "error")
        gate("structure", "block" if not structure["ok"] else "warn" if any(item["severity"] == "warning" for item in findings) else "checked", "package-validate", findings=findings, details=structure)
        if structure["ok"]:
            triggers = trigger_eval(root, persist=False)
            if triggers.get("files"):
                case_gate("trigger", triggers)
            for key, check in (("routing", route_eval), ("handoff", handoff_check)):
                result = check(root)
                status = "block" if not result["ok"] else "warn" if result.get("status") == "review" else "checked"
                gate(key, status, "package-contract", details=result)
            children = []
            targets = [{"name": "router", "path": structure["router"]}] + structure["children"]
            for child in targets:
                result = review_skill(root / child["path"], profile=profile, persist=False)
                children.append({"name": child["name"], "path": child["path"], **result})
            gate("children", "block" if any(c["blockers"] for c in children) else "warn" if any(c["warnings"] for c in children) else "checked", "embedded-child-reviews", children=children)
    else:
        findings = validate_skill(root)
        structural_errors = any(item["severity"] == "error" for item in findings)
        meaningful_warnings = any(
            item["severity"] == "warning" and (profile != "local" or item.get("code") != "scaffold-content")
            for item in findings
        )
        gate("structure", "block" if structural_errors else "warn" if meaningful_warnings else "checked", "validate", findings=findings)
        if not structural_errors:
            case_gate("trigger", trigger_eval(root, persist=False))

    structure_ok = not any(item["key"] == "structure" and item["status"] == "block" for item in gates)
    if structure_ok:
        case_gate("output", output_eval(root, persist=False))
    if profile == "distribution" and structure_ok:
        ir = skill_ir(root, persist=False)
        complete = ir.get("contract", {}).get("has_router" if is_package else "has_workflow")
        gate("ir", "checked" if complete else "warn", "source-model", details=ir)
        registry = registry_audit(root, persist=False)
        gate("registry", "checked" if registry["ok"] else "warn", "distribution-metadata", details=registry)
    elif profile != "distribution":
        skipped.extend({"key": key, "reason": "Only required for distribution review"} for key in ("ir", "registry"))

    trust = trust_audit(root, persist=False)
    gate("trust", "block" if not trust["ok"] else "warn" if any(i["severity"] == "warn" for i in trust["findings"]) else "checked", "static-source-scan", details=trust)
    behavior = behavior_evidence(root)
    if behavior.get("ok"):
        status = "pass" if behavior.get("behavior_verified") else "block" if behavior.get("status") == "failed" else "warn"
        gate("behavior", status, "reports/behavior_evidence.json", details=behavior)
        if profile != "local" and not behavior.get("coverage_verified"):
            gate("behavior-coverage", "warn", "complete-planned-suite", reason="Legacy evidence does not establish the planned denominator")
    elif behavior.get("status") == "invalid":
        gate("behavior", "block", "reports/behavior_evidence.json", details=behavior)
    elif profile != "local":
        gate("behavior", "warn", "model/client-task-run", reason="No behavior evidence bound to the current source")
    else:
        skipped.append({"key": "behavior", "reason": "No task-run evidence supplied; behavior remains unverified"})
    blockers = sum(item["status"] == "block" for item in gates)
    warnings = sum(item["status"] == "warn" for item in gates)
    result = {
        "ok": blockers == 0,
        "decision": "blocked" if blockers else "review" if warnings else "pass",
        "profile": profile,
        "gates": gates, "blockers": blockers, "warnings": warnings,
        "skipped": skipped,
        "behavior_verified": bool(behavior.get("behavior_verified")),
        "semantic_review": "requires-agent-review;static-gates-do-not-assess-instruction-meaning",
        "optional_not_run": (["模型或客户端行为重放"] if not behavior.get("behavior_verified") else []) + ["独立评审/A-B", "原生客户端权限探针"],
        "evidence_status": "supplied-task-evidence-and-static-checks" if behavior.get("ok") else "static-checks-only",
        "limitations": "A check decision is not a judgment of domain quality, improvement, or release readiness.",
    }
    return write_report(root, "review", result, "Ye 综合审查", persist=persist)
