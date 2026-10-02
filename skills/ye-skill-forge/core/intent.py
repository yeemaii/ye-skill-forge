"""将模糊想法压缩成可审查的 Skill 设计意图。

这个模块不替模型替用户做领域决定。它只把已知信息分层、标出假设，
并找出下一条最能改变设计的提问，避免一开始收集一长串低价值字段。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


INTENT_SCHEMA_VERSION = "2.0"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[\n;,；]+", value)
    if not isinstance(value, Iterable):
        return [_text(value)] if _text(value) else []
    result = []
    for item in value:
        item = _text(item)
        if item and item not in result:
            result.append(item)
    return result


def choose_design_pattern(data: Dict[str, Any]) -> str:
    """选择最小生产形态，而不是按功能数量盲目升级复杂度。"""
    composition = data.get("composition") or {}
    if isinstance(composition, str):
        composition = {"requested": composition}
    if not isinstance(composition, dict):
        composition = {}
    children = _list(composition.get("children"))
    components = _list(data.get("components"))
    if children or composition.get("router") or composition.get("independent_triggers"):
        return "skill-family"
    if len(components) > 1 or data.get("delegation") or composition.get("stages"):
        return "workflow-pack"
    return "single-procedural-skill"


def build_intent_model(brief: Dict[str, Any]) -> Dict[str, Any]:
    """返回稳定的意图模型；显式信息优先，推断内容始终标为假设。"""
    brief = dict(brief or {})
    surface = _text(brief.get("surface_request") or brief.get("idea") or brief.get("job"))
    root = _text(brief.get("root_problem"))
    assumptions: List[str] = []
    if not root and surface:
        root = f"让用户能够稳定完成：{surface}"
        assumptions.append("根问题由表层想法暂代，尚未由用户确认")
    target_user = _text(brief.get("target_user") or brief.get("audience"))
    recurring_job = _text(brief.get("recurring_job") or brief.get("job"))
    inputs = _list(brief.get("inputs") or brief.get("input_description"))
    outputs = _list(brief.get("outputs") or brief.get("output_format"))
    boundaries = _list(brief.get("boundaries") or brief.get("exclusions") or brief.get("non_goals"))
    success = _list(brief.get("success_signals") or brief.get("quality_standards"))
    triggers = _list(brief.get("triggers") or brief.get("trigger_examples"))
    near = _list(brief.get("near_neighbors") or brief.get("near_neighbor"))
    constraints = _list(brief.get("constraints"))
    components = _list(brief.get("components"))
    composition = brief.get("composition") or {}
    if isinstance(composition, str):
        composition = {"requested": composition}
    if not isinstance(composition, dict):
        composition = {}

    missing = []
    root_confirmed = brief.get("root_confirmed") is True and bool(_text(brief.get("root_problem")))
    if not root_confirmed:
        missing.append("root_problem")
    for key, value in (
        ("target_user", target_user),
        ("recurring_job", recurring_job),
        ("inputs", inputs),
        ("outputs", outputs),
        ("boundaries", boundaries),
        ("success_signals", success),
    ):
        if not value:
            missing.append(key)
    if not near:
        missing.append("near_neighbors")
    if not triggers:
        missing.append("triggers")

    design = choose_design_pattern({"components": components, "composition": composition, "delegation": brief.get("delegation")})
    required = {"root_problem", "recurring_job", "outputs", "boundaries", "success_signals"}
    # 名称、目标用户和输入细节可以在低风险第一版中作为假设；不强制填满表格。
    readiness = round(1 - len(required.intersection(missing)) / len(required), 2)
    if design == "skill-family" and not composition.get("router"):
        missing.append("router_contract")
        required.add("router_contract")
        readiness = min(readiness, 0.7)

    tension = _text(brief.get("tension"))
    if not tension:
        tension = "覆盖更多表达与保持准确路由之间的平衡"
        assumptions.append("设计张力使用默认的覆盖面/路由准确性")

    return {
        "schema_version": INTENT_SCHEMA_VERSION,
        "surface_request": surface,
        "root_problem": root,
        "root_confirmed": root_confirmed,
        "target_user": target_user,
        "recurring_job": recurring_job,
        "inputs": inputs,
        "outputs": outputs,
        "triggers": triggers,
        "near_neighbors": near,
        "boundaries": boundaries,
        "success_signals": success,
        "constraints": constraints,
        "tension": tension,
        "design_pattern": design,
        "components": components,
        "composition": composition,
        "missing": list(dict.fromkeys(missing)),
        "blocking_missing": [key for key in missing if key in required],
        "assumptions": assumptions,
        "readiness": readiness,
        "next_action": "clarify" if required.intersection(missing) else "design",
    }


QUESTION_BANK = {
    "root_problem": "当这个 Skill 做得很好时，用户哪一个反复出现的失败会消失？请描述失败，而不是想要的工具名称。",
    "target_user": "谁会反复使用它？这个人的上下文或权限会怎样改变设计？",
    "recurring_job": "用户会提供什么输入，并希望每次得到什么可检查的结果？",
    "inputs": "最小必需输入是什么？缺失时应该追问、标记未知，还是拒绝继续？",
    "outputs": "输出中哪些字段或决定是必须存在，才能判断任务完成？",
    "boundaries": "最容易被误认为属于它的相邻请求是什么？哪些请求必须留给其他 Skill？",
    "success_signals": "不用主观的‘感觉更好’，怎样观察到结果满足要求？",
    "near_neighbors": "给一个看起来很像、但不该触发这个 Skill 的请求。",
    "triggers": "用户会怎样自然地表达这个需求？给一个真实说法。",
    "router_contract": "如果拆成多个 Skill，Router 根据什么证据选择子 Skill，并向它交接哪些状态？",
}


def high_information_questions(model: Dict[str, Any], limit: int = 2) -> List[Dict[str, str]]:
    """按会改变架构/边界/风险的程度排序，最多返回少量问题。"""
    missing = list(model.get("blocking_missing", model.get("missing", [])))
    priority = [
        "root_problem", "recurring_job", "outputs", "boundaries", "router_contract",
        "success_signals", "target_user", "inputs", "near_neighbors", "triggers",
    ]
    result = []
    for key in priority:
        if key in missing and key in QUESTION_BANK:
            result.append({"field": key, "question": QUESTION_BANK[key], "why": "会改变 Skill 的职责或验证方式"})
        if len(result) >= min(2, max(1, limit)):
            break
    return result


def clarify(brief: Dict[str, Any], limit: int = 2) -> Dict[str, Any]:
    model = build_intent_model(brief)
    model["questions"] = high_information_questions(model, limit)
    return model
