"""证据驱动的进化记录；默认只生成可审查提案，不修改 Skill。"""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any, Dict
from uuid import uuid4

from core.lifecycle import GENERATED_DIRS, iter_source_files, package_manifest, read_json, tree_sha256, trust_audit, write_json
from core.package import local_path, route_eval, validate_package
from core.skill_utils import is_within, load_skill, validate_skill


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def nearest_assets(skill_path: str | Path, feedback: Dict[str, Any]) -> list:
    """按问题类型检索目标包中现有的可演化资产，避免重复造规则。"""
    root = Path(skill_path).expanduser().resolve()
    terms = set()
    for item in feedback.get("issues", []) if isinstance(feedback, dict) else []:
        terms.update(str(item.get("type", "")).replace("_", " ").split())
        terms.update(str(item.get("description", "")).lower().split()[:4])
    candidates = []
    for directory in ("references", "evals", "scripts", "methods", "templates"):
        path = root / directory
        if not path.is_dir():
            continue
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            name = item.name.lower()
            score = sum(1 for term in terms if term and term in name)
            if score:
                candidates.append({"path": item.relative_to(root).as_posix(), "score": score})
    return sorted(candidates, key=lambda item: (-item["score"], item["path"]))[:5]


def build_evidence_packet(skill_path: str | Path, feedback: Dict[str, Any], proposals: list | None = None) -> Dict[str, Any]:
    root = Path(skill_path).expanduser().resolve()
    manifest = package_manifest(root)
    issues = feedback.get("issues", []) if isinstance(feedback, dict) else []
    assets = nearest_assets(root, feedback)
    actionable = bool(issues or feedback.get("suggestions"))
    action = "merge" if assets and actionable else "create" if actionable else "discard"
    return {
        "schema_version": "1.0",
        "created_at": _now(),
        "skill": manifest.get("name", root.name),
        "version": manifest.get("version", ""),
        "record_type": "proposal",
        "source_sha256": tree_sha256(root),
        "target_kind": "meta-skill" if manifest.get("name") == "ye-skill-forge" else "skill-package" if manifest.get("package_type") else "skill",
        "source_boundary": "用户提供的反馈；未读取私有日志或 shell history",
        "observations": issues,
        "preserved_behaviors": feedback.get("good", []) if isinstance(feedback, dict) else [],
        "proposals": proposals or [],
        "nearest_assets": assets,
        "retrieval_method": "filename-heuristic;作者需核查内容和根问题是否相同",
        "hypotheses": [],
        "root_review": "重新检查反馈是否仍属于现有根问题；不自动扩大职责",
        "evidence_level": "E1-feedback-text",
        "deployment_status": "provisional",
        "asset_action": action,
        "rollback": "保留当前版本；提案未应用，应用后重放原失败例和近邻负例",
    }


