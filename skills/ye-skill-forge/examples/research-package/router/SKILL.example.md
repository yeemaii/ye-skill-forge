---
name: research-workbench-router
description: 将研究请求路由到来源筛选或证据综合子 Skill，并交接输入、状态和证据要求；不直接完成研究业务任务。
metadata:
  author: Ye Skill Forge 示例
  version: "1.0.0"
  language: zh-CN
---

# Research Workbench Router

## Workflow
1. 读取 `../package.json` 中的子 Skill 注册表和路由规则，识别来源筛选或证据综合请求。
   交接前读取 [共享证据契约](../shared/evidence-schema.md)，确认 records 字段和阶段状态；不替子 Skill 提取或综合证据。
2. 筛选、去重和检查来源可信依据选择 `source-triage`；比较来源的一致与冲突选择 `evidence-synthesis`。
3. 先筛选再综合的复合请求返回有序计划 `[source-triage, evidence-synthesis]`，前一阶段的来源表成为后一阶段输入。
4. 只说“处理资料”且没有目标时返回 `clarify`，询问要来源表还是综合结果；无关任务返回 `out-of-scope`。
5. 按共享契约原样交接原始输入、records 来源表、已知约束、假设和证据状态。前置阶段失败或缺少必需字段时报告断点并停止后续依赖阶段。

## Boundaries
- 不替子 Skill 执行研究分析。
- 不把路由选择当作研究结论。
