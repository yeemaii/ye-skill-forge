"""Ye 的轻量生命周期能力：IR、信任、交付、运营和组合审查。"""

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.skill_utils import load_skill, validate_skill


TARGETS = ("openai", "claude", "generic", "agent-skills-compatible", "vscode")
GENERATED_DIRS = {"reports", "dist", ".git", "__pycache__", ".yao", ".codex", ".ye"}
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
CAPABILITY_PATTERNS = {
    "subprocess": re.compile(r"\b(?:subprocess|os\.system|os\.popen)\b"),
    "network": re.compile(r"\b(?:requests|urllib|httpx|socket)\b|https?://"),
    "file_write": re.compile(r"\.(?:write_text|write_bytes)|\bopen\([^\n]+['\"]w"),
    "interactive": re.compile(r"\b(?:input|prompt_toolkit)\s*\("),
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def write_report(root, name, value, title="Ye 报告"):
    root = Path(root).resolve()
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_json(report_dir / f"{name}.json", value)
    lines = [f"# {title}", "", f"生成时间：{utc_now()}", ""]
    if isinstance(value, dict):
        if "ok" in value:
            lines.append(f"状态：{'通过' if value['ok'] else '需要处理'}")
        for key, item in value.items():
            if key in {"ok", "generated_at"}:
                continue
            if isinstance(item, (str, int, float, bool)) or item is None:
                lines.append(f"- {key}: {item}")
    lines.extend(["", "机器可读证据：" + json_path.name])
    (report_dir / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return value


def package_manifest(root):
    return read_json(Path(root) / "manifest.json", {}) or {}


def iter_source_files(root):
    root = Path(root).resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in GENERATED_DIRS or part.endswith(".pyc") for part in rel.parts):
            continue
        if rel.as_posix().startswith("reports/telemetry"):
            continue
        yield path, rel


def tree_sha256(root):
    digest = hashlib.sha256()
    entries = []
    for path, rel in iter_source_files(root):
        entries.append((rel.as_posix(), path))
    for rel_name, path in sorted(entries):
        digest.update(rel_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_skill_ir(root):
    root, skill_file, metadata, _frontmatter, body = load_skill(root)
    headings = [line.lstrip("#").strip() for line in body.splitlines() if line.startswith("#")]
    eval_files = [p.relative_to(root).as_posix() for p in (root / "evals").rglob("*") if p.is_file()] if (root / "evals").is_dir() else []
    scripts = [p.relative_to(root).as_posix() for p in (root / "scripts").glob("*.py")] if (root / "scripts").is_dir() else []
    manifest = package_manifest(root)
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "source": skill_file.relative_to(root).as_posix(),
        "identity": {"name": metadata.get("name"), "description": metadata.get("description", "")},
        "contract": {
            "headings": headings,
            "has_workflow": any("workflow" in h.lower() or "流程" in h or "生命周期" in h for h in headings),
            "has_input_output": any("input" in h.lower() or "output" in h.lower() or "输入" in h or "输出" in h for h in headings),
            "has_boundaries": any("bound" in h.lower() or "范围" in h or "边界" in h for h in headings),
        },
        "resources": {"scripts": scripts, "evals": eval_files},
        "risk": {
            "maturity_tier": manifest.get("maturity_tier", "scaffold"),
            "owner": manifest.get("owner"),
            "review_cadence": manifest.get("review_cadence"),
            "target_platforms": manifest.get("target_platforms", ["agent-skills-compatible"]),
        },
    }


def skill_ir(root):
    result = build_skill_ir(root)
    return write_report(root, "skill_ir", result, "Skill IR")


def trust_audit(root):
    root = Path(root).resolve()
    findings = []
    capabilities = set()
    scripts = []
    for path in sorted((root / "scripts").rglob("*.py")) if (root / "scripts").is_dir() else []:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        rel = path.relative_to(root).as_posix()
        file_caps = [name for name, pattern in CAPABILITY_PATTERNS.items() if pattern.search(text)]
        capabilities.update(file_caps)
        scripts.append({"path": rel, "capabilities": file_caps, "argparse": "argparse" in text})
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append({"severity": "block", "code": "secret-pattern", "path": rel, "message": "发现疑似秘密或私钥模式"})
        if "argparse" not in text and "SCRIPT_INTERFACE = \"internal-module\"" not in text:
            findings.append({"severity": "warn", "code": "help-surface", "path": rel, "message": "脚本未声明 argparse 或 internal-module 接口"})
    for path, rel in iter_source_files(root):
        if rel.name == "requirements.txt":
            for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                if line.strip() and not line.lstrip().startswith("#") and "==" not in line:
                    findings.append({"severity": "warn", "code": "unpinned-dependency", "path": rel.as_posix(), "message": line.strip()})
    permission_policy = read_json(root / "security" / "permission_policy.json", None)
    if capabilities and not permission_policy:
        findings.append({"severity": "warn", "code": "permission-policy", "path": "security/permission_policy.json", "message": "脚本声明了高权限能力但缺少权限策略"})
    return write_report(root, "security_trust", {
        "ok": not any(item["severity"] == "block" for item in findings),
        "generated_at": utc_now(),
        "capabilities": sorted(capabilities),
        "scripts": scripts,
        "permission_policy_present": bool(permission_policy),
        "findings": findings,
        "evidence_status": "static",
        "limitations": ["未证明目标客户端的原生权限执行", "未证明外部网络服务或真实客户端行为"],
    }, "信任与权限审计")


def trigger_eval(root):
    root = Path(root).resolve()
    files = []
    positives = negatives = near = 0
    for path in (root / "evals").rglob("*") if (root / "evals").is_dir() else []:
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        files.append(path.relative_to(root).as_posix())
        try:
            if path.suffix.lower() == ".jsonl":
                values = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            else:
                values = [json.loads(path.read_text(encoding="utf-8-sig"))]
        except (OSError, json.JSONDecodeError):
            continue
        for value in values:
            if isinstance(value, dict):
                positives += len(value.get("positive", value.get("should_trigger", [])) or [])
                negatives += len(value.get("negative", value.get("should_not_trigger", [])) or [])
                near += len(value.get("near_neighbor", value.get("near_neighbors", [])) or [])
    status = "pass" if positives and negatives else "missing"
    return write_report(root, "trigger_eval", {
        "ok": bool(positives and negatives),
        "status": status,
        "counts": {"positive": positives, "negative": negatives, "near_neighbor": near},
        "files": files,
        "metrics": {
            "trigger_recall": None,
            "trigger_precision": None,
            "negative_rejection_rate": None,
            "near_neighbor_confusions": None,
            "reason": "只发现静态案例，尚未执行模型或客户端路由；不能计算准确率。",
        },
        "evidence_status": "static;未执行模型路由",
    }, "触发评测")


def output_eval(root):
    root = Path(root).resolve()
    files = [p for p in (root / "evals").rglob("*") if p.is_file() and "output" in p.as_posix().lower()] if (root / "evals").is_dir() else []
    cases = 0
    for path in files:
        if path.suffix.lower() == ".jsonl":
            cases += sum(1 for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())
        elif path.suffix.lower() == ".json":
            value = read_json(path, {})
            cases += len(value) if isinstance(value, list) else len(value.get("cases", [])) if isinstance(value, dict) else 0
    return write_report(root, "output_eval", {"ok": cases > 0, "status": "present" if cases else "missing", "cases": cases, "files": [p.relative_to(root).as_posix() for p in files], "evidence_status": "static;未运行模型或人工盲审", "limitations": ["不能证明 with-skill 相对 baseline 的实际质量提升"]}, "输出评测")


def _safe_output_dir(root, output_dir):
    root = Path(root).resolve()
    output = Path(output_dir).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    if output == root:
        raise ValueError("输出目录不能等于 skill 源目录")
    return output


def compile_targets(root, output_dir=None, targets=None):
    root = Path(root).resolve()
    output = _safe_output_dir(root, output_dir or root / "dist" / "targets")
    targets = targets or ["generic"]
    invalid = sorted(set(targets) - set(TARGETS))
    if invalid:
        raise ValueError(f"未知目标: {', '.join(invalid)}")
    output.mkdir(parents=True, exist_ok=True)
    manifest = package_manifest(root)
    results = []
    for target in targets:
        target_dir = output / target
        target_dir.mkdir(parents=True, exist_ok=True)
        for rel in ("SKILL.md", "manifest.json"):
            source = root / rel
            if source.is_file():
                shutil.copy2(source, target_dir / rel)
        interface_source = root / "agents" / "interface.yaml"
        if interface_source.is_file():
            (target_dir / "agents").mkdir(exist_ok=True)
            shutil.copy2(interface_source, target_dir / "agents" / "interface.yaml")
        adapter = {
            "target": target,
            "source_sha256": tree_sha256(root),
            "capability": "source-plus-metadata",
            "runtime_behavior_verified": False,
            "limitations": "编译成功不等于目标客户端运行时兼容；需要目标客户端 smoke test",
        }
        write_json(target_dir / "adapter.json", adapter)
        results.append(adapter)
    report = {"ok": True, "output_dir": str(output), "targets": results, "manifest_name": manifest.get("name"), "evidence_status": "executed-structure"}
    return write_report(root, "compiled_targets", report, "目标编译")


def package_skill(root, output_dir=None, make_zip=True):
    root = Path(root).resolve()
    output = _safe_output_dir(root, output_dir or root / "dist")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{package_manifest(root).get('name', root.name)}.zip"
    if make_zip:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
            for path, rel in iter_source_files(root):
                if rel.as_posix().startswith("dist/"):
                    continue
                handle.write(path, rel.as_posix())
        with zipfile.ZipFile(archive) as check:
            for info in check.infolist():
                if info.filename.startswith("/") or ".." in Path(info.filename).parts:
                    raise ValueError(f"归档包含不安全路径: {info.filename}")
            entry_count = len(check.infolist())
    else:
        entry_count = 0
    result = {"ok": archive.is_file() if make_zip else True, "archive": str(archive) if make_zip else None, "source_sha256": tree_sha256(root), "entries": entry_count, "excluded": sorted(GENERATED_DIRS), "evidence_status": "executed-structure"}
    return write_report(root, "package_verification", result, "包校验")


def install_simulate(root, package_dir):
    root = Path(root).resolve()
    package_dir = Path(package_dir).expanduser().resolve()
    archives = sorted(package_dir.glob("*.zip")) if package_dir.is_dir() else [package_dir]
    if not archives:
        return write_report(root, "install_simulation", {"ok": False, "error": "未找到 zip 归档", "evidence_status": "missing"}, "安装模拟")
    archive = archives[0]
    with tempfile.TemporaryDirectory(prefix="ye-install-") as temp:
        temp_root = Path(temp).resolve()
        with zipfile.ZipFile(archive) as handle:
            for info in handle.infolist():
                target = (temp_root / info.filename).resolve()
                if target != temp_root and temp_root not in target.parents:
                    return write_report(root, "install_simulation", {"ok": False, "error": f"路径穿越: {info.filename}", "evidence_status": "executed"}, "安装模拟")
            handle.extractall(temp_root)
        candidates = [p.parent for p in temp_root.rglob("SKILL.md")]
        if not candidates:
            return write_report(root, "install_simulation", {"ok": False, "error": "归档缺少 SKILL.md", "evidence_status": "executed"}, "安装模拟")
        findings = validate_skill(candidates[0])
        result = {"ok": not any(item["severity"] == "error" for item in findings), "archive": str(archive), "extracted_skill": str(candidates[0]), "validation": findings, "evidence_status": "executed-temporary-install"}
    return write_report(root, "install_simulation", result, "安装模拟")


def _version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value or ""))
    return tuple(int(item) for item in match.groups()) if match else None


