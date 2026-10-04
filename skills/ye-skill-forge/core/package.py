"""SkillPackage 的轻量契约、路由评测和子 Skill 交接检查。"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List

from core.skill_utils import is_within, load_skill, validate_skill


PACKAGE_SCHEMA_VERSION = "1.0"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ROUTE_ACTIONS = {"out-of-scope", "clarify"}


def local_path(root: Path, value: Any) -> Path:
    """包声明只能引用包内相对路径，包括对 Windows 路径和符号链接的检查。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("路径必须是非空字符串")
    windows = PureWindowsPath(value)
    if Path(value).is_absolute() or windows.drive or windows.root or ".." in windows.parts:
        raise ValueError(f"需要包内相对路径: {value}")
    target = (root / value.replace("\\", "/")).resolve()
    if target == root or not is_within(target, root):
        raise ValueError(f"路径超出包边界: {value}")
    return target


def read_skill_manifest(root: Path) -> Dict[str, Any]:
    root = Path(root)
    values = {}
    for name in ("package.json", "manifest.json"):
        path = root / name
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if isinstance(value, dict):
            values[name] = value
    package = values.get("package.json", {})
    manifest = values.get("manifest.json", {})
    if package.get("package_type") in ("skill-package", "skill-family"):
        return package
    if manifest.get("package_type") in ("skill-package", "skill-family"):
        return manifest
    return manifest or (package if "package_type" in package else {})


