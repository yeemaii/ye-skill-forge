#!/usr/bin/env python3
"""Ye Skill Forge 统一中文 CLI。"""

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.cli import configure_console
from core.lifecycle import (
    TARGETS,
    atlas,
    compile_targets,
    drift_report,
    install_simulate,
    output_eval,
    package_skill,
    registry_audit,
    skill_ir,
    telemetry_event,
    trigger_eval,
    trust_audit,
    upgrade_check,
    read_json,
    write_report,
)
from core.skill_utils import validate_skill
from scripts.create import create_package
from scripts.evaluate import evaluate_skill
from scripts.improve import build_proposals, render_report
from core.feedback_parser import FeedbackParser


def path_arg(value):
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"目录不存在: {path}")
    return path


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if value.get("ok", True) else 2


def command_validate(args):
    findings = validate_skill(args.skill_dir)
    return emit({"ok": not any(item["severity"] == "error" for item in findings), "findings": findings, "evidence_status": "static"})


def command_evaluate(args):
    return emit(evaluate_skill(args.skill_dir))


def command_create(args):
    data = {
        "name": args.slug,
        "display_name": args.skill_name,
        "author": args.author,
        "job": args.job,
        "template": args.template,
        "input_description": args.input_description or "说明输入及缺失字段。",
        "output_format": args.output_format or "按输出契约返回 Markdown。",
        "workflow_steps": args.workflow_step or ["读取全部输入", "执行工作流", "按契约检查输出"],
        "exclusions": args.exclude or ["不处理职责之外的一次性请求"],
        "quality_standards": "\n".join(f"- {item}" for item in (args.quality_check or ["完整、准确、可核查"])) ,
        "architecture": args.architecture or "",
        "agents": args.agents or "使用单一执行角色；只有独立且可验证的工作才委派。",
        "configuration": args.configuration or "无用户可选配置。",
    }
    try:
        paths, findings = create_package(data, args.output_dir or (Path.cwd() / args.slug))
    except (FileExistsError, ValueError, OSError) as exc:
        return emit({"ok": False, "error": str(exc)})
    return emit({"ok": True, "paths": paths, "warnings": [item for item in findings if item["severity"] == "warning"], "evidence_status": "executed-structure"})


def command_improve(args):
    try:
        feedback = FeedbackParser().parse(args.feedback, base_dir=args.skill_dir)
        proposals = build_proposals(feedback)
        report = render_report(args.skill_dir, feedback, proposals)
    except (ValueError, OSError, FileNotFoundError) as exc:
        return emit({"ok": False, "error": str(exc)})
    print(report)
    return 0


def command_skill_ir(args):
    return emit(skill_ir(args.skill_dir))


def command_trigger_eval(args):
    return emit(trigger_eval(args.skill_dir))


def command_output_eval(args):
    return emit(output_eval(args.skill_dir))


def command_trust(args):
    return emit(trust_audit(args.skill_dir))


def command_compile(args):
    try:
        output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
        return emit(compile_targets(args.skill_dir, output_dir, args.target))
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        return emit({"ok": False, "error": str(exc)})


def command_package(args):
    try:
        output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
        return emit(package_skill(args.skill_dir, output_dir, args.zip))
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        return emit({"ok": False, "error": str(exc)})


def command_install(args):
    try:
        return emit(install_simulate(args.skill_dir, args.package_dir))
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        return emit({"ok": False, "error": str(exc)})


def command_upgrade(args):
    try:
        return emit(upgrade_check(args.skill_dir, args.previous))
    except (ValueError, OSError) as exc:
        return emit({"ok": False, "error": str(exc)})


def command_registry(args):
    return emit(registry_audit(args.skill_dir))


def command_telemetry(args):
    try:
        if args.action == "record":
            return emit(telemetry_event(args.skill_dir, args.event, args.outcome, args.failure_type, args.command))
        return emit(drift_report(args.skill_dir))
    except (ValueError, OSError) as exc:
        return emit({"ok": False, "error": str(exc)})


def command_atlas(args):
    return emit(atlas(args.workspace))


def command_review(args, quiet=False):
    root = args.skill_dir
    checks = {
        "validate": {"result": validate_skill(root)},
        "trigger": trigger_eval(root),
        "output": output_eval(root),
        "trust": trust_audit(root),
        "ir": skill_ir(root),
        "registry": registry_audit(root),
    }
    findings = checks["validate"]["result"]
    gates = []
    gates.append({"key": "structure", "status": "pass" if not any(item["severity"] == "error" for item in findings) else "block", "evidence": "validate"})
    for key in ("trigger", "output"):
        result = checks[key]
        gates.append({"key": key, "status": "pass" if result.get("ok") else "warn", "evidence": f"reports/{key}_eval.json", "reason": result.get("status", "missing")})
    trust_findings = checks["trust"].get("findings", [])
    trust_status = "block" if not checks["trust"].get("ok") else "warn" if any(item.get("severity") == "warn" for item in trust_findings) else "pass"
    gates.append({"key": "trust", "status": trust_status, "evidence": "reports/security_trust.json", "findings": len(trust_findings)})
    gates.append({"key": "ir", "status": "pass" if checks["ir"].get("contract", {}).get("has_workflow") else "warn", "evidence": "reports/skill_ir.json"})
    gates.append({"key": "registry", "status": "pass" if checks["registry"].get("ok") else "warn", "evidence": "reports/registry_audit.json"})
    blockers = sum(1 for gate in gates if gate["status"] == "block")
    warnings = sum(1 for gate in gates if gate["status"] == "warn")
    result = {"ok": blockers == 0, "decision": "blocked" if blockers else "review" if warnings else "pass", "gates": gates, "blockers": blockers, "warnings": warnings, "optional_not_run": ["盲审/A-B", "原生客户端权限探针", "外部客户端遥测", "多 skill Atlas"], "evidence_status": "mixed-static-and-executed"}
    write_report(root, "review", result, "Ye 综合审查")
    if quiet:
        return 0 if result["ok"] else 2
    return emit(result)


