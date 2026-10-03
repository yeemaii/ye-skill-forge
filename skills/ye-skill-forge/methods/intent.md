# 意图建模与高信息量提问

## 目标

不要把“我想做一个 X skill”直接当作设计。先区分表层交付物和用户希望稳定复用的结果、方法：

```text
表层想法 -> 用户结果 -> 重复工作 -> 输入/材料/工具 -> 触发/近邻 -> 成功信号
```

用户结果或职责若未确认，模型只能标为假设，状态保持 `clarify`。确认可以来自用户已经描述的真实任务、期望结果、有效做法或失败，不重复索取确认。职责、结果、边界和成功信号足够形成可审查第一版时进入设计；可合理推断的其他字段不阻塞。

## 提问选择

给每个候选问题估计它是否会改变：

1. 单 Skill、工作流包还是 Skill 家族；
2. 输入、输出、权限或风险边界；
3. 触发路由或可观察验证方式。

每轮只问影响最大的前一到两项，不设置会迫使模型假装理解的总轮数。优先问用户结果、必需输出、已有有效做法和近邻负例；已有失败时再追问失败，避免询问可以安全假设的名称、文风或目录细节。一个输入/期望结果/实际结果的真实案例通常比抽象功能清单更有信息。

必要时提出两种可辨别的根问题候选，并说明选择会怎样改变输出；不要暗示某个候选才是“真正需求”。保持用户已选的领域、产品和授权范围。

## 证据字段

`user_result`、`root_problem`、`target_user`、`recurring_job`、`inputs`、`outputs`、`materials`、`tools`、`permissions`、`reusable_method`、`triggers`、`near_neighbors`、`boundaries` 和 `success_signals` 是可审查字段。`assumptions` 记录推断，`missing` 记录全部缺口，`blocking_missing` 只保留阻止设计的缺口。`readiness` 是字段准备度，不是质量或理解准确率。

`intent.py` 整理字段并选问题，不调用语言模型，也不能自动找出根因。仅给出 idea 时，输出的根问题是明确标记的临时候选。

## 从简报到文件

```json
{
  "root_problem": "整理来源时反复丢失引用",
  "user_result": "每项事实都能回到原始资料",
  "root_confirmed": true,
  "recurring_job": "把资料整理为带引用的笔记",
  "inputs": ["原始资料"],
  "outputs": ["按主题排列的引用笔记"],
  "boundaries": ["不写无来源结论"],
  "success_signals": ["每项事实可追溯到原始资料"],
  "triggers": ["整理这些资料为引用笔记"],
  "near_neighbors": ["帮我创作一个无关的小说故事"]
}
```

将作者确认的领域决策保存为 `brief.json`，用 `intent --brief-file brief.json` 检查，再用 `create --brief-file brief.json --require-ready` 生成骨架。模型继续把骨架的泛化步骤改成具体领域决策，并补实际输入/输出案例；CLI 本身不完成领域设计。用户结果、职责、输出、边界或成功条件未明确时 `--require-ready` 在写文件前返回失败；不带该选项只允许得到标为 draft 的骨架。

阶段列表 `components` 默认表示一个工作流；只有声明 `composition.children`、`router` 或 `independent_triggers`，才升级为 Skill 家族。单个步骤没有理由使用多 Skill 包。
