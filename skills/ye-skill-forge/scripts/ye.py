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
    package_manifest,
    record_behavior_evidence,
)
from core.skill_utils import validate_skill
from scripts.create import create_package
from scripts.evaluate import evaluate_skill
from scripts.improve import build_proposals, render_report
from core.feedback_parser import FeedbackParser
from core.intent import clarify
from core.package import create_package_scaffold, handoff_check, route_eval, validate_package
from core.evolution import apply_evolution, build_evidence_packet, evolution_summary, record_evolution, rollback_evolution
from core.review import review_skill


def default_skill_output(slug):
    """Choose the project-local runtime root without writing into Ye itself."""
    base = Path.cwd().resolve()
    if base == ROOT or ROOT in base.parents:
        base = ROOT.parents[1]
    return base / ".ye" / "skills" / slug


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
        "input_description": args.input_description or "",
        "output_format": args.output_format or "",
        "workflow_steps": args.workflow_step or ["读取全部输入", "执行工作流", "按契约检查输出"],
        "exclusions": args.exclude or [],
        "quality_standards": "\n".join(f"- {item}" for item in (args.quality_check or [])),
        "architecture": args.architecture or "",
        "agents": args.agents or "使用单一执行角色；只有独立且可验证的工作才委派。",
        "configuration": args.configuration or "无用户可选配置。",
        "root_problem": args.root_problem or "",
        "user_result": args.user_result or "",
        "reusable_method": args.reusable_method or "",
        "materials": args.material,
        "tools": args.tool,
        "permissions": args.permission,
        "target_user": args.target_user or "",
        "trigger_examples": args.trigger or [],
        "near_neighbors": args.near_neighbor or [],
        "success_signals": args.success_signal or [],
        "root_confirmed": args.root_confirmed,
    }
    try:
        if args.brief_file:
            brief = read_json(args.brief_file, None)
            if not isinstance(brief, dict):
                raise ValueError("--brief-file 需要有效 JSON 对象")
            data.update(brief)
            data.update({"name": args.slug, "display_name": args.skill_name})
        if not data.get("job"):
            data["job"] = data.get("recurring_job", "")
        if args.require_ready and clarify(data)["next_action"] != "design":
            return emit({"ok": False, "error": "意图尚未明确；未生成文件", "intent": clarify(data)})
        paths, findings = create_package(data, args.output_dir or default_skill_output(args.slug))
    except (FileExistsError, ValueError, OSError) as exc:
        return emit({"ok": False, "error": str(exc)})
    return emit({"ok": True, "paths": paths, "warnings": [item for item in findings if item["severity"] == "warning"], "evidence_status": "executed-structure"})


def command_intent(args):
    try:
        brief = read_json(args.brief_file, None) if args.brief_file else json.loads(args.brief) if args.brief else {"idea": args.idea, "job": args.job}
        if not isinstance(brief, dict):
            raise ValueError("意图简报必须是 JSON 对象")
    except (json.JSONDecodeError, ValueError) as exc:
        return emit({"ok": False, "error": f"--brief 不是有效 JSON: {exc}"})
    result = clarify(brief, args.max_questions)
    result["ok"] = True
    result["evidence_status"] = "intent-model;未替用户确认根问题"
    return emit(result)


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


def command_behavior_evidence(args):
    try:
        return emit(record_behavior_evidence(args.skill_dir, args.evidence_file))
    except (ValueError, OSError) as exc:
        return emit({"ok": False, "error": str(exc)})


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


def command_package_validate(args):
    return emit(validate_package(args.package_dir))


def command_package_create(args):
    try:
        return emit(create_package_scaffold(args.slug, args.output_dir or default_skill_output(args.slug), args.child))
    except (ValueError, FileExistsError, OSError) as exc:
        return emit({"ok": False, "error": str(exc)})


def command_route_eval(args):
    return emit(route_eval(args.package_dir))


def command_handoff_check(args):
    return emit(handoff_check(args.package_dir))


def command_evolve(args):
    try:
        if args.action == "summary":
            return emit(evolution_summary(args.skill_dir))
        if args.action == "rollback":
            if not args.packet:
                raise ValueError("rollback 需要 --packet 指定应用记录")
            return emit(rollback_evolution(args.skill_dir, args.packet))
        if args.action == "apply":
            if not args.packet or not args.change_file:
                raise ValueError("apply 需要 --packet 和 --change-file；默认预览，--apply 才写入")
            return emit(apply_evolution(args.skill_dir, args.packet, args.change_file, args.evidence_file, args.apply, args.allow_self_edit))
        if not args.feedback:
            raise ValueError("record 需要 --feedback；它只记录提案，不会自动修改 Skill")
        feedback = FeedbackParser().parse(args.feedback, base_dir=args.skill_dir)
        proposals = build_proposals(feedback)
        packet = build_evidence_packet(args.skill_dir, feedback, proposals)
        return emit(record_evolution(args.skill_dir, packet))
    except (ValueError, OSError, SyntaxError) as exc:
        return emit({"ok": False, "error": str(exc)})


