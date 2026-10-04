"""Build discoverable Skill artifacts without installing or scheduling them."""

import json
from pathlib import Path
import re

import yaml

from core.package import local_path, read_skill_manifest, validate_package
from core.skill_utils import NAME_PATTERN, load_skill, validate_skill


TARGET_ALIASES = {"openai": "codex", "claude": "claude-code", "agent-skills-compatible": "generic", "vscode": "generic"}
TARGETS = ("codex", "claude-code", "generic", *TARGET_ALIASES)
PACKAGE_TYPES = ("skill-package", "skill-family")


def _read_yaml_object(path):
    if not path.is_file():
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML metadata: {path}") from exc
    return value if isinstance(value, dict) else {}


def _relocate_asset(value, source_root, package_root):
    """Rebase a relative asset path when Router metadata becomes package metadata."""
    if not isinstance(value, str) or not value.strip() or value.startswith(("data:", "http://", "https://", "#")):
        return value
    candidate = Path(value.replace("\\", "/"))
    if candidate.is_absolute():
        return value
    resolved = (source_root / candidate).resolve()
    try:
        relative = resolved.relative_to(package_root.resolve())
    except ValueError:
        return value
    return relative.as_posix() if resolved.is_file() else value


def adapt_target(root, target):
    root = Path(root).resolve()
    platform = TARGET_ALIASES.get(target, target)
    if platform not in {"codex", "claude-code", "generic"}:
        raise ValueError(f"Unknown target: {target}")
    generated = []
    package_manifest = read_skill_manifest(root)
    package = package_manifest.get("package_type") in PACKAGE_TYPES
    entry_root = root
    children = []
    generated_root_entry = False
    if package:
        validation = validate_package(root)
        if not validation["ok"]:
            raise ValueError("Cannot adapt an invalid Skill package")
        children = [{"name": item["name"], "path": item["path"]} for item in validation["children"]]
        entry_root = local_path(root, validation["router"])
        if not (root / "SKILL.md").exists():
            metadata = load_skill(entry_root)[2]
            package_name = validation["manifest"].get("name")
            if not isinstance(package_name, str) or len(package_name) > 64 or not NAME_PATTERN.fullmatch(package_name):
                raise ValueError("Package adaptation requires a valid package name")
            header = yaml.safe_dump({"name": package_name, "description": metadata["description"]}, allow_unicode=True, sort_keys=False)
            router_file = entry_root.relative_to(root).as_posix() + "/SKILL.md"
            body = (
                "# Skill package entry\n\n"
                f"Read [{metadata['name']}]({router_file}) and follow its routing and handoff rules.\n"
                "Resolve each resource path relative to the file that declares it.\n"
                "The host Agent reads the selected child SKILL.md and performs that stage.\n"
                "One Agent can complete the whole plan sequentially; native Skill invocation or delegation is optional.\n"
                "Check each stage's required output before continuing. Stop dependent stages when their input is unavailable.\n"
                "Keep the whole directory together. Child discovery by the client is not assumed.\n"
            )
            (root / "SKILL.md").write_text(f"---\n{header}---\n\n{body}", encoding="utf-8", newline="\n")
            generated.append("SKILL.md")
            generated_root_entry = True
    metadata = load_skill(root)[2]
    if any(item["severity"] == "error" for item in validate_skill(root)):
        raise ValueError("Adapted entry does not pass structural validation")
    name = metadata["name"]
    config_root = root if (root / "agents/interface.yaml").is_file() or not package else entry_root
    config = _read_yaml_object(config_root / "agents/interface.yaml")
    compatibility = config.get("compatibility", {})
    execution = compatibility.get("execution", {}) if isinstance(compatibility, dict) else {}
    if package and config_root != entry_root and (not isinstance(execution, dict) or "shell" not in execution):
        router_config = _read_yaml_object(entry_root / "agents/interface.yaml")
        router_compatibility = router_config.get("compatibility", {})
        execution = router_compatibility.get("execution", {}) if isinstance(router_compatibility, dict) else {}
    shell = execution.get("shell", "environment") if isinstance(execution, dict) else "environment"
    if platform == "codex" and not (root / "agents/openai.yaml").exists():
        # Preserve an existing root native file byte-for-byte. Only parse the
        # Router native metadata when generating a missing root file.
        native_source_root = entry_root
        native_source = _read_yaml_object(entry_root / "agents/openai.yaml")
        interface = config.get("interface")
        interface_source_root = config_root
        if not isinstance(interface, dict):
            interface = native_source.get("interface")
            interface_source_root = native_source_root
        if not isinstance(interface, dict):
            interface = {
                "display_name": name,
                "short_description": metadata["description"][:64],
                "default_prompt": f"Use ${name} to complete the requested task.",
            }
        else:
            interface = dict(interface)
            interface["short_description"] = str(interface.get("short_description") or metadata["description"])[:64]
            if not re.search(r"\$" + re.escape(name) + r"(?![a-z0-9-])", str(interface.get("default_prompt", ""))):
                interface["default_prompt"] = f"Use ${name} to complete the requested task."
        short = str(interface.get("short_description") or metadata["description"])
        if len(short) < 25:
            short = f"Reusable Skill for {name}: {short}"
        native_interface = {
            "display_name": str(interface.get("display_name") or name),
            "short_description": short[:64],
            "default_prompt": str(interface["default_prompt"]),
        }
        native_output = dict(native_source)
        native_interface_source = native_source.get("interface") if isinstance(native_source.get("interface"), dict) else {}
        for key in ("icon_small", "icon_large", "brand_color"):
            if isinstance(interface.get(key), str) and interface[key]:
                native_interface[key] = _relocate_asset(interface[key], interface_source_root, root) if interface_source_root != root and key != "brand_color" else interface[key]
            elif isinstance(native_interface_source.get(key), str) and native_interface_source[key]:
                native_interface[key] = _relocate_asset(native_interface_source[key], native_source_root, root) if native_source_root != root and key != "brand_color" else native_interface_source[key]
        native_output["interface"] = native_interface
        (root / "agents").mkdir(exist_ok=True)
        remaining = {key: value for key, value in native_output.items() if key != "interface"}
        content = "interface:\n" + "".join(f"  {key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in native_interface.items())
        if remaining:
            content += yaml.safe_dump(remaining, allow_unicode=True, sort_keys=False)
        (root / "agents/openai.yaml").write_text(content, encoding="utf-8", newline="\n")
        generated.append("agents/openai.yaml")
    install = {
        "codex": f".agents/skills/{name}",
        "claude-code": f".claude/skills/{name}",
        "generic": f"<client-skill-directory>/{name}",
    }[platform]
    return {
        "platform": platform,
        "capability": "discoverable-entry-and-install-plan",
        "entry": "SKILL.md",
        "entry_name": name,
        "generated_files": generated,
        "installation": {"suggested_project_path": install, "action": "copy-whole-directory", "verify_client_discovery": True},
        "execution": {"owner": "host-agent", "default": "sequential", "scheduler_included": False, "shell": shell},
        "children": children,
        "child_discovery_required": None if package and not generated_root_entry else False,
        "independent_child_invocation": "requires-client-registration-and-resource-path-verification" if children else "not-applicable",
        "runtime_behavior_verified": False,
        "limitations": "Installation paths must be checked in the client. Metadata and artifact validation do not prove native discovery, routing, permissions or task quality.",
    }
