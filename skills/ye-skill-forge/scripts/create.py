#!/usr/bin/env python3
"""Create a new Agent Skills-compatible package from a small, explicit brief."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.generator import generate_frontmatter, generate_interface, generate_manifest, generate_skill, save_skill
from core.cli import configure_console
from core.skill_utils import is_within, validate_skill
from core.intent import build_intent_model


def slug_for(name, requested_slug=None):
    slug = (requested_slug or "").strip().lower()
    if not slug:
        pieces = re.findall(r"[a-z0-9]+", name.lower())
        slug = "-".join(pieces)
    if not slug:
        raise ValueError("只含非拉丁字符的名称必须显式提供小写 slug，请使用 --slug。")
    if len(slug) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("slug 必须是 1-64 个小写字母或数字，并用单个连字符分隔。")
    return slug


def read_lines(prompt, required=False):
    print(prompt)
    values = []
    while True:
        value = input("> ").strip()
        if not value:
            break
        values.append(value)
    if required and not values:
        raise ValueError("至少需要提供一项内容。")
    return values


def collect_interactive_brief(display_name, slug):
    print("请描述这个 skill 要负责的重复任务。")
    job = input("> ").strip()
    if not job:
        raise ValueError("skill 的重复任务不能为空。")

    audience = input("使用范围 [personal/team/complex]（默认 team）：").strip().lower() or "team"
    template = {"personal": "minimal", "team": "standard", "complex": "advanced"}.get(audience)
    if not template:
        raise ValueError("范围只能是 personal、team 或 complex。")

    input_description = input("接受的输入（默认：描述任务输入）：").strip()
    output_format = input("所需输出（默认：简洁 Markdown）：").strip()
    workflow_steps = read_lines("工作流步骤，每行一个；空行结束：")
    exclusions = read_lines("应保持在范围外的近邻请求，每行一个：")
    quality_standards = read_lines("可观察的质量检查，每行一个：")
    data = {
        "name": slug,
        "display_name": display_name,
        "job": job,
        "template": template,
        "input_description": input_description or "描述接受的输入及缺失字段。",
        "output_format": output_format or "按契约返回简洁 Markdown。",
        "workflow_steps": workflow_steps,
        "exclusions": exclusions,
        "quality_standards": "\n".join(f"- {item}" for item in quality_standards) or "检查完整性、正确性和请求的格式。",
        "author": "Unspecified",
    }
    print("可选澄清：请只回答会改变职责或边界的问题；直接回车表示暂用假设。")
    root_problem = input("真正要消除的重复失败（可留空）：").strip()
    target_user = input("反复使用者（可留空）：").strip()
    triggers = read_lines("用户自然表达示例（每行一个；空行结束）：")
    near_neighbors = read_lines("最像但不应触发的请求（每行一个；空行结束）：")
    success_signals = read_lines("可观察成功信号（每行一个；空行结束）：")
    data.update({"root_problem": root_problem, "root_confirmed": bool(root_problem), "target_user": target_user, "trigger_examples": triggers, "near_neighbors": near_neighbors, "success_signals": success_signals})
    if template == "advanced":
        data["architecture"] = input("哪些独立组件足以说明需要 advanced 模板？").strip()
        data["agents"] = input("是否需要独立角色？如不需要，请说明原因。").strip()
        data["configuration"] = input("哪些用户选项会实质改变行为？").strip() or "无用户可选配置。"
        if not data["architecture"] or not data["agents"]:
            raise ValueError("advanced 模板需要组件说明和明确的角色/委派决定。")
    return data


def collect_argument_brief(args, slug):
    return {
        "name": slug,
        "display_name": args.skill_name,
        "job": args.job.strip(),
        "template": args.template or "standard",
        "input_description": args.input_description or "描述接受的输入及缺失字段。",
        "output_format": args.output_format or "按契约返回简洁 Markdown。",
        "workflow_steps": args.workflow_step or [],
        "exclusions": args.exclude or [],
        "quality_standards": "\n".join(f"- {item}" for item in args.quality_check) or "检查完整性、正确性和请求的格式。",
        "root_problem": args.root_problem or "",
        "root_confirmed": args.root_confirmed,
        "target_user": args.target_user or "",
        "trigger_examples": args.trigger,
        "near_neighbors": args.near_neighbor,
        "success_signals": args.success_signal,
        "author": args.author,
        "architecture": args.architecture or "",
        "agents": args.agents or "",
        "configuration": args.configuration or "无用户可选配置。",
    }


def build_description(data):
    exclusions = "; ".join(data.get("exclusions", []))
    description = f"{data['job']}。当用户要求重复执行这项工作时使用。"
    if exclusions:
        description += f"不要用于：{exclusions}。"
    return " ".join(description.split())[:1024]


def create_package(skill_data, output_dir):
    skill_data = dict(skill_data)
    for source, destination in (("recurring_job", "job"), ("inputs", "input_description"), ("outputs", "output_format"), ("boundaries", "exclusions"), ("triggers", "trigger_examples")):
        if skill_data.get(source):
            value = skill_data[source]
            skill_data[destination] = "\n".join(str(item) for item in value) if isinstance(value, list) and destination in {"input_description", "output_format"} else value
    skill_data.setdefault("template", "standard")
    if not str(skill_data.get("job", "")).strip():
        raise ValueError("skill 的重复任务不能为空。")
    if skill_data.get("template") == "advanced" and not all(
        str(skill_data.get(key, "")).strip() for key in ("architecture", "agents")
    ):
        raise ValueError("advanced 模板需要组件说明和明确的角色/委派决定。")
    intent = build_intent_model(skill_data)
    skill_data["_intent_model"] = intent
    if not skill_data.get("root_problem"):
        skill_data["root_problem"] = intent["root_problem"]
    if not skill_data.get("target_user"):
        skill_data["target_user"] = intent["target_user"]
    if not skill_data.get("trigger_examples"):
        skill_data["trigger_examples"] = intent["triggers"]
    if not skill_data.get("near_neighbors"):
        skill_data["near_neighbors"] = intent["near_neighbors"]
    if not skill_data.get("success_signals"):
        skill_data["success_signals"] = intent["success_signals"]
    if not skill_data.get("design_pattern"):
        skill_data["design_pattern"] = intent["design_pattern"]
    if not skill_data.get("composition"):
        skill_data["composition"] = intent["composition"]
    skill_data["description"] = build_description(skill_data)
    body = generate_skill(skill_data, skill_data["template"])
    content = generate_frontmatter(skill_data) + body
    output_path = Path(output_dir).expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path = output_path.resolve()

    source_root = Path(__file__).resolve().parent.parent
    if is_within(output_path, source_root):
        raise ValueError("Refusing to create a skill inside the ye-skill-forge source directory.")
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing target: {output_path}")

    paths = save_skill(
        content,
        generate_manifest(skill_data),
        output_path,
        interface=generate_interface(skill_data),
        trigger_cases={"positive": intent["triggers"], "negative": intent["near_neighbors"], "near_neighbor": intent["near_neighbors"]} if intent["triggers"] or intent["near_neighbors"] else None,
    )
    findings = validate_skill(output_path)
    errors = [item for item in findings if item["severity"] == "error"]
    if errors:
        detail = "; ".join(item["message"] for item in errors)
        raise ValueError(f"Generated package failed validation: {detail}")
    return paths, findings


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_name", help="Human-readable skill name")
    parser.add_argument("--slug", help="Lowercase folder/frontmatter name; required for non-Latin-only names")
    parser.add_argument("--output", help="New output directory; defaults to ./<slug>")
    parser.add_argument("--template", choices=("minimal", "standard", "advanced"))
    parser.add_argument("--job", help="Recurring job; when provided, use non-interactive mode")
    parser.add_argument("--input-description")
    parser.add_argument("--output-format")
    parser.add_argument("--workflow-step", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--quality-check", action="append", default=[])
    parser.add_argument("--root-problem")
    parser.add_argument("--root-confirmed", action="store_true", help="已有用户证据确认根问题")
    parser.add_argument("--target-user")
    parser.add_argument("--trigger", action="append", default=[])
    parser.add_argument("--near-neighbor", action="append", default=[])
    parser.add_argument("--success-signal", action="append", default=[])
    parser.add_argument("--architecture", help="Required for the advanced template")
    parser.add_argument("--agents", help="Required for the advanced template; state roles or why delegation is not used")
    parser.add_argument("--configuration", help="User choices that materially change behavior")
    parser.add_argument("--author", default="Unspecified")
    args = parser.parse_args()

    try:
        slug = slug_for(args.skill_name, args.slug)
        if args.job:
            brief = collect_argument_brief(args, slug)
        else:
            brief = collect_interactive_brief(args.skill_name, slug)
            if args.template:
                brief["template"] = args.template
            brief["author"] = args.author
        output_dir = args.output or slug
        paths, findings = create_package(brief, output_dir)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print("Skill package created and structurally validated:")
    for path in paths:
        print(f"- {path}")
    print(f"- {Path(paths[0]).parent / 'agents' / 'interface.yaml'}")
    for finding in findings:
        if finding["severity"] == "warning":
            print(f"[WARNING] {finding['message']}")
    print("Run scripts/evaluate.py for the static checklist; semantic behavior still needs sample runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
