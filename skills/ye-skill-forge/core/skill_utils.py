"""Shared parsing and validation helpers for skill packages."""

import json
import re
from pathlib import Path

import yaml


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_PATTERN = re.compile(
    r"\A---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)
PLACEHOLDER_PATTERN = re.compile(
    r"\{(?:skill_name|job_description|workflow_steps|input_description|"
    r"output_format(?:_example)?|output_example|exclusions|quality_standards|"
    r"references|architecture_description|agent_definitions|"
    r"configuration_options|root_problem|target_user|trigger_examples|"
    r"near_neighbors|success_signals|composition_contract)\}"
)
SCAFFOLD_MARKERS = (
    "待作者明确",
    "待从真实材料",
    "有代表性的输出示例。",
    "只在引用能解决真实歧义时加入。",
)


def resolve_skill_dir(skill_path):
    path = Path(skill_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Skill directory not found: {path}")
    return path


def load_skill(skill_path):
    root = resolve_skill_dir(skill_path)
    skill_file = root / "SKILL.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"SKILL.md not found in {root}")

    text = skill_file.read_text(encoding="utf-8-sig")
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        raise ValueError("SKILL.md must start with a YAML frontmatter block")

    metadata = yaml.safe_load(match.group("yaml"))
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    return root, skill_file, metadata, match.group("yaml"), text[match.end():]


def validate_skill(skill_path):
    findings = []

    def add(severity, code, message):
        findings.append({"severity": severity, "code": code, "message": message})

    try:
        root, skill_file, metadata, _frontmatter, body = load_skill(skill_path)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        add("error", "skill-file", str(exc))
        return findings

    name = metadata.get("name")
    if not isinstance(name, str) or len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        add("error", "name", "Frontmatter name must be 1-64 lowercase letters or digits separated by single hyphens.")

    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        add("error", "description", "Frontmatter description must be a non-empty string.")
    elif len(description.strip()) < 20:
        add("warning", "description-short", "Description is very short; clarify the job and when to use this skill.")
    elif len(description) > 1024:
        add("warning", "description-long", "Description exceeds 1024 characters and may be difficult to route reliably.")

    if not body.strip():
        add("error", "empty-body", "SKILL.md has no instructions after frontmatter.")
    if PLACEHOLDER_PATTERN.search(body):
        add("error", "unfilled-template", "SKILL.md still contains an unfilled template placeholder.")
    scaffold_hits = [marker for marker in SCAFFOLD_MARKERS if marker in body]
    if scaffold_hits:
        add("warning", "scaffold-content", "Generated scaffold still contains generic guidance; replace it with the target domain method before calling the Skill complete.")

    estimated_tokens = max(1, len(skill_file.read_text(encoding="utf-8-sig")) // 4)
    if estimated_tokens > 6000:
        add("warning", "large-entrypoint", f"SKILL.md is about {estimated_tokens} tokens; move deferred detail into references.")

    manifest_file = root / "manifest.json"
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            add("error", "manifest-json", f"manifest.json is not valid JSON: {exc}")
        else:
            if not isinstance(manifest, dict):
                add("error", "manifest-shape", "manifest.json must contain a JSON object.")
            elif name and manifest.get("name") != name:
                add("error", "manifest-name", "manifest.json name must match SKILL.md frontmatter.")
            elif not manifest.get("version"):
                add("warning", "manifest-version", "manifest.json has no version.")
            if isinstance(manifest, dict) and "design" in manifest:
                design = manifest["design"]
                if not isinstance(design, dict):
                    add("error", "design-shape", "manifest.design must be an object.")
                else:
                    if design.get("root_confirmed") is not True:
                        add("warning", "intent-unconfirmed", "Root problem is provisional; this is an authoring scaffold, not a confirmed design.")
                    for field in ("root_problem", "target_user", "triggers", "near_neighbors", "success_signals"):
                        if not design.get(field):
                            add("warning", "design-missing", f"manifest.design.{field} lacks concrete design evidence.")

    interface_file = root / "agents" / "interface.yaml"
    if interface_file.exists():
        try:
            interface = yaml.safe_load(interface_file.read_text(encoding="utf-8-sig"))
        except (OSError, yaml.YAMLError) as exc:
            add("error", "interface-yaml", f"agents/interface.yaml is not valid YAML: {exc}")
        else:
            if not isinstance(interface, dict) or not isinstance(interface.get("interface"), dict):
                add("error", "interface-shape", "agents/interface.yaml must contain an interface mapping.")
            else:
                interface_fields = interface["interface"]
                for field in ("display_name", "short_description", "default_prompt"):
                    if not interface_fields.get(field):
                        add("error", "interface-field", f"agents/interface.yaml is missing interface.{field}.")

                compatibility = interface.get("compatibility")
                if compatibility is not None:
                    if not isinstance(compatibility, dict):
                        add("error", "compatibility-shape", "compatibility must be a mapping.")
                        compatibility = {}
                    if not compatibility.get("canonical_format"):
                        add("error", "compatibility-format", "compatibility.canonical_format is required when compatibility metadata is present.")
                    targets = compatibility.get("adapter_targets")
                    if not isinstance(targets, list) or not targets or any(not isinstance(item, str) or not item.strip() for item in targets):
                        add("error", "compatibility-targets", "compatibility.adapter_targets must be a non-empty list.")
                        targets = []
                    activation = compatibility.get("activation")
                    if not isinstance(activation, dict) or not activation.get("mode"):
                        add("error", "compatibility-activation", "compatibility.activation.mode is required.")
                    execution = compatibility.get("execution", {})
                    if not isinstance(execution, dict):
                        execution = {}
                    if execution.get("context") not in {"inline", "fork"}:
                        add("error", "compatibility-context", "compatibility.execution.context must be inline or fork.")
                    if execution.get("shell") not in {"bash", "powershell"}:
                        add("error", "compatibility-shell", "compatibility.execution.shell must be bash or powershell.")
                    trust = compatibility.get("trust", {})
                    if not isinstance(trust, dict):
                        trust = {}
                    if trust.get("source_tier") not in {"local", "managed", "plugin", "remote"}:
                        add("error", "compatibility-source", "compatibility.trust.source_tier is invalid or missing.")
                    if trust.get("remote_inline_execution") not in {"forbid", "allow"}:
                        add("error", "compatibility-inline-execution", "compatibility.trust.remote_inline_execution must be forbid or allow.")
                    if not trust.get("remote_metadata_policy"):
                        add("error", "compatibility-metadata-policy", "compatibility.trust.remote_metadata_policy is required.")
                    degradation = compatibility.get("degradation", {})
                    if not isinstance(degradation, dict):
                        degradation = {}
                    for target in targets:
                        if target not in degradation:
                            add("error", "compatibility-degradation", f"No degradation strategy is declared for {target}.")

    if not any(item["severity"] == "error" for item in findings):
        add("info", "valid", f"Skill structure is valid: {skill_file}")
    return findings


def is_within(path, parent):
    """Return whether a resolved path is equal to or below another path."""
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False