def package_children(root: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    declared = manifest.get("children", manifest.get("skills", []))
    if isinstance(declared, dict):
        declared = [{"name": key, **(value if isinstance(value, dict) else {"path": value})} for key, value in declared.items()]
    if not isinstance(declared, list):
        raise ValueError("children 必须是列表或名称到路径的映射")
    result = []
    for item in declared:
        if isinstance(item, str):
            item = {"name": Path(item).name, "path": item}
        if not isinstance(item, dict):
            raise ValueError("每个子 Skill 必须声明名称和路径")
        target = local_path(root, item.get("path"))
        name = item.get("name") or target.name
        if not isinstance(name, str) or len(name) > 64 or not NAME_PATTERN.fullmatch(name):
            raise ValueError(f"子 Skill 名称无效: {name}")
        if name in ROUTE_ACTIONS:
            raise ValueError(f"子 Skill 名称与保留路由动作冲突: {name}")
        result.append({**item, "name": name, "path": target.relative_to(root).as_posix(), "absolute_path": str(target)})
    return result


def validate_package(package_path: str | Path) -> Dict[str, Any]:
    root = Path(package_path).expanduser().resolve()
    manifest = read_skill_manifest(root)
    findings = []
    if not root.is_dir():
        return {"ok": False, "package": str(root), "findings": [{"severity": "error", "code": "package-dir", "message": "包目录不存在"}]}
    if not manifest:
        findings.append({"severity": "error", "code": "package-manifest", "message": "需要 package.json 或含 package_type 的 manifest.json"})
    if manifest.get("package_type") not in ("skill-package", "skill-family"):
        findings.append({"severity": "error", "code": "package-type", "message": "包清单必须声明 package_type=skill-package 或 skill-family"})
    router = manifest.get("router")
    try:
        router_root = local_path(root, router)
    except ValueError as exc:
        findings.append({"severity": "error", "code": "router-path", "message": str(exc)})
        router_root = root / "__invalid_router__"
    if not (router_root / "SKILL.md").is_file():
        findings.append({"severity": "error", "code": "router-missing", "message": f"缺少 Router SKILL.md: {router}"})
        router_result = {"ok": False, "findings": []}
    else:
        router_findings = validate_skill(router_root)
        router_result = {"ok": not any(item["severity"] == "error" for item in router_findings), "findings": router_findings}
        if not router_result["ok"]:
            findings.append({"severity": "error", "code": "router-invalid", "message": "Router SKILL.md 未通过结构校验"})
    root_entry = root / "SKILL.md"
    if root_entry.is_file():
        root_findings = validate_skill(root)
        if any(item["severity"] == "error" for item in root_findings):
            findings.append({"severity": "error", "code": "root-entry-invalid", "message": "包根 SKILL.md 未通过结构校验"})
        elif isinstance(manifest.get("name"), str) and load_skill(root)[2].get("name") != manifest["name"]:
            findings.append({"severity": "error", "code": "root-entry-name", "message": "包根 SKILL.md 名称必须与包清单 name 一致"})
    try:
        children = package_children(root, manifest)
    except ValueError as exc:
        findings.append({"severity": "error", "code": "children-contract", "message": str(exc)})
        children = []
    child_results = []
    names = set()
    paths = set()
    for child in children:
        name = str(child["name"])
        if name in names:
            findings.append({"severity": "error", "code": "duplicate-child", "message": f"子 Skill 名称重复: {name}"})
        names.add(name)
        child_root = Path(child["absolute_path"])
        if any(is_within(child_root, existing) or is_within(existing, child_root) for existing in paths) or child_root == router_root or is_within(router_root, child_root) or is_within(child_root, router_root):
            findings.append({"severity": "error", "code": "child-overlap", "message": f"Router 和子 Skill 路径必须独立: {child['path']}"})
        paths.add(child_root)
        if not (child_root / "SKILL.md").is_file():
            findings.append({"severity": "error", "code": "child-missing", "message": f"子 Skill 缺少 SKILL.md: {child['path']}"})
            continue
        child_findings = validate_skill(child_root)
        if not any(item["severity"] == "error" for item in child_findings):
            if load_skill(child_root)[2].get("name") != name:
                child_findings.append({"severity": "error", "code": "child-name", "message": "注册名称必须与子 Skill frontmatter.name 一致"})
        child_results.append({"name": name, "path": child["path"], "ok": not any(i["severity"] == "error" for i in child_findings), "findings": child_findings})
    if not children:
        findings.append({"severity": "error", "code": "children-missing", "message": "包至少需要一个可交接的子 Skill"})
    contracts = manifest.get("contracts") or {}
    handoff = contracts.get("handoff") if isinstance(contracts, dict) else None
    missing_handoff = [key for key in ("input", "output", "state") if not isinstance(handoff, dict) or not isinstance(handoff.get(key), str) or not handoff[key].strip()]
    if missing_handoff:
        findings.append({"severity": "error", "code": "handoff-contract", "message": f"交接契约缺少非空字段: {', '.join(missing_handoff)}"})
    shared = manifest.get("shared", [])
    if not isinstance(shared, list):
        findings.append({"severity": "error", "code": "shared-contract", "message": "shared 必须是包内资源路径列表"})
    else:
        for item in shared:
            try:
                resource = local_path(root, item)
                if not resource.is_file():
                    raise ValueError(f"共享资源不存在: {item}")
            except ValueError as exc:
                findings.append({"severity": "error", "code": "shared-path", "message": str(exc)})
    if "shared" not in manifest:
        findings.append({"severity": "warning", "code": "shared-contract", "message": "未声明 shared 资源边界；共享知识应显式列出"})
    return {"ok": not any(i["severity"] == "error" for i in findings) and router_result["ok"] and all(i["ok"] for i in child_results), "package": str(root), "manifest": manifest, "router": str(router), "router_result": router_result, "children": child_results, "findings": findings, "evidence_status": "executed-structure"}


def route_eval(package_path: str | Path) -> Dict[str, Any]:
    root = Path(package_path).expanduser().resolve()
    result = validate_package(root)
    manifest = result.get("manifest", {})
    cases_path = root / "evals" / "route_cases.json"
    cases = []
    if cases_path.is_file():
        try:
            loaded = json.loads(cases_path.read_text(encoding="utf-8-sig"))
            cases = loaded if isinstance(loaded, list) else loaded.get("cases", []) if isinstance(loaded, dict) else []
            if not isinstance(cases, list):
                raise ValueError("cases 必须是列表")
        except (OSError, json.JSONDecodeError, ValueError):
            cases = []
            result.setdefault("findings", []).append({"severity": "error", "code": "route-cases", "message": "路由样例不是有效 JSON"})
    routing = manifest.get("routing") or {}
    findings = result.setdefault("findings", [])
    rules = routing.get("rules", []) if isinstance(routing, dict) else []
    if not isinstance(rules, list) or not rules:
        findings.append({"severity": "error", "code": "routing-rules", "message": "需要非空 routing.rules 列表"})
        rules = []
    declared = set()
    for item in rules:
        if not isinstance(item, dict) or not isinstance(item.get("when"), str) or not item["when"].strip() or not isinstance(item.get("target"), str):
            findings.append({"severity": "error", "code": "routing-rule", "message": "每个路由规则需要非空 when 和 target"})
        else:
            declared.add(str(item["target"]))
    child_names = {item["name"] for item in result.get("children", [])}
    if child_names - declared:
        findings.append({"severity": "error", "code": "route-rule-coverage", "message": f"子 Skill 缺少路由规则: {', '.join(sorted(child_names - declared))}"})
    unknown_targets = sorted(declared - child_names)
    if unknown_targets:
        result.setdefault("findings", []).append({"severity": "error", "code": "route-target", "message": f"路由指向不存在的子 Skill: {', '.join(unknown_targets)}"})
    counts = {"positive": 0, "negative": 0, "conflict": 0, "sequence": 0}
    case_targets = set()
    seen_inputs = {}
    covered = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not isinstance(case.get("input"), str) or not case["input"].strip():
            findings.append({"severity": "error", "code": "route-case", "message": f"样例 {index + 1} 需要非空 input"})
            continue
        expected = case.get("expected")
        if isinstance(expected, list) and expected and all(isinstance(target, str) and target in child_names for target in expected):
            kind = "sequence"
            targets = expected
        elif isinstance(expected, str) and expected in child_names | ROUTE_ACTIONS:
            kind = "negative" if expected == "out-of-scope" else "conflict" if expected == "clarify" else "positive"
            targets = [expected] if expected in child_names else []
        else:
            findings.append({"severity": "error", "code": "route-case-target", "message": f"样例 {index + 1} 的 expected 必须是子 Skill、有序子 Skill 列表、clarify 或 out-of-scope"})
            continue
        if case.get("kind", kind) != kind:
            findings.append({"severity": "error", "code": "route-case-kind", "message": f"样例 {index + 1} 的 kind 与 expected 不符"})
        counts[kind] += 1
        case_targets.update(targets)
        covered.update(targets)
        normalized = " ".join(case["input"].split()).casefold()
        if normalized in seen_inputs and seen_inputs[normalized] != expected:
            findings.append({"severity": "error", "code": "route-case-contradiction", "message": f"同一输入有相互矛盾的期望目标: {case['input']}"})
        seen_inputs[normalized] = expected
    unknown_case_targets = sorted(case_targets - child_names)
    if unknown_case_targets:
        result.setdefault("findings", []).append({"severity": "error", "code": "route-case-target", "message": f"路由样例指向不存在的子 Skill: {', '.join(unknown_case_targets)}"})
    missing_coverage = sorted(child_names - covered)
    coverage_gaps = [key for key in ("negative", "conflict") if not counts[key]]
    if missing_coverage or coverage_gaps:
        findings.append({"severity": "warning", "code": "route-coverage", "message": f"缺少覆盖: 子 Skill={missing_coverage}, 案例类型={coverage_gaps}"})
    errors = any(item["severity"] == "error" for item in findings)
    status = "missing" if not cases else "block" if errors else "review" if missing_coverage or coverage_gaps else "pass"
    result.update({"ok": result.get("ok", False) and not errors and bool(cases), "status": status, "route_cases": len(cases), "counts": counts, "uncovered_children": missing_coverage, "declared_targets": sorted(declared), "metrics": {"routing_accuracy": None, "handoff_success": None, "reason": "样例已检查结构与覆盖，未执行模型 Router"}, "evidence_status": "static;未执行模型路由"})
    return result


def handoff_check(package_path: str | Path) -> Dict[str, Any]:
    result = validate_package(package_path)
    manifest = result.get("manifest", {})
    contracts = manifest.get("contracts")
    handoff = contracts.get("handoff") if isinstance(contracts, dict) else None
    required = {"input", "output", "state"}
    present = {key for key, value in handoff.items() if isinstance(value, str) and value.strip()} if isinstance(handoff, dict) else set()
    missing = sorted(required - present)
    if missing:
        result.setdefault("findings", []).append({"severity": "error", "code": "handoff-fields", "message": f"交接契约缺少字段: {', '.join(missing)}"})
    result.update({"ok": result.get("ok", False) and not missing, "handoff": handoff or {}, "missing_fields": missing, "evidence_status": "executed-structure"})
    return result


def create_package_scaffold(name: str, output_dir: str | Path, children: List[str]) -> Dict[str, Any]:
    """创建可立即校验的包骨架；业务职责仍需由作者补全。"""
    if len(name) > 64 or not NAME_PATTERN.fullmatch(name or ""):
        raise ValueError("包名必须是小写字母或数字，并用单个连字符分隔")
    normalized = []
    for child in children:
        child = str(child).strip().lower()
        if len(child) > 64 or not NAME_PATTERN.fullmatch(child):
            raise ValueError(f"子 Skill 名称无效: {child}")
        if child in ROUTE_ACTIONS:
            raise ValueError(f"子 Skill 名称与保留路由动作冲突: {child}")
        if child not in normalized:
            normalized.append(child)
    if not normalized:
        raise ValueError("至少需要一个子 Skill")
    target = Path(output_dir).expanduser().resolve()
    if is_within(target, Path(__file__).resolve().parents[1]):
        raise ValueError("不能将生成的子 Skill 写入 Ye 源目录")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing target: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=target.parent))
    try:
        manifest = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "package_type": "skill-family",
            "name": name,
            "version": "0.1.0",
            "status": "draft",
            "router": "router",
            "children": [{"name": child, "path": f"skills/{child}"} for child in normalized],
            "shared": [],
            "contracts": {"handoff": {"input": "request", "output": "child result", "state": "routing context"}},
            "routing": {"rules": [{"target": child, "when": f"用户明确请求 {child} 负责的工作"} for child in normalized]},
        }
        (staging / "package.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        router = staging / "router"
        router.mkdir(parents=True)
        (router / "SKILL.md").write_text(
            f"---\nname: {name[:57].rstrip('-')}-router\ndescription: 路由 {name} 的子 Skill 请求并交接上下文；不直接完成子 Skill 业务工作。\nmetadata:\n  author: Ye Skill Forge\n  version: \"0.1.0\"\n---\n\n# {name} Router\n\n## Workflow\n1. 读取 ../package.json 的子 Skill 注册表和 routing.rules，识别请求。\n2. 单职责选择一个子 Skill；复合请求给出有序执行计划和各阶段交接信息。\n3. 无法区分时询问会改变路由的问题；不属于本包时返回 out-of-scope。\n4. 交接 input、output、state 和证据要求；子 Skill 失败时报告断点并停止依赖它的后续阶段。\n\n## Boundaries\n- 不替子 Skill 执行业务工作。\n- 本文件是骨架，尚未验证真实路由行为。\n",
            encoding="utf-8",
        )
        for child in normalized:
            child_dir = staging / "skills" / child
            child_dir.mkdir(parents=True)
            (child_dir / "SKILL.md").write_text(
                f"---\nname: {child}\ndescription: 执行 {child} 负责的可重复工作；职责和边界需要作者补全。\nmetadata:\n  author: Ye Skill Forge\n  version: \"0.1.0\"\n---\n\n# {child}\n\n## Workflow\n1. 明确输入和缺失字段。\n2. 执行本 Skill 的具体工作。\n3. 返回可核查结果和证据状态。\n\n## Boundaries\n- 只处理本 Skill 的职责。\n",
                encoding="utf-8",
            )
        (staging / "evals").mkdir()
        (staging / "evals" / "route_cases.json").write_text(json.dumps([], ensure_ascii=False) + "\n", encoding="utf-8")
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"ok": True, "path": str(target), "manifest": manifest, "evidence_status": "scaffold-structure"}
