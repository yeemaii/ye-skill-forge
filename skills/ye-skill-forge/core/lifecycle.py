"""Ye 的轻量生命周期能力：IR、信任、交付、运营和组合审查。"""

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.skill_utils import is_within, load_skill, validate_skill


TARGETS = ("openai", "claude", "generic", "agent-skills-compatible", "vscode")
GENERATED_DIRS = {"reports", "dist", ".git", "__pycache__", ".yao", ".codex", ".ye", ".venv", "venv", "env", ".pytest_cache", ".mypy_cache", ".idea", ".vscode"}
LOCAL_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", ".coverage"}
ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)[\"']?\s*[:=]\s*[\"'][^\"'\r\n]{8,}[\"']"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
ENV_SECRET_NAME = re.compile(r"(?:^|_)(?:API_?KEY|ACCESS_KEY|PRIVATE_KEY|SECRET|TOKEN|PASSWORD)(?:_|$)", re.IGNORECASE)
ENV_PLACEHOLDER = re.compile(r"^(?:your[-_].+|replace[-_].+|change[-_]?(?:me|this)|placeholder|example|sample|dummy|<[^>]+>|\$\{[^}]+\})$", re.IGNORECASE)
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
    report_dir = (root / "reports").resolve()
    if root not in report_dir.parents:
        raise ValueError("reports 目录不能通过链接超出目标边界")
    report_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("json", "md"):
        if root not in (report_dir / f"{name}.{extension}").resolve().parents:
            raise ValueError("报告文件不能通过链接超出目标边界")
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
    root = Path(root)
    # SkillPackage 使用 package.json；单 Skill 保持 manifest.json。
    value = read_json(root / "package.json", None) if (root / "package.json").is_file() else read_json(root / "manifest.json", {})
    return value if isinstance(value, dict) else {}


def iter_source_files(root):
    root = Path(root).resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in GENERATED_DIRS or part.endswith(".pyc") for part in rel.parts):
            continue
        if rel.name in LOCAL_FILES or ((rel.name == ".env" or rel.name.startswith(".env.")) and rel.name not in ENV_TEMPLATES):
            continue
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError(f"源文件不能通过链接超出包边界: {rel}")
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
    root = Path(root).resolve()
    manifest = package_manifest(root)
    if not (root / "SKILL.md").is_file() and manifest.get("package_type") in {"skill-package", "skill-family"}:
        from core.package import package_children, validate_package
        if not validate_package(root)["ok"]:
            raise ValueError("SkillPackage 结构无效，先运行 package-validate")
        children = package_children(root, manifest)
        return {
            "schema_version": "2.0",
            "generated_at": utc_now(),
            "source": None,
            "identity": {"name": manifest.get("name"), "description": manifest.get("description", "")},
            "contract": {"package_type": manifest.get("package_type"), "has_router": bool(manifest.get("router")), "child_count": len(children), "has_handoff": bool((manifest.get("contracts") or {}).get("handoff"))},
            "resources": {"children": [{"name": item["name"], "path": item["path"]} for item in children], "shared": manifest.get("shared", [])},
            "composition": {"router": manifest.get("router"), "routing": manifest.get("routing", {}), "handoff": (manifest.get("contracts") or {}).get("handoff", {})},
            "risk": {"maturity_tier": manifest.get("maturity_tier", "scaffold"), "target_platforms": manifest.get("target_platforms", ["agent-skills-compatible"])},
        }
    root, skill_file, metadata, _frontmatter, body = load_skill(root)
    headings = [line.lstrip("#").strip() for line in body.splitlines() if line.startswith("#")]
    eval_files = [p.relative_to(root).as_posix() for p in (root / "evals").rglob("*") if p.is_file()] if (root / "evals").is_dir() else []
    scripts = [p.relative_to(root).as_posix() for p in (root / "scripts").glob("*.py")] if (root / "scripts").is_dir() else []
    manifest = package_manifest(root)
    design = manifest.get("design", {}) if isinstance(manifest.get("design", {}), dict) else {}
    routing = manifest.get("routing", {}) if isinstance(manifest.get("routing", {}), dict) else {}
    return {
        "schema_version": "2.0",
        "generated_at": utc_now(),
        "source": skill_file.relative_to(root).as_posix(),
        "identity": {"name": metadata.get("name"), "description": metadata.get("description", "")},
        "contract": {
            "headings": headings,
            "has_workflow": any("workflow" in h.lower() or any(term in h for term in ("流程", "生命周期", "工作流", "工作模式", "创建和改进")) for h in headings),
            "has_input_output": any("input" in h.lower() or "output" in h.lower() or "输入" in h or "输出" in h for h in headings),
            "has_boundaries": any("bound" in h.lower() or "范围" in h or "边界" in h for h in headings),
            "has_root_problem": bool(design.get("root_problem")),
            "has_routing_boundary": bool(design.get("triggers") or design.get("near_neighbors")),
            "has_success_signals": bool(design.get("success_signals")),
        },
        "intent": {
            "root_problem": design.get("root_problem", ""),
            "root_confirmed": bool(design.get("root_confirmed", False)),
            "target_user": design.get("target_user", ""),
            "triggers": design.get("triggers", []),
            "near_neighbors": design.get("near_neighbors", []),
            "success_signals": design.get("success_signals", []),
            "pattern": design.get("pattern", "single-procedural-skill"),
            "assumptions": design.get("assumptions", []),
            "missing": design.get("missing", []),
            "readiness": design.get("readiness"),
        },
        "composition": {
            "package_type": manifest.get("package_type"),
            "router": manifest.get("router"),
            "children": manifest.get("children", []),
            "routing": routing,
            "handoff": (manifest.get("contracts") or {}).get("handoff", {}) if isinstance(manifest.get("contracts", {}), dict) else {},
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


def _env_template_has_secret(text):
    if SECRET_PATTERNS[1].search(text):
        return True
    for line in text.splitlines():
        assignment = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not assignment or not ENV_SECRET_NAME.search(assignment[1]):
            continue
        value = assignment[2]
        if value.startswith(("'", '"')):
            quote = value[0]
            end = value.find(quote, 1)
            value = value[1:end] if end >= 0 else value[1:]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0]
        value = value.strip()
        if value and not ENV_PLACEHOLDER.fullmatch(value):
            return True
    return False


def trust_audit(root):
    root = Path(root).resolve()
    findings = []
    capabilities = set()
    scripts = []
    for path, relative in iter_source_files(root):
        if path.suffix != ".py" or not {"scripts", "core", "shared"}.intersection(relative.parts[:-1]):
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        rel = path.relative_to(root).as_posix()
        file_caps = [name for name, pattern in CAPABILITY_PATTERNS.items() if pattern.search(text)]
        capabilities.update(file_caps)
        scripts.append({"path": rel, "capabilities": file_caps, "argparse": "argparse" in text})
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append({"severity": "block", "code": "secret-pattern", "path": rel, "message": "发现疑似秘密或私钥模式"})
        if path.parent == root / "scripts" and "argparse" not in text and "SCRIPT_INTERFACE = \"internal-module\"" not in text:
            findings.append({"severity": "warn", "code": "help-surface", "path": rel, "message": "脚本未声明 argparse 或 internal-module 接口"})
    for path, rel in iter_source_files(root):
        # 部署配置和引用中的秘密同样会进入分发面；tests 中的虚构凭据是审计回归素材。
        if "tests" not in rel.parts and (path.suffix.lower() in {".md", ".json", ".yaml", ".yml", ".txt", ".toml", ".ini", ".cfg", ".pem", ".key"} or rel.name in ENV_TEMPLATES):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            has_secret = _env_template_has_secret(text) if rel.name in ENV_TEMPLATES else any(pattern.search(text) for pattern in SECRET_PATTERNS)
            if has_secret:
                findings.append({"severity": "block", "code": "secret-pattern", "path": rel.as_posix(), "message": "配置或引用中发现疑似秘密或私钥模式"})
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
        "limitations": ["秘密扫描基于静态模式，不能证明不存在敏感数据", "未证明目标客户端的原生权限执行", "未证明外部网络服务或真实客户端行为"],
    }, "信任与权限审计")


