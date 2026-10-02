---
name: evidence-synthesis
description: 比较已筛选的研究来源并形成带引用的综合结果；不要在没有来源输入时补写事实。
metadata:
  author: Ye Skill Forge 示例
  version: "1.0.0"
---

# Evidence Synthesis

## Workflow
1. 读取 records 来源表和证据状态，按 [共享证据契约](../../shared/evidence-schema.md) 检查必需字段；缺少时报告断点。
2. 区分一致、冲突和未知信息。
3. 输出带来源引用的综合结果和限制。

## Output
返回 conclusions、原始 records 与 unresolved。每个结论按契约包含 claim、sources、status、support、uncertainty；引用指向 records.source。保留输入来源定位、未知和冲突，duplicate/excluded 不作为独立支持证据。