def upgrade_check(root, previous):
    root = Path(root).resolve()
    current = package_manifest(root)
    previous_data = read_json(previous, {}) if Path(previous).is_file() else package_manifest(previous)
    old = _version(previous_data.get("version"))
    new = _version(current.get("version"))
    issues = []
    if not old or not new:
        issues.append("当前或上一版本不是有效 semver")
    elif new <= old:
        issues.append("当前版本没有高于上一版本")
    old_targets = set(previous_data.get("target_platforms", []))
    new_targets = set(current.get("target_platforms", []))
    if old_targets - new_targets and new and old and new[0] == old[0]:
        issues.append("删除目标平台应至少提升 major 版本")
    result = {"ok": not issues, "current": current.get("version"), "previous": previous_data.get("version"), "recommended": "major" if old and new and (old_targets - new_targets) else "patch-or-minor", "issues": issues, "migration_required": bool(issues or old_targets != new_targets), "evidence_status": "static-metadata"}
    return write_report(root, "upgrade_check", result, "升级检查")


def registry_audit(root):
    root = Path(root).resolve()
    manifest = package_manifest(root)
    required = ("name", "version", "owner", "license", "review_cadence")
    missing = [field for field in required if not manifest.get(field)]
    result = {"ok": not missing, "missing": missing, "name": manifest.get("name"), "version": manifest.get("version"), "owner": manifest.get("owner"), "license": manifest.get("license"), "review_cadence": manifest.get("review_cadence"), "source_sha256": tree_sha256(root), "evidence_status": "executed-source-audit"}
    return write_report(root, "registry_audit", result, "注册审计")