def record_evolution(skill_path: str | Path, packet: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(skill_path).expanduser().resolve()
    evolution_dir = (root / "reports" / "evolution").resolve()
    if not is_within(evolution_dir, root):
        raise ValueError("进化目录不能通过链接超出目标边界")
    evolution_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    path = evolution_dir / f"{stamp}.json"
    index = 1
    while path.exists():
        path = evolution_dir / f"{stamp}-{index}.json"
        index += 1
    write_json(path, packet)
    return {"ok": True, "path": str(path), "packet": packet, "evidence_status": "recorded-proposal"}


def _json_object(path):
    value = read_json(path, None)
    if not isinstance(value, dict):
        raise ValueError(f"需要有效 JSON 对象: {path}")
    return value


def _ledger_path(root, path):
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    ledger = (root / "reports" / "evolution").resolve()
    if not is_within(ledger, root) or ledger not in path.parents or not path.is_file():
        raise ValueError("进化记录必须来自目标的 reports/evolution/ 目录")
    return path


def _atomic_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".ye-write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def apply_evolution(skill_path, packet_path, change_file, evidence_file=None, apply=False, allow_self_edit=False):
    """预览一个显式文本变更集；应用需要版本绑定的回放记录和显式开关。

    只验证提交的回放结构和源版本，不代替评审者判断模型输出是否正确。
    不运行变更集中的代码。低风险本地应用保持 provisional。
    """
    root = Path(skill_path).expanduser().resolve()
    packet_path = _ledger_path(root, packet_path)
    packet = _json_object(packet_path)
    baseline = tree_sha256(root)
    if packet.get("source_sha256") != baseline:
        raise ValueError("源 Skill 已变化；重新记录反馈并审核当前版本")
    plan = _json_object(change_file)
    if plan.get("source_sha256") != baseline:
        raise ValueError("变更集的 source_sha256 不匹配")
    changes = plan.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("changes 需要至少一个 {path, content} 文本变更")
    files = []
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("content"), str):
            raise ValueError("每项变更必须包含 path 和完整文本 content")
        target = local_path(root, change.get("path"))
        rel = target.relative_to(root)
        if set(rel.parts).intersection(GENERATED_DIRS) or target.suffix not in {".md", ".json", ".yaml", ".yml", ".txt", ".py"}:
            raise ValueError(f"变更只允许源文本文件，不能编辑运行状态或二进制: {rel}")
        if target in seen or target.is_dir():
            raise ValueError(f"变更路径重复或不是文件: {rel}")
        seen.add(target)
        before = target.read_bytes() if target.exists() else None
        after = change["content"].encode("utf-8")
        if target.suffix == ".py":
            compile(change["content"], str(rel), "exec")
        files.append({"path": rel.as_posix(), "before": before, "after": after})
    if not any(item["before"] != item["after"] for item in files):
        raise ValueError("变更集没有实际差异")
    manifest = package_manifest(root)
    self_edit = root == Path(__file__).resolve().parents[1] or manifest.get("name") == "ye-skill-forge"
    if apply and self_edit and not allow_self_edit:
        raise ValueError("修改 Ye 自身需要 --allow-self-edit，并且此前已获用户授权")
    with tempfile.TemporaryDirectory(prefix="ye-evolve-") as temp:
        candidate = Path(temp)
        for source, rel in iter_source_files(root):
            destination = candidate / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        for item in files:
            destination = candidate / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(item["after"])
        if manifest.get("package_type") in {"skill-package", "skill-family"}:
            validation = validate_package(candidate)
            if validation["ok"]:
                validation = route_eval(candidate)
            candidate_name = package_manifest(candidate).get("name")
        else:
            findings = validate_skill(candidate)
            validation = {"ok": not any(i["severity"] == "error" for i in findings), "findings": findings}
            candidate_name = load_skill(candidate)[2].get("name") if validation["ok"] else None
        if candidate_name != (manifest.get("name") or load_skill(root)[2].get("name")):
            raise ValueError("进化不能更改 Skill 身份；新职责应创建新 Skill")
        trust = trust_audit(candidate)
        candidate_hash = tree_sha256(candidate)
    if not validation["ok"] or not trust["ok"]:
        raise ValueError("候选版本未通过结构或信任门禁")
    evidence = _json_object(evidence_file) if evidence_file else {}
    cases = evidence.get("cases", [])
    valid_cases = isinstance(cases, list) and all(
        isinstance(case, dict) and case.get("passed") is True and all(isinstance(case.get(key), str) and case[key].strip() for key in ("input", "expected", "observed"))
        for case in cases
    )
    required = {"observed-failure", "near-neighbor"}
    if packet.get("preserved_behaviors"):
        required.add("preserved-success")
    kinds = {case["kind"] for case in cases if isinstance(case, dict) and isinstance(case.get("kind"), str)} if isinstance(cases, list) else set()
    replay_ready = valid_cases and required.issubset(kinds) and evidence.get("source_sha256") == baseline and evidence.get("candidate_sha256") == candidate_hash and evidence.get("judge_mode") in {"human-review", "model-replay", "same-context-agent"}
    result = {"ok": True, "applied": False, "source_sha256": baseline, "candidate_sha256": candidate_hash, "changed_files": [f["path"] for f in files], "validation": validation, "replay_ready": bool(replay_ready), "required_case_kinds": sorted(required), "evidence_status": "candidate-structure;回放记录由调用者提供，未独立验证语义", "deployment_status": "provisional"}
    if not apply:
        return result
    if not replay_ready:
        raise ValueError("应用需要绑定 source/candidate 摘要的原失败例、近邻负例和保留行为回放记录")
    if tree_sha256(root) != baseline:
        raise ValueError("预览期间源 Skill 已变化；拒绝覆盖")
    event = {"record_type": "application", "created_at": _now(), "proposal": packet_path.name, "source_sha256": baseline, "candidate_sha256": candidate_hash, "deployment_status": "provisional", "application_status": "prepared", "judge_mode": evidence["judge_mode"], "evidence": evidence, "files": [{"path": item["path"], "before_base64": base64.b64encode(item["before"]).decode("ascii") if item["before"] is not None else None, "after_sha256": hashlib.sha256(item["after"]).hexdigest()} for item in files]}
    # 先保存可恢复的旧内容，再写入；失败时恢复已经写入的文件。
    recorded = record_evolution(root, event)
    try:
        for item in files:
            _atomic_bytes(root / item["path"], item["after"])
        event["application_status"] = "applied"
        write_json(recorded["path"], event)
    except Exception:
        for item in files:
            target = root / item["path"]
            if item["before"] is None:
                target.unlink(missing_ok=True)
            else:
                _atomic_bytes(target, item["before"])
        event["application_status"] = "rolled-back"
        event["deployment_status"] = "quarantined"
        write_json(recorded["path"], event)
        raise
    result.update({"applied": True, "rollback_record": recorded["path"], "judge_mode": evidence["judge_mode"]})
    return result


