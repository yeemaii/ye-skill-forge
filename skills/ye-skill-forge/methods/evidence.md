# 证据与隐私

报告分为四类：`observed`（已观察）、`static`（静态检查）、`executed`（已运行）和 `missing`（缺少证据）。静态检查只能支持结构结论；不能支持“质量提高”“目标客户端可用”或“发布安全”等行为结论。

代表性行为运行记录为版本绑定证据：包含当前 `source_sha256`、`judge_mode` 和实际观察。推荐版本 2，先固定完整 suite，再保存每个案例的 passed、failed 或 not-run 状态、执行环境和实际输出或未执行原因。格式和比较方法见 [behavior-testing.md](behavior-testing.md)。旧 input/expected/observed/passed 格式兼容，但不能证明完整计划覆盖。

使用 `python scripts/ye.py behavior-evidence <skill-dir> --evidence-file evidence.json` 写入目标 `reports/behavior_evidence.json`。记录有效的 `ok` 不表示行为成功；`behavior_verified`、失败和完成率分别报告。`review` 会重新计算源摘要，失败记录阻断行为门禁，未执行项保留缺口；源文件变化、案例不完整或评审方式不明时记录无效。不得通过只保留成功案例获得发布证据。

遥测默认只允许事件名、版本、命令、结果、失败类型和时间等元数据。不得记录原始 prompt、输出、对话、凭据、私有文件或审查原文。分发时排除原始 JSONL，只保留聚合报告。

证据冲突时保守处理：报告显示通过但源文件不存在，判为失败；报告缺少来源，判为缺少证据；待人工审查不计入人工通过率；“生成了 hook/模板”不计为真实客户端运行证据。

行为证据的结构和版本绑定由 Ye 检查；`human-review`、`model-replay`、`same-context-agent` 和 `client-smoke` 只说明评审方式，不能把结构检查自动升级为语义正确性。
