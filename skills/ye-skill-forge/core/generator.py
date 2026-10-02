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

    values = {
        "{skill_name}": skill_data.get("display_name") or skill_data.get("name", "New Skill"),
        "{job_description}": skill_data.get("job", ""),
        "{workflow_steps}": workflow_text or "1. 读取全部输入\n2. 执行工作流\n3. 按契约检查输出",
        "{input_description}": skill_data.get("input_description", "说明接受的输入及缺失字段。"),
        "{output_format}": skill_data.get("output_format", "按契约返回简洁 Markdown。"),
        "{output_format_example}": skill_data.get("output_format_example", "text"),
        "{output_example}": skill_data.get("output_example", "有代表性的输出示例。"),
        "{exclusions}": exclusions_text or "- 不处理职责之外的请求",
        "{quality_standards}": skill_data.get("quality_standards", "检查完整性、正确性和请求的格式。"),
        "{references}": skill_data.get("references", "只在引用能解决真实歧义时加入。"),
        "{architecture_description}": skill_data.get("architecture", "只有工作流确实需要时才拆分组件。"),
        "{agent_definitions}": skill_data.get("agents", "除非独立工作能带来收益，否则使用单一角色。"),
        "{configuration_options}": skill_data.get("configuration", "只记录会改变行为的用户选项。"),
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
    return {
        "name": skill_data.get("name", ""),
        "version": "1.0.0",
        "description": " ".join(str(skill_data.get("description", "")).split()),
        "owner": str(skill_data.get("owner") or skill_data.get("author") or "Unspecified"),
        "updated_at": now,
        "status": "draft",
        "maturity_tier": skill_data.get("maturity_tier", "scaffold"),
        "lifecycle_stage": "authoring",
        "review_cadence": "as-needed",
        "license": "MIT",
        "created_by": "ye-skill-forge",
        "template": skill_data.get("template", "standard"),
        "target_format": "agent-skills-compatible",
        "target_platforms": ["openai", "claude", "generic", "agent-skills-compatible", "vscode"],
        "capabilities": ["create-skill", "validate-skill", "evaluate-skill", "improve-skill"],
    }


def generate_interface(skill_data):
    display_name = str(skill_data.get("display_name") or skill_data.get("name", "New Skill"))
    job = " ".join(str(skill_data.get("job", "完成所述任务")).split())
    return {
        "compatibility": {
            "canonical_format": "agent-skills",
            "adapter_targets": ["openai", "claude", "generic", "agent-skills-compatible", "vscode"],
            "activation": {"mode": "manual", "paths": []},
            "execution": {"context": "inline", "shell": "powershell"},
            "trust": {
                "source_tier": "local",
                "remote_inline_execution": "forbid",
                "remote_metadata_policy": "allow-metadata-only",
            },
            "degradation": {
                "openai": "源格式加适配元数据；目标客户端行为需复测",
                "claude": "源格式加适配元数据；目标客户端行为需复测",
                "generic": "中立源格式",
                "agent-skills-compatible": "中立源格式；运行时效果需独立验证",
                "vscode": "源格式加 VS Code 说明；目标客户端行为需复测",
            },
        },
        "interface": {
            "display_name": display_name,
            "short_description": job[:80] or "完成所述任务",
            "default_prompt": f"使用 ${skill_data.get('name', 'skill')} {job.rstrip('。.')}。",
        }
    }


def save_skill(skill_content, manifest, output_dir, interface=None):
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
        staging.rename(output_path)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return str(output_path / "SKILL.md"), str(output_path / "manifest.json")