def command_release(args):
    review_code = command_review(argparse.Namespace(skill_dir=args.skill_dir), quiet=True)
    review = read_json(Path(args.skill_dir) / "reports" / "review.json", {}) or {}
    manifest = read_json(Path(args.skill_dir) / "manifest.json", {}) or {}
    strict = args.strict or manifest.get("maturity_tier") in {"library", "governed"}
    package = None
    install = None
    try:
        if args.package_dir:
            package_dir = Path(args.package_dir).expanduser().resolve()
            package = package_skill(args.skill_dir, package_dir, True)
            install = install_simulate(args.skill_dir, args.package_dir)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        return emit({"ok": False, "error": str(exc), "review": review})
    review_ready = review_code == 0 and (not strict or not review.get("warnings"))
    result = {"ok": review_ready and (not args.package_dir or (package and package.get("ok") and install and install.get("ok"))), "review_exit": review_code, "strict": strict, "warnings_block_release": strict, "review": review, "package": package, "install": install, "evidence_status": "release-preflight"}
    write_report(args.skill_dir, "release_check", result, "发布预检")
    return emit(result)


def build_parser():
    parser = argparse.ArgumentParser(description="Ye Skill Forge：中文优先的 skill 全生命周期工具")
    sub = parser.add_subparsers(dest="command", required=True)

    def skill_parser(name, help_text):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("skill_dir", type=path_arg)
        return child

    skill_parser("validate", "结构和元数据校验")
    sub.choices["validate"].set_defaults(func=command_validate)
    skill_parser("evaluate", "静态质量清单")
    sub.choices["evaluate"].set_defaults(func=command_evaluate)
    skill_parser("skill-ir", "生成平台无关 Skill IR")
    sub.choices["skill-ir"].set_defaults(func=command_skill_ir)
    skill_parser("trigger-eval", "检查触发正负例")
    sub.choices["trigger-eval"].set_defaults(func=command_trigger_eval)
    skill_parser("output-eval", "检查输出评测样例")
    sub.choices["output-eval"].set_defaults(func=command_output_eval)
    skill_parser("trust", "扫描脚本权限和秘密模式")
    sub.choices["trust"].set_defaults(func=command_trust)
    skill_parser("registry-audit", "审计版本和分发元数据")
    sub.choices["registry-audit"].set_defaults(func=command_registry)
    skill_parser("review", "运行核心门禁并汇总证据")
    sub.choices["review"].set_defaults(func=command_review)

    create = sub.add_parser("create", help="创建 skill 包")
    create.add_argument("skill_name")
    create.add_argument("--slug", required=True)
    create.add_argument("--job", required=True)
    create.add_argument("--output-dir", default=None)
    create.add_argument("--template", choices=("minimal", "standard", "advanced"), default="standard")
    create.add_argument("--input-description")
    create.add_argument("--output-format")
    create.add_argument("--workflow-step", action="append")
    create.add_argument("--exclude", action="append")
    create.add_argument("--quality-check", action="append")
    create.add_argument("--architecture")
    create.add_argument("--agents")
    create.add_argument("--configuration")
    create.add_argument("--author", default="Ye")
    create.set_defaults(func=command_create)

    improve = skill_parser("improve", "根据反馈生成改进提案")
    improve.add_argument("--feedback", required=True)
    improve.set_defaults(func=command_improve)

    compile_parser = skill_parser("compile", "从同一源生成目标适配")
    compile_parser.add_argument("--target", action="append", choices=TARGETS, required=True)
    compile_parser.add_argument("--output-dir", default=None)
    compile_parser.set_defaults(func=command_compile)

    package_parser = skill_parser("package", "生成安全 zip 归档")
    package_parser.add_argument("--output-dir", default=None)
    package_parser.add_argument("--zip", action="store_true", default=True)
    package_parser.set_defaults(func=command_package)

    install_parser = skill_parser("install-simulate", "在临时目录解压并验证归档")
    install_parser.add_argument("--package-dir", required=True)
    install_parser.set_defaults(func=command_install)

    upgrade_parser = skill_parser("upgrade-check", "比较当前和上一版本")
    upgrade_parser.add_argument("--previous", required=True)
    upgrade_parser.set_defaults(func=command_upgrade)

    telemetry = skill_parser("telemetry", "记录或汇总元数据遥测")
    telemetry.add_argument("action", choices=("record", "drift"))
    telemetry.add_argument("--event", default="script_run")
    telemetry.add_argument("--outcome", default="accepted")
    telemetry.add_argument("--failure-type", default="none")
    telemetry.add_argument("--command", default="manual")
    telemetry.set_defaults(func=command_telemetry)

    atlas_parser = sub.add_parser("atlas", help="扫描多个 skill 的静态路由重叠")
    atlas_parser.add_argument("workspace", type=Path)
    atlas_parser.set_defaults(func=command_atlas)

    release = skill_parser("release-check", "运行发布前综合检查")
    release.add_argument("--package-dir")
    release.add_argument("--strict", action="store_true", help="将 warning 也视为发布阻断")
    release.set_defaults(func=command_release)
    return parser


if __name__ == "__main__":
    configure_console()
    parsed = build_parser().parse_args()
    raise SystemExit(parsed.func(parsed))
