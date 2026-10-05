---
name: evidence-synthesis
description: 比较已筛选的研究来源并形成带引用的综合结果；不要在没有来源输入时补写事实。
metadata:
  author: Ye Skill Forge 示例
  version: "1.0.0"
---

# Evidence Synthesis

## Workflow
1. 读取 records 来源表和证据状态，按 [共享证据契约](../../shared/evidence-schema.md) 检查必需字段；缺少时报告断点，不通过补写事实修补交接。
2. 将主张按对象、时间和适用条件对齐。不同年份、样本或措施的结果不能直接当成相互矛盾；不能对齐时说明差异并限制综合范围。
3. 比较支持与反证及其来源独立性。duplicate/excluded 不增加支持数量；证据数量不替代方法质量。同条件下存在未解释反证时标为 conflicted，分别引用，不能多数投票消除冲突。
4. 只有一个可用来源时归因到该来源，不宣称跨来源共识；没有可用依据时返回空 conclusions 和明确缺口。有主张但支持不足时可列为 unknown，不将其写成已验证事实。
5. 输出带来源引用的综合结果和限制。区分原始主张、综合判断与未知项；保留与结论相矛盾的可用证据。

## Output
返回 conclusions、原始 records 与 unresolved。每个结论按契约包含 claim、sources、status、support、uncertainty；引用指向 records.source。保留输入来源定位、未知和冲突。贯穿两个阶段的例子见 [worked-example.md](../../worked-example.md)。