def _case_documents(path):
    try:
        text = path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()], None
        return [json.loads(text)], None
    except (OSError, ValueError) as exc:
        return [], str(exc)


def _nonempty_case_value(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return bool(value)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def trigger_eval(root):
    root = Path(root).resolve()
    files = []
    findings = []
    groups = (("positive", "should_trigger"), ("negative", "should_not_trigger"), ("near_neighbor", "near_neighbors"))
    counts = [0, 0, 0]
    for path in (root / "evals").rglob("*") if (root / "evals").is_dir() else []:
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        rel = path.relative_to(root).as_posix()
        values, error = _case_documents(path)
        dedicated = "trigger" in rel.lower()
        if error:
            if dedicated:
                files.append(rel)
                findings.append({"severity": "error", "code": "trigger-json", "path": rel, "message": error})
            continue
        relevant = dedicated or any(isinstance(value, dict) and any(key in value for group in groups for key in group) for value in values)
        if not relevant:
            continue
        files.append(rel)
        for value in values:
            if not isinstance(value, dict) or not any(key in value for group in groups for key in group):
                findings.append({"severity": "error", "code": "trigger-shape", "path": rel, "message": "触发案例需要 positive/negative/near_neighbor 分组对象"})
                continue
            for index, aliases in enumerate(groups):
                key = next((key for key in aliases if key in value), None)
                if key is None:
                    continue
                entries = value[key]
                if not isinstance(entries, list) or any(not (isinstance(entry, str) and entry.strip() or isinstance(entry, dict) and isinstance(entry.get("input"), str) and entry["input"].strip()) for entry in entries):
                    findings.append({"severity": "error", "code": "trigger-cases", "path": rel, "message": f"{key} 必须是非空请求字符串或含 input 的对象列表"})
                    continue
                counts[index] += len(entries)
    positives, negatives, near = counts
    status = "invalid" if findings else "pass" if positives and negatives else "missing"
    return write_report(root, "trigger_eval", {
        "ok": not findings and bool(positives and negatives),
        "status": status,
        "counts": {"positive": positives, "negative": negatives, "near_neighbor": near},
        "files": files,
        "findings": findings,
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
    files = [p for p in (root / "evals").rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".jsonl"} and "output" in p.relative_to(root).as_posix().lower()] if (root / "evals").is_dir() else []
    cases = 0
    findings = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        values, error = _case_documents(path)
        if error:
            findings.append({"severity": "error", "code": "output-json", "path": rel, "message": error})
            continue
        if path.suffix.lower() == ".json":
            document = values[0]
            values = document if isinstance(document, list) else document.get("cases") if isinstance(document, dict) else None
        if not isinstance(values, list):
            findings.append({"severity": "error", "code": "output-shape", "path": rel, "message": "输出 JSON 需要案例列表或 cases 列表对象"})
            continue
        for case in values:
            if not isinstance(case, dict) or not _nonempty_case_value(case.get("input")) or not any(_nonempty_case_value(case.get(key)) for key in ("expected", "expected_output", "expected_behavior", "required_sections", "rubric", "success_signals")):
                findings.append({"severity": "error", "code": "output-case", "path": rel, "message": "输出案例需要具体 input 和 expected、rubric 或行为/结构检查标准"})
            else:
                cases += 1
    return write_report(root, "output_eval", {"ok": not findings and cases > 0, "status": "invalid" if findings else "present" if cases else "missing", "cases": cases, "files": [p.relative_to(root).as_posix() for p in files], "findings": findings, "evidence_status": "static;未运行模型或人工盲审", "limitations": ["不能证明 with-skill 相对 baseline 的实际质量提升"]}, "输出评测")


BEHAVIOR_JUDGES = {"human-review", "model-replay", "same-context-agent", "client-smoke"}


def validate_behavior_evidence(root, evidence):
    """Validate version-bound evidence supplied by a real Skill run or review.

    The checker validates provenance and case shape. It does not claim that a
    model output is semantically correct; that judgment belongs to the stated
    judge mode and its reviewer.
    """
    root = Path(root).resolve()
    findings = []
    if not isinstance(evidence, dict):
        return {"ok": False, "status": "invalid", "findings": [{"code": "evidence-shape", "message": "行为证据必须是 JSON 对象"}], "cases": 0}
    if evidence.get("source_sha256") != tree_sha256(root):
        findings.append({"code": "stale-source", "message": "行为证据绑定的源摘要与当前 Skill 不一致"})
    if evidence.get("judge_mode") not in BEHAVIOR_JUDGES:
        findings.append({"code": "judge-mode", "message": f"judge_mode 必须是 {sorted(BEHAVIOR_JUDGES)} 之一"})
    cases = evidence.get("cases")
    if not isinstance(cases, list) or not cases:
        findings.append({"code": "cases", "message": "行为证据至少需要一个实际案例"})
        cases = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            findings.append({"code": "case-shape", "case": index, "message": "每个行为案例必须是对象"})
            continue
        for key in ("input", "expected", "observed"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                findings.append({"code": "case-field", "case": index, "message": f"行为案例缺少非空 {key}"})
        if case.get("passed") is not True:
            findings.append({"code": "case-failed", "case": index, "message": "行为证据中的每个案例必须明确 passed=true"})
    return {"ok": not findings, "status": "present" if not findings else "invalid", "findings": findings, "cases": len(cases), "judge_mode": evidence.get("judge_mode")}


def record_behavior_evidence(root, evidence_file):
    """Record externally produced behavior evidence after binding it to source."""
    root = Path(root).resolve()
    evidence_path = Path(evidence_file).expanduser().resolve()
    if is_within(evidence_path, root) and root / "reports" not in evidence_path.parents:
        raise ValueError("行为证据输入应放在 Skill 目录外，或放在 reports/ 下；不要把私有证据打进源包")
    evidence = read_json(evidence_path, None)
    if not isinstance(evidence, dict):
        return write_report(root, "behavior_evidence", {"ok": False, "status": "invalid", "error": "证据文件必须是 JSON 对象", "evidence_status": "invalid-input"}, "行为证据")
    result = validate_behavior_evidence(root, evidence)
    if result["ok"]:
        stored = dict(evidence)
        stored["ok"] = True
        stored["status"] = "present"
        stored["recorded_at"] = utc_now()
        stored["evidence_status"] = "version-bound;语义判断由声明的评审方式负责"
        return write_report(root, "behavior_evidence", stored, "行为证据")
    result["evidence_status"] = "invalid-input"
    return write_report(root, "behavior_evidence", result, "行为证据")


def behavior_evidence(root):
    """Read and validate the evidence currently recorded for this source tree."""
    root = Path(root).resolve()
    path = root / "reports" / "behavior_evidence.json"
    if not path.is_file():
        return {"ok": False, "status": "missing", "cases": 0, "findings": [], "evidence_status": "missing"}
    evidence = read_json(path, None)
    result = validate_behavior_evidence(root, evidence)
    result["path"] = str(path)
    result["evidence_status"] = "version-bound" if result["ok"] else "invalid-recorded-evidence"
    return result


def _safe_output_dir(root, output_dir):
    root = Path(root).resolve()
    output = Path(output_dir).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    if output == root:
        raise ValueError("输出目录不能等于 skill 源目录")
    if root in output.parents and output.relative_to(root).parts[0] != "dist":
        raise ValueError("源目录内的交付输出必须位于 dist/；也可以选用源目录外的新目录")
    return output


def compile_targets(root, output_dir=None, targets=None):
    root = Path(root).resolve()
    output = _safe_output_dir(root, output_dir or root / "dist" / "targets")
    targets = targets or ["generic"]
    invalid = sorted(set(targets) - set(TARGETS))
    if invalid:
        raise ValueError(f"未知目标: {', '.join(invalid)}")
    manifest = package_manifest(root)
    if manifest.get("package_type") in {"skill-package", "skill-family"}:
        from core.package import validate_package
        validation = validate_package(root)
        if not validation["ok"]:
            raise ValueError("SkillPackage 结构无效，先运行 package-validate")
    if not trust_audit(root)["ok"]:
        raise ValueError("信任扫描发现阻断项；不能把疑似秘密编译进分发目标")
    # 在复制前固定源列表，避免自定义输出目录被递归编译进自身。
    sources = list(iter_source_files(root))
    if any(output == source.parent or output in source.parents for source, _rel in sources):
        raise ValueError("输出目录包含源文件；请选择空目录或 dist 下的新目录")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for target in targets:
        target_dir = output / target
        target_dir.mkdir(parents=True, exist_ok=True)
        if target_dir.exists() and any(target_dir.iterdir()):
            raise FileExistsError(f"目标目录非空，避免残留旧资源: {target_dir}")
        # 单 Skill 的脚本、引用和资产同样是运行所需源文件。
        for source, rel in sources:
            destination = target_dir / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
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
    if not trust_audit(root)["ok"]:
        raise ValueError("信任扫描发现阻断项；不能把疑似秘密打包")
    sources = list(iter_source_files(root))
    if any(output == source.parent or output in source.parents for source, _rel in sources):
        raise ValueError("输出目录包含源文件；请选择空目录或 dist 下的新目录")
    output.mkdir(parents=True, exist_ok=True)
    name = package_manifest(root).get('name', root.name)
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("归档名称必须是合法 Skill 名称")
    archive = output / f"{name}.zip"
    if make_zip:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
            for path, rel in sources:
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
    result = {"ok": archive.is_file() if make_zip else True, "archive": str(archive) if make_zip else None, "source_sha256": tree_sha256(root), "entries": entry_count, "excluded": sorted(GENERATED_DIRS | LOCAL_FILES) + [".env", ".env.* (except example/sample/template)"], "evidence_status": "executed-structure"}
    return write_report(root, "package_verification", result, "包校验")


def install_simulate(root, package_dir):
    root = Path(root).resolve()
    package_dir = Path(package_dir).expanduser().resolve()
    archives = sorted(package_dir.glob("*.zip")) if package_dir.is_dir() else [package_dir]
    if not archives:
        return write_report(root, "install_simulation", {"ok": False, "error": "未找到 zip 归档", "evidence_status": "missing"}, "安装模拟")
    expected = package_dir / f"{package_manifest(root).get('name', root.name)}.zip"
    if expected in archives:
        archive = expected
    elif len(archives) == 1:
        archive = archives[0]
    else:
        raise ValueError("目录含多个归档且没有匹配名称；请指定准确 zip 文件")
    with tempfile.TemporaryDirectory(prefix="ye-install-") as temp:
        temp_root = Path(temp).resolve()
        with zipfile.ZipFile(archive) as handle:
            for info in handle.infolist():
                target = (temp_root / info.filename).resolve()
                if target != temp_root and temp_root not in target.parents:
                    return write_report(root, "install_simulation", {"ok": False, "error": f"路径穿越: {info.filename}", "evidence_status": "executed"}, "安装模拟")
            handle.extractall(temp_root)
        if (temp_root / "package.json").is_file() or package_manifest(temp_root).get("package_type") in {"skill-package", "skill-family"}:
            from core.package import validate_package, route_eval, handoff_check
            validation = validate_package(temp_root)
            routes = route_eval(temp_root)
            handoff = handoff_check(temp_root)
            return write_report(root, "install_simulation", {"ok": validation["ok"] and routes["ok"] and handoff["ok"], "archive": str(archive), "package": validation, "routing": routes, "handoff": handoff, "evidence_status": "executed-temporary-install"}, "安装模拟")
        candidates = [temp_root] if (temp_root / "SKILL.md").is_file() else [p.parent for p in temp_root.rglob("SKILL.md")]
        if not candidates:
            return write_report(root, "install_simulation", {"ok": False, "error": "归档缺少 SKILL.md", "evidence_status": "executed"}, "安装模拟")
        if len(candidates) != 1:
            return write_report(root, "install_simulation", {"ok": False, "error": "归档有多个入口但未声明 SkillPackage，无法推断安装目标", "evidence_status": "executed"}, "安装模拟")
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
