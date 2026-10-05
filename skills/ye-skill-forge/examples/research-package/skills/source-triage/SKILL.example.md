---
name: source-triage
description: 筛选、去重并标注研究来源，保留可追溯的来源依据；不要综合来源形成最终结论。
metadata:
  author: Ye Skill Forge 示例
  version: "1.0.0"
---

# Source Triage

## Workflow
1. 读取研究问题、纳入条件和实际可读的来源，按 [共享证据契约](../../shared/evidence-schema.md) 建立 records。没有来源时请求输入；决定纳入与否的条件缺失时先澄清，已有条件足够则继续并记录假设。
2. 用内容、时间、对象和条件判断相关性。每条主张保留原文依据与定位；标题或摘要不代表已读全文，未读到的内容不补写。
3. 追溯原始出处。转载同一出处标为 duplicate，指向保留行；主题相似或结论相同不能单独证明重复。原始出处不明时标为 unknown，不能当独立证据计数。
4. 在 assessment 中记录原始/二手/未知来源、可核查依据和限制。原始来源不自动可靠：区分作者主张与研究支持，记录方法、样本、日期等与问题有关的缺口，不编造统一可信度分数。
5. 返回所有来源行和 unresolved。排除、重复和无法读取均说明原因。全部来源不合格或不可读时明确没有可用证据，仍保留来源表，不制造合格记录。

## Output
返回 `records` 与 `unresolved`，完整字段见共享契约。未读取相关内容时 claim/support 为 null；重复或排除项说明原因，不静默删除来源行。贯穿两个阶段的例子见 [worked-example.md](../../worked-example.md)。
