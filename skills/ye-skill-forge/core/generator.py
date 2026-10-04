"""Render and safely persist Agent Skills-compatible packages."""

import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.skill_utils import NAME_PATTERN


def load_template(template_name):
    if template_name not in {"minimal", "standard", "advanced"}:
        raise ValueError(f"Unknown template: {template_name}")
    template_path = Path(__file__).parent.parent / "templates" / f"{template_name}.md"
    return template_path.read_text(encoding="utf-8")


def generate_skill(skill_data, template_type="standard"):
    template = load_template(template_type)
    workflow_steps = skill_data.get("workflow_steps", [])
    if isinstance(workflow_steps, list):
        workflow_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(workflow_steps))
    else:
        workflow_text = str(workflow_steps)

    exclusions = skill_data.get("exclusions", [])
    if isinstance(exclusions, list):
        exclusions_text = "\n".join(f"- {item}" for item in exclusions)
    else:
        exclusions_text = str(exclusions)

    def as_lines(value, fallback):
        if isinstance(value, list):
            text = "\n".join(f"- {item}" for item in value if str(item).strip())
        else:
            text = str(value or "")
        return text.strip() or fallback

    def as_materials(value, fallback):
        return as_lines(value, fallback)

    values = {
        "{skill_name}": skill_data.get("display_name") or skill_data.get("name", "New Skill"),
        "{job_description}": skill_data.get("job", ""),
        "{workflow_steps}": workflow_text or "1. 读取全部输入\n2. 执行工作流\n3. 按契约检查输出",
        "{input_description}": skill_data.get("input_description") or "待作者明确接受的输入及缺失字段处理（骨架）。",
        "{output_format}": skill_data.get("output_format") or "待作者明确输出契约（骨架）。",
        "{output_format_example}": skill_data.get("output_format_example", "text"),
        "{output_example}": skill_data.get("output_example", "有代表性的输出示例。"),
        "{exclusions}": exclusions_text or "- 不处理职责之外的请求",
        "{quality_standards}": skill_data.get("quality_standards") or "待作者明确可检查的成功条件（骨架）。",
        "{references}": skill_data.get("references", "只在引用能解决真实歧义时加入。"),
        "{architecture_description}": skill_data.get("architecture", "只有工作流确实需要时才拆分组件。"),
        "{agent_definitions}": skill_data.get("agents", "除非独立工作能带来收益，否则使用单一角色。"),
        "{configuration_options}": skill_data.get("configuration", "只记录会改变行为的用户选项。"),
        "{root_problem}": skill_data.get("root_problem") or skill_data.get("job", "解决一个可重复的问题。"),
        "{target_user}": skill_data.get("target_user") or "待明确；不影响低风险骨架生成。",
        "{user_result}": skill_data.get("user_result") or skill_data.get("output_format") or "待明确用户最终要得到的结果。",
        "{reusable_method}": skill_data.get("reusable_method") or "待从真实材料、成功做法或规范中提炼。",
        "{materials}": as_materials(skill_data.get("materials"), "正常工作所需的用户材料和已确认参考"),
        "{tools}": as_materials(skill_data.get("tools"), "仅使用完成结果所需的确定性工具"),
        "{permissions}": as_materials(skill_data.get("permissions"), "按用户授权和外部动作边界执行"),
        "{trigger_examples}": as_lines(skill_data.get("trigger_examples"), "- 用户明确提出该重复任务"),
        "{near_neighbors}": as_lines(skill_data.get("near_neighbors"), "- 与本任务相邻但属于其他职责的请求"),
        "{success_signals}": as_lines(skill_data.get("success_signals") or skill_data.get("quality_standards"), "- 输出满足契约并保留可核查依据"),
        "{composition_contract}": skill_data.get("composition_contract", "单一 Skill 直接完成工作；需要拆分时先定义 Router 和交接契约。"),
    }
    for placeholder, value in values.items():
        template = template.replace(placeholder, str(value).strip())

    if re.search(r"\{[a-z_]+\}", template):
        raise ValueError("Template contains an unresolved placeholder")
    return template.strip() + "\n"


def generate_frontmatter(skill_data):
    name = skill_data.get("name", "")
    if len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        raise ValueError("Skill name must be 1-64 lowercase letters or digits separated by single hyphens")
    description = " ".join(str(skill_data.get("description", "")).split())
    if not description:
        raise ValueError("A non-empty skill description is required")
    author = str(skill_data.get("author", "Unspecified")).strip() or "Unspecified"
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "metadata:\n"
        f"  author: {json.dumps(author, ensure_ascii=False)}\n"
        "  version: \"1.0.0\"\n"
        "---\n\n"
    )


