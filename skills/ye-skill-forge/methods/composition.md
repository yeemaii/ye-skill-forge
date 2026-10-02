# 多 Skill 组合

多个相依步骤只需要一个入口的 `workflow-pack`；子职责能够独立触发或复用时使用 `SkillPackage`。包必须声明：

- `router`：只选择子 Skill 并交接，不执行子 Skill 的业务工作；
- `children`：子 Skill 名称和包内相对路径，名称必须与 frontmatter 一致，名称和路径不能重复；
- `shared`：允许共享的文件路径列表，文件必须存在，不需要共享时写空列表；
- `contracts.handoff`：至少有 `input`、`output`、`state`；
- `routing.rules`：自然语言输入到子 Skill 的可解释目标；
- `evals/route_cases.json`：期望目标的路由样例。

路径不能是绝对路径、穿越包边界或借链接引用外部文件。Router 与子 Skill 路径必须独立；显式注册的集合是事实源，不偷偷发现其他目录。

## 路由与顺序编排

路由样例使用 `input` 和 `expected`：

| 期望值 | 含义 |
| --- | --- |
| 子 Skill 名称 | 选择一个职责 |
| `out-of-scope` | 请求属于包外 |
| `clarify` | 信息不足，先提问 |
| 有序子 Skill 名称列表 | 按次序交接和执行 |

必须覆盖每个子 Skill，并包含包外负例和歧义例；缺少覆盖返回 review，格式错误或矛盾期望返回 block。`kind` 可省略，填写时应为 `positive / negative / conflict / sequence` 且与 expected 一致。

复合请求先形成计划，交接每阶段输入、输出期待、进度、假设和证据状态。后续只使用已完成阶段的产物；前置失败时报告断点，不伪造后续完成。只在相互独立且收益明确时并行。执行由目标 agent 或客户端完成，这套 CLI 检查编排契约，不是通用 agent 调度器。

`review` 会检查包结构、路由、handoff 和所有 Router/子 Skill 的审查结果。编译保留相对目录；安装模拟验证整个包，不能只抽查第一个 SKILL.md。

包级通过只证明结构和契约完整。路由准确率、交接成功率和子 Skill 的实际效果仍需要模型执行、真实客户端或人工评审证据。
