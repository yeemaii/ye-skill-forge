"""单 Skill 与 SkillPackage 使用同一个审查入口。"""

from pathlib import Path

from core.lifecycle import package_manifest, registry_audit, skill_ir, trust_audit, trigger_eval, output_eval, write_report
from core.package import validate_package, route_eval, handoff_check
from core.skill_utils import validate_skill


def review_skill(root):
    root = Path(root).resolve()
    manifest = package_manifest(root)
    is_package = (root / "package.json").is_file() or manifest.get("package_type") in {"skill-package", "skill-family"}
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
        gate("structure", "block" if structural_errors else "warn" if any(item["severity"] == "warning" for item in findings) else "pass", "validate", findings=findings)
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
    if manifest.get("maturity_tier") in {"production", "library", "governed"}:
        gate("behavior", "warn", "模型/客户端行为重放", reason="本命令未执行行为评测；严格发布预检不能靠静态案例通过")
    blockers = sum(item["status"] == "block" for item in gates)
    warnings = sum(item["status"] == "warn" for item in gates)
    result = {
        "ok": blockers == 0,
        "decision": "blocked" if blockers else "review" if warnings else "pass",
        "gates": gates, "blockers": blockers, "warnings": warnings,
        "behavior_verified": False,
        "optional_not_run": ["模型或客户端行为重放", "独立评审/A-B", "原生客户端权限探针"],
        "evidence_status": "mixed-static-and-executed-structure",
    }
    return write_report(root, "review", result, "Ye 综合审查")
