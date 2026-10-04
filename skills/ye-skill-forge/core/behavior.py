"""Validate supplied observations; never execute or grade model tasks."""

import hashlib
import json
import re


BEHAVIOR_JUDGES = {"human-review", "model-replay", "same-context-agent", "client-smoke"}
CASE_STATUSES = {"passed", "failed", "not-run"}


def suite_hash(suite):
    ordered = sorted(suite, key=lambda item: item["id"])
    return hashlib.sha256(json.dumps(ordered, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def case_status(case):
    status = case.get("status")
    passed = case.get("passed")
    return ("passed" if passed else "failed") if status is None and isinstance(passed, bool) else status


def summarize_evidence(evidence):
    findings = []
    if not isinstance(evidence, dict):
        return {"ok": False, "status": "invalid", "findings": [{"code": "evidence-shape", "message": "Evidence must be an object"}], "cases": 0}

    def issue(code, message):
        findings.append({"code": code, "message": message})

    if not isinstance(evidence.get("source_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", evidence["source_sha256"]):
        issue("source-hash", "source_sha256 must identify the tested source")
    if not isinstance(evidence.get("judge_mode"), str) or evidence["judge_mode"] not in BEHAVIOR_JUDGES:
        issue("judge-mode", "Unknown judge_mode")
    version = evidence.get("schema_version", "1")
    if not isinstance(version, str) or version not in {"1", "2"}:
        issue("schema-version", "Supported evidence versions are 1 and 2")
    suite = evidence.get("suite", [])
    planned = {}
    if version == "2":
        environment = evidence.get("environment")
        if not isinstance(environment, dict) or any(not isinstance(environment.get(key), str) or not environment[key].strip() for key in ("client", "model")):
            issue("environment", "Version 2 requires environment.client and environment.model")
        if not isinstance(suite, list) or not suite:
            issue("suite", "Version 2 requires the complete planned suite")
            suite = []
        for item in suite:
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key].strip() for key in ("id", "input", "expected")):
                issue("suite-case", "Planned cases require id, input and expected")
                continue
            if item["id"] in planned:
                issue("duplicate-id", f"Duplicate planned id: {item['id']}")
            planned[item["id"]] = item
    cases = evidence.get("cases")
    if not isinstance(cases, list) or not cases:
        issue("cases", "Evidence requires case observations")
        cases = []
    counts = {"passed": 0, "failed": 0, "not-run": 0}
    seen = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            issue("case-shape", f"Case {index + 1} must be an object")
            continue
        for key in ("input", "expected"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                issue("case-field", f"Case {index + 1} requires {key}")
        status = case_status(case)
        passed = case.get("passed")
        if not isinstance(status, str) or status not in CASE_STATUSES:
            issue("case-status", f"Case {index + 1} requires passed, failed or not-run")
            continue
        counts[status] += 1
        if "passed" in case and (not isinstance(passed, bool) or passed != (status == "passed")):
            issue("case-status", f"Case {index + 1} has contradictory passed/status")
        required_field = "reason" if status == "not-run" else "observed"
        if not isinstance(case.get(required_field), str) or not case[required_field].strip():
            issue("case-field", f"Case {index + 1} requires {required_field}")
        if version == "2":
            case_id = case.get("id")
            if not isinstance(case_id, str) or case_id not in planned:
                issue("case-id", f"Case {index + 1} is not in the planned suite")
                continue
            if case_id in seen:
                issue("duplicate-id", f"Duplicate result id: {case_id}")
            seen.add(case_id)
            if any(case.get(key) != planned[case_id][key] for key in ("input", "expected")):
                issue("changed-case", f"Input or expected result changed: {case_id}")
    if version == "2" and set(planned) != seen:
        issue("missing-results", "Every planned case must have a result, including not-run cases")
    executed = counts["passed"] + counts["failed"]
    verified = not findings and bool(executed) and not counts["failed"] and not counts["not-run"]
    status = "invalid" if findings else "failed" if counts["failed"] else "partial" if counts["not-run"] else "present"
    return {
        "ok": not findings, "status": status, "findings": findings,
        "cases": len(cases), "counts": {"total": len(cases), "executed": executed, **counts},
        "pass_rate": counts["passed"] / executed if executed else None,
        "completion_rate": executed / len(cases) if cases else None,
        "behavior_verified": verified, "judge_mode": evidence.get("judge_mode"),
        "suite_sha256": suite_hash(suite) if version == "2" and not findings else None,
        "coverage_verified": version == "2" and not findings,
        "limitations": "Version binding and record structure are checked; observations and judgments are supplied by the stated reviewer. Version 1 cannot establish the planned denominator.",
    }


def compare_evidence(baseline, candidate):
    left, right = summarize_evidence(baseline), summarize_evidence(candidate)
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return {"ok": False, "status": "not-comparable", "baseline": left, "candidate": right}
    findings = []
    if not left["ok"] or not right["ok"]:
        findings.append("Both records must be structurally valid")
    if not left.get("suite_sha256") or left.get("suite_sha256") != right.get("suite_sha256"):
        findings.append("Comparison requires the same complete version 2 suite")
    if baseline.get("environment") != candidate.get("environment") or baseline.get("judge_mode") != candidate.get("judge_mode"):
        findings.append("Environment and judge_mode must match")
    if left.get("counts", {}).get("not-run") or right.get("counts", {}).get("not-run"):
        findings.append("Unexecuted cases cannot establish improvement")
    if findings:
        return {"ok": False, "status": "not-comparable", "findings": findings, "baseline": left, "candidate": right}
    old = {case["id"]: case_status(case) for case in baseline["cases"]}
    new = {case["id"]: case_status(case) for case in candidate["cases"]}
    fixed = sorted(key for key in old if old[key] == "failed" and new[key] == "passed")
    regressed = sorted(key for key in old if old[key] == "passed" and new[key] == "failed")
    return {
        "ok": True, "status": "compared", "fixed": fixed, "regressed": regressed,
        "baseline_source_sha256": baseline["source_sha256"], "candidate_source_sha256": candidate["source_sha256"],
        "baseline": left, "candidate": right,
        "evidence_status": "supplied-observations;historical-source-and-judgments-not-independently-verified",
        "limitations": "A matched comparison describes these cases only; it does not prove statistical significance or general improvement.",
    }