def command_atlas(args):
    return emit(atlas(args.workspace))


def command_review(args, quiet=False):
    try:
        result = review_skill(args.skill_dir)
    except (OSError, ValueError) as exc:
        result = {"ok": False, "error": str(exc)}
    if quiet:
        return 0 if result["ok"] else 2
    return emit(result)


def command_release(args):
    review_code = command_review(argparse.Namespace(skill_dir=args.skill_dir), quiet=True)
    review = read_json(Path(args.skill_dir) / "reports" / "review.json", {}) or {}
    manifest = package_manifest(args.skill_dir)
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
    behavior = skill_parser("behavior-evidence", "记录并绑定真实行为验证证据")
    behavior.add_argument("--evidence-file", required=True)
    behavior.set_defaults(func=command_behavior_evidence)
    skill_parser("trust", "扫描脚本权限和秘密模式")
    sub.choices["trust"].set_defaults(func=command_trust)
    skill_parser("registry-audit", "审计版本和分发元数据")
    sub.choices["registry-audit"].set_defaults(func=command_registry)
    skill_parser("review", "运行核心门禁并汇总证据")
    sub.choices["review"].set_defaults(func=command_review)

    intent = sub.add_parser("intent", help="从模糊想法生成用户结果、设计字段和高信息量提问")
    intent_group = intent.add_mutually_exclusive_group(required=True)
    intent_group.add_argument("--idea")
    intent_group.add_argument("--brief", help="JSON 形式的意图简报")
    intent_group.add_argument("--brief-file", help="意图简报 JSON 文件")
    intent.add_argument("--job")
    intent.add_argument("--max-questions", type=int, default=2)
    intent.set_defaults(func=command_intent)

    create = sub.add_parser("create", help="创建 skill 包")
    create.add_argument("skill_name")
    create.add_argument("--slug", required=True)
    create.add_argument("--job", help="重复任务；也可由 --brief-file 提供")
    create.add_argument("--brief-file", help="消费 intent 简报，保留领域决策和假设")
    create.add_argument("--require-ready", action="store_true", help="用户结果/职责/输出/边界/成功条件不明确时拒绝生成")
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
    create.add_argument("--root-problem")
    create.add_argument("--root-confirmed", action="store_true", help="已有用户证据确认根问题")
    create.add_argument("--user-result", help="用户最终要得到的结果")
    create.add_argument("--reusable-method", help="已知有效做法、规范或参考来源")
    create.add_argument("--material", action="append", default=[], help="正常工作所需材料；可重复")
    create.add_argument("--tool", action="append", default=[], help="正常工作所需工具；可重复")
    create.add_argument("--permission", action="append", default=[], help="必要授权或外部动作边界；可重复")
    create.add_argument("--target-user")
    create.add_argument("--trigger", action="append")
    create.add_argument("--near-neighbor", action="append")
    create.add_argument("--success-signal", action="append")
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

    package_validate = sub.add_parser("package-validate", help="验证 SkillPackage、Router 和子 Skill")
    package_validate.add_argument("package_dir", type=path_arg)
    package_validate.set_defaults(func=command_package_validate)

    package_create = sub.add_parser("package-init", help="创建多 Skill 包的可校验骨架")
    package_create.add_argument("slug", help="小写包名")
    package_create.add_argument("--child", action="append", required=True, help="子 Skill 名称，可重复")
    package_create.add_argument("--output-dir")
    package_create.set_defaults(func=command_package_create)

    route_parser = sub.add_parser("route-eval", help="检查包级路由样例和目标")
    route_parser.add_argument("package_dir", type=path_arg)
    route_parser.set_defaults(func=command_route_eval)

    handoff_parser = sub.add_parser("handoff-check", help="检查 Router 到子 Skill 的交接契约")
    handoff_parser.add_argument("package_dir", type=path_arg)
    handoff_parser.set_defaults(func=command_handoff_check)

    evolve = skill_parser("evolve", "记录证据驱动的进化提案")
    evolve.add_argument("action", choices=("record", "summary", "apply", "rollback"))
    evolve.add_argument("--feedback")
    evolve.add_argument("--packet", help="目标 reports/evolution 内的提案或应用记录")
    evolve.add_argument("--change-file", help="显式文本变更集 JSON")
    evolve.add_argument("--evidence-file", help="版本绑定的行为回放记录 JSON")
    evolve.add_argument("--apply", action="store_true", help="审核后写入；默认只预览候选")
    evolve.add_argument("--allow-self-edit", action="store_true", help="显式允许已授权的 Ye 自身修改")
    evolve.set_defaults(func=command_evolve)

    release = skill_parser("release-check", "运行发布前综合检查")
    release.add_argument("--package-dir")
    release.add_argument("--strict", action="store_true", help="将 warning 也视为发布阻断")
    release.set_defaults(func=command_release)
    return parser


if __name__ == "__main__":
    configure_console()
    parsed = build_parser().parse_args()
    raise SystemExit(parsed.func(parsed))