def rollback_evolution(skill_path, application_path):
    root = Path(skill_path).expanduser().resolve()
    path = _ledger_path(root, application_path)
    event = _json_object(path)
    if event.get("record_type") != "application" or event.get("application_status") not in {"applied", "prepared"}:
        raise ValueError("需要已应用或中断待恢复的 application 记录")
    files = event.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("回滚记录缺少文件")
    prepared = []
    seen = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("回滚文件记录必须是对象")
        target = local_path(root, item.get("path"))
        if target in seen:
            raise ValueError("回滚文件记录包含重复路径")
        seen.add(target)
        if set(target.relative_to(root).parts).intersection(GENERATED_DIRS):
            raise ValueError("回滚路径必须是源文件")
        before = base64.b64decode(item["before_base64"], validate=True) if item.get("before_base64") is not None else None
        actual = target.read_bytes() if target.exists() else None
        after_hash = hashlib.sha256(actual).hexdigest() if actual is not None else None
        if after_hash != item.get("after_sha256") and not (event["application_status"] == "prepared" and actual == before):
            raise ValueError(f"文件在应用后又被修改，拒绝覆盖: {item['path']}")
        prepared.append((target, before))
    event.update({"application_status": "prepared", "rollback_started_at": _now()})
    write_json(path, event)
    for target, before in prepared:
        if before is None:
            target.unlink(missing_ok=True)
        else:
            _atomic_bytes(target, before)
    event.update({"application_status": "rolled-back", "deployment_status": "quarantined", "rolled_back_at": _now()})
    write_json(path, event)
    return {"ok": True, "rolled_back": True, "files": [item["path"] for item in files], "evidence_status": "restored-source-files"}


def evolution_summary(skill_path: str | Path) -> Dict[str, Any]:
    root = Path(skill_path).expanduser().resolve()
    directory = (root / "reports" / "evolution").resolve()
    if not is_within(directory, root):
        raise ValueError("进化目录不能通过链接超出目标边界")
    records = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            if not is_within(path, root):
                raise ValueError("进化记录不能通过链接超出目标边界")
            data = read_json(path, {})
            if data:
                records.append(data)
    applied = sum(record.get("application_status") == "applied" for record in records)
    return {"ok": True, "records": len(records), "applications": applied, "latest": records[-1] if records else None, "status": "no-data" if not records else "applied-provisional" if applied else "proposals-only", "evidence_status": "local-aggregate"}
