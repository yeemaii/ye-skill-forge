---
name: source-triage
description: 筛选、去重并标注研究来源，保留可追溯的来源依据；不要综合来源形成最终结论。
metadata:
  author: Ye Skill Forge 示例
  version: "1.0.0"
---

# Source Triage

## Workflow
1. 读取来源和筛选条件，并按 [共享证据契约](../../shared/evidence-schema.md) 建立 records。
2. 标注相关性、重复项和明显缺失。
3. 返回来源清单、依据和未解决问题。

## Output
返回 `records` 与 `unresolved`。每条记录按契约包含 source、claim、support、status、uncertainty；未读取正文时 claim/support 为 null，保留来源定位和证据缺口。重复或排除项说明原因，不静默删除来源行。