def generate_manifest(skill_data):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    intent_model = skill_data.get("_intent_model") if isinstance(skill_data.get("_intent_model"), dict) else {}

    def design_list(value):
        if isinstance(value, (list, tuple)):
            return list(value)
        if value is None or not str(value).strip():
            return []
        return [str(value).strip()]

    inputs = design_list(skill_data.get("inputs") or intent_model.get("inputs") or skill_data.get("input_description"))
    outputs = design_list(skill_data.get("outputs") or intent_model.get("outputs") or skill_data.get("output_format"))
    return {
        "schema_version": "2.0",
        "name": skill_data.get("name", ""),
        "version": "1.0.0",
        "description": " ".join(str(skill_data.get("description", "")).split()),
        "owner": str(skill_data.get("owner") or skill_data.get("author") or "Unspecified"),
        "updated_at": now,
        "status": "draft",
        "maturity_tier": skill_data.get("maturity_tier", "scaffold"),
        "lifecycle_stage": "authoring",
        "review_cadence": "as-needed",
        "license": skill_data.get("license", ""),
        "created_by": "ye-skill-forge",
        "template": skill_data.get("template", "standard"),
        "target_format": "agent-skills-compatible",
        "target_platforms": ["codex", "claude-code", "generic"],
        "capabilities": skill_data.get("capabilities", []),
        "design": {
            "root_problem": skill_data.get("root_problem") or skill_data.get("job", ""),
            "user_result": skill_data.get("user_result") or skill_data.get("desired_result") or skill_data.get("output_format", ""),
            "target_user": skill_data.get("target_user", ""),
            "recurring_job": skill_data.get("recurring_job") or skill_data.get("job", ""),
            "inputs": inputs,
            "outputs": outputs,
            "boundaries": skill_data.get("boundaries") or skill_data.get("exclusions", []),
            "reusable_method": skill_data.get("reusable_method") or skill_data.get("known_good_method", ""),
            "materials": skill_data.get("materials", []),
            "tools": skill_data.get("tools", []),
            "permissions": skill_data.get("permissions", []),
            "evidence": skill_data.get("evidence", []),
            "triggers": skill_data.get("trigger_examples", []),
            "near_neighbors": skill_data.get("near_neighbors", []),
            "success_signals": skill_data.get("success_signals", []),
            "constraints": skill_data.get("constraints", []),
            "tension": skill_data.get("tension", ""),
            "pattern": skill_data.get("design_pattern", "single-procedural-skill"),
            "composition": skill_data.get("composition", {}),
            "root_confirmed": bool(intent_model.get("root_confirmed", skill_data.get("root_confirmed", False))),
            "assumptions": intent_model.get("assumptions", []),
            "missing": intent_model.get("missing", []),
            "readiness": intent_model.get("readiness"),
            "next_action": intent_model.get("next_action", "clarify"),
        },
    }


def generate_interface(skill_data):
    display_name = str(skill_data.get("display_name") or skill_data.get("name", "New Skill"))
    job = " ".join(str(skill_data.get("job", "完成所述任务")).split())
    return {
        "compatibility": {
            "canonical_format": "agent-skills",
            "adapter_targets": ["codex", "claude-code", "generic"],
            "activation": {"mode": "manual", "paths": []},
            "execution": {"context": "inline", "shell": skill_data.get("shell", "environment")},
            "trust": {
                "source_tier": "local",
                "remote_inline_execution": "forbid",
                "remote_metadata_policy": "allow-metadata-only",
            },
            "degradation": {
                "codex": "完整 Skill 目录和可选 openai.yaml；安装与行为需客户端复测",
                "claude-code": "完整 Skill 目录；由宿主 Agent 顺序读取资源，原生调用需复测",
                "generic": "完整中立源格式；按实际文件读写与脚本能力降级，不依赖子 Agent",
            },
        },
        "interface": {
            "display_name": display_name,
            "short_description": job[:80] or "完成所述任务",
            "default_prompt": f"使用 ${skill_data.get('name', 'skill')} {job.rstrip('。.')}。",
        }
    }


def save_skill(skill_content, manifest, output_dir, interface=None, trigger_cases=None):
    """Create a new package atomically; never overwrite an existing target."""
    output_path = Path(output_dir).expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path = output_path.resolve()
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing target: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_path.name}-", dir=output_path.parent))
    try:
        with (staging / "SKILL.md").open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(skill_content)
        manifest = dict(manifest)
        manifest.setdefault("created_at", datetime.now(timezone.utc).replace(microsecond=0).isoformat())
        with (staging / "manifest.json").open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        if interface is not None:
            agents_dir = staging / "agents"
            agents_dir.mkdir()
            with (agents_dir / "interface.yaml").open("w", encoding="utf-8", newline="\n") as stream:
                yaml.safe_dump(interface, stream, allow_unicode=True, sort_keys=False)
        if trigger_cases:
            (staging / "evals").mkdir()
            with (staging / "evals" / "trigger_cases.json").open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(trigger_cases, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
        staging.rename(output_path)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return str(output_path / "SKILL.md"), str(output_path / "manifest.json")
