"""单 Skill 与 SkillPackage 使用同一个审查入口。"""

from pathlib import Path

from core.lifecycle import behavior_evidence, is_skill_package, package_manifest, registry_audit, skill_ir, trust_audit, trigger_eval, output_eval, write_report
from core.package import validate_package, route_eval, handoff_check
from core.skill_utils import validate_skill


def review_skill(root):
    root = Path(root).resolve()
    manifest = package_manifest(root)
    is_package = is_skill_package(root)
    gates = []

    def gate(key, status, evidence, **detail):
        gates.append({"key": key, "status": status, "evidence": evidence, **detail})

    if is_package:
        structure = validate_package(root)
        gate("structure", "block" if not structure["ok"] else "warn" if any(item["severity"] == "warning" for item in structure["findings"]) else "pass", "package-validate", findings=structure["findings"])
        if structure["ok"]:
            ir = skill_ir(root)
            gate("ir", "pass" if ir.get("contract", {}).get("has_router") else "warn", "reports/skill_ir.json")
            for key, check in (("routing", route_eval), ("handoff", handoff_check)):
                result = check(root)
                gate(key, "block" if not result["ok"] else "warn" if result.get("status") == "review" else "pass", key, evidence_status=result["evidence_status"])
            children = []
            targets = [{"name": "router", "path": structure["router"]}] + structure["children"]
            for child in targets:
                result = review_skill(root / child["path"])
                children.append({"name": child["name"], "decision": result["decision"], "blockers": result["blockers"], "warnings": result["warnings"]})
            gate("children", "block" if any(c["blockers"] for c in children) else "warn" if any(c["warnings"] for c in children) else "pass", "<child>/reports/review.json", children=children)
    else:
        findings = validate_skill(root)
        structural_errors = any(item["severity"] == "error" for item in findings)
        mature = manifest.get("maturity_tier") in {"production", "library", "governed"}
        meaningful_warnings = any(
            item["severity"] == "warning" and (mature or item.get("code") != "scaffold-content")
            for item in findings
        )
        gate("structure", "block" if structural_errors else "warn" if meaningful_warnings else "pass", "validate", findings=findings)
        if not structural_errors:
            for key, check in (("trigger", trigger_eval), ("output", output_eval)):
                result = check(root)
                gate(key, "block" if result.get("status") == "invalid" else "pass" if result["ok"] else "warn", f"reports/{key}_eval.json", reason=result.get("status", "missing"), evidence_status=result["evidence_status"], findings=result.get("findings", []))
            ir = skill_ir(root)
            gate("ir", "pass" if ir.get("contract", {}).get("has_workflow") else "warn", "reports/skill_ir.json")

    trust = trust_audit(root)
    gate("trust", "block" if not trust["ok"] else "warn" if any(i["severity"] == "warn" for i in trust["findings"]) else "pass", "reports/security_trust.json", findings=trust["findings"])
    registry = registry_audit(root)
    gate("registry", "pass" if registry["ok"] else "warn", "reports/registry_audit.json")
    behavior = behavior_evidence(root)
    mature = manifest.get("maturity_tier") in {"production", "library", "governed"}
    if behavior.get("ok"):
        status = "pass" if behavior.get("behavior_verified") else "block" if behavior.get("status") == "failed" else "warn"
        gate("behavior", status, "reports/behavior_evidence.json", cases=behavior.get("cases", 0), counts=behavior.get("counts"), coverage_verified=behavior.get("coverage_verified"), judge_mode=behavior.get("judge_mode"), evidence_status=behavior.get("evidence_status"))
        if mature and not behavior.get("coverage_verified"):
            gate("behavior-coverage", "warn", "完整行为案例计划", reason="旧格式记录未绑定完整 suite，无法核实测试分母")
    elif behavior.get("status") == "invalid":
        gate("behavior", "block", "reports/behavior_evidence.json", findings=behavior.get("findings", []), evidence_status=behavior.get("evidence_status"))
    elif mature:
        gate("behavior", "warn", "模型/客户端行为重放", reason="尚未记录与当前源版本绑定的行为证据")
    blockers = sum(item["status"] == "block" for item in gates)
    warnings = sum(item["status"] == "warn" for item in gates)
    result = {
        "ok": blockers == 0,
        "decision": "blocked" if blockers else "review" if warnings else "pass",
        "gates": gates, "blockers": blockers, "warnings": warnings,
        "behavior_verified": bool(behavior.get("behavior_verified")),
        "semantic_review": "requires-agent-review;static-gates-do-not-assess-instruction-meaning",
        "optional_not_run": (["模型或客户端行为重放"] if not behavior.get("behavior_verified") else []) + ["独立评审/A-B", "原生客户端权限探针"],
        "evidence_status": "mixed-static-and-executed-structure",
    }
    return write_report(root, "review", result, "Ye 综合审查")