def telemetry_event(root, event, outcome="unknown", failure_type="none", command="manual"):
    root = Path(root).resolve()
    allowed_events = {"skill_activation", "skill_output", "script_run", "review_event"}
    allowed_outcomes = {"accepted", "edited", "rejected", "missed", "failed", "reviewed", "unknown"}
    allowed_failures = {"wrong_trigger", "under_trigger", "bad_output", "missing_resource", "script_error", "review_overdue", "none"}
    if event not in allowed_events or outcome not in allowed_outcomes or failure_type not in allowed_failures:
        raise ValueError("遥测事件、结果或失败类型不在允许集合中")
    event_path = root / ".ye" / "telemetry_events.jsonl"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    item = {"event": event, "skill": package_manifest(root).get("name", root.name), "version": package_manifest(root).get("version", ""), "source": "manual", "command": command, "outcome": outcome, "failure_type": failure_type, "timestamp": utc_now()}
    with event_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"ok": True, "event_path": str(event_path), "recorded_fields": sorted(item), "privacy": "metadata-only"}


def drift_report(root):
    root = Path(root).resolve()
    event_path = root / ".ye" / "telemetry_events.jsonl"
    events = []
    if event_path.is_file():
        for line in event_path.read_text(encoding="utf-8-sig").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    failures = {}
    for item in events:
        failure = item.get("failure_type", "none")
        if failure != "none":
            failures[failure] = failures.get(failure, 0) + 1
    result = {"ok": True, "status": "no-data" if not events else "drift" if failures else "healthy", "events": len(events), "failures": failures, "privacy": "metadata-only;原始事件不进入分发包", "evidence_status": "local-aggregate"}
    return write_report(root, "adoption_drift", result, "采用与漂移报告")


def atlas(workspace):
    workspace = Path(workspace).resolve()
    skills = []
    for skill_file in workspace.rglob("SKILL.md"):
        if "ye-skill-forge" in skill_file.parts or "yao-meta-skill-custom" in skill_file.parts:
            continue
        try:
            _root, _file, metadata, _front, _body = load_skill(skill_file.parent)
        except Exception:
            continue
        words = set(re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", str(metadata.get("description", "")).lower()))
        skills.append({"path": str(skill_file.parent), "name": metadata.get("name"), "description": metadata.get("description", ""), "terms": sorted(words)})
    collisions = []
    for index, left in enumerate(skills):
        for right in skills[index + 1:]:
            overlap = sorted(set(left["terms"]) & set(right["terms"]))
            if len(overlap) >= 3:
                collisions.append({"left": left["name"], "right": right["name"], "overlap": overlap})
    result = {"ok": True, "skills": skills, "collisions": collisions, "status": "portfolio-signal-only", "evidence_status": "static-metadata"}
    report_dir = workspace / "reports"
    write_json(report_dir / "skill_atlas.json", result)
    return result
