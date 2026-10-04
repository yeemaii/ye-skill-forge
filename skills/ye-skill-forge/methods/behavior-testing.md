# 行为验证与同案例比较

执行者是宿主 Agent、目标客户端或人工评审。Ye 整理案例、验证记录和比较结果，不启动实验、目标业务或子 Agent。文件存在、结构通过、记录格式有效和行为通过是不同结论。

## 先固定案例

以真实任务选正常请求、近邻边界、缺失输入和要保留的成功行为。修改已有 Skill 时加入原失败例；多 Skill 包加入歧义路由、复合请求及前置阶段失败。案例复杂度与风险匹配，不要求每个简单 Skill 建大型基准。

先保存完整 `suite` 再运行；每项有稳定 id、实际 input 和可观察 expected。开发案例用于修改，验证案例用于选方案，最终验收案例不参与反复选优。没有独立执行环境时可以同上下文检查，但如实声明 `same-context-agent`；新建子 Agent 或同模型评审也不自动构成独立盲审。

## 版本 2 记录

```json
{
  "schema_version": "2",
  "source_sha256": "当前源树摘要",
  "judge_mode": "human-review",
  "environment": {"client": "实际客户端及版本", "model": "实际模型；未获知时写 unknown"},
  "suite": [
    {"id": "normal", "input": "整理含一个决定的会议记录", "expected": "决定可追溯到原文"},
    {"id": "missing", "input": "整理没有正文的记录", "expected": "请求提供正文"}
  ],
  "cases": [
    {"id": "normal", "input": "整理含一个决定的会议记录", "expected": "决定可追溯到原文", "status": "failed", "observed": "输出决定没有原文依据"},
    {"id": "missing", "input": "整理没有正文的记录", "expected": "请求提供正文", "status": "not-run", "reason": "客户端不可用"}
  ]
}
```

`status` 为 passed、failed 或 not-run。已运行项保存实际 observed，未运行项保存 reason；不要根据期望编造 observed。suite 的每个 id 恰有一个结果，不能删掉失败或未执行项，也不能运行后修改 input/expected。模型调用、工具轨迹和产物可另外保存到本地 reports，记录可复核来源而不打进发布包。

```text
python <ENGINE_ROOT>/scripts/ye.py behavior-evidence <target> --evidence-file run.json
python <ENGINE_ROOT>/scripts/ye.py behavior-compare --baseline-file baseline.json --candidate-file candidate.json
```

记录入口的 `ok` 表示记录有效；`behavior_verified` 才表示提供的案例已全部运行并通过。有效失败记录保留并阻断行为门禁；未执行项保留为 partial，不计入运行成功率的分母，同时单独报告完成率。版本 1 的 input/expected/observed/passed 仍可读取，但不能证明完整计划覆盖。

## 比较与报告

改善已有 Skill 时保存旧版源和结果，再执行候选版；使用相同 suite、环境及评审方式。`behavior-compare` 检查这些条件，列出修复和退化案例，不代替重新运行，也不验证历史源和观察的真实性。不同客户端或模型的结果分别报告，不合成一次公平 A/B。

主观质量可用匿名 A/B：评审者读取中立 A/B 产物，作者保存版本映射；随机或交替安排顺序，预先确定质量标准。没有条件盲审就说明限制，不把自评写成独立证据。

报告源版本、计划数、执行数、成功、失败、未执行、环境、评审方式和真实失败。修复一个案例不能推出所有领域提升；有退化时分析取舍并保留待验证状态。源变化后旧证据失效，不能用它证明当前版本发布就绪。
