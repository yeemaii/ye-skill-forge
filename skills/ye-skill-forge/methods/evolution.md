# 证据驱动进化

反馈先成为 evidence packet，再决定是否改变源文件。packet 应说明反馈来源边界、观察、保留行为、最近的已有资产、资产动作（`create`、`merge` 或 `discard`）、部署状态和回滚条件。

## 进化谁

目标可以是生成的 Skill、多 Skill 包，也可以是 Ye 本身。修补目标 Skill 只影响该目标；修补 Ye 的方法、模板和实现才会影响以后生成的 Skill，不自动更新历史产物。只有跨案例共通的机制缺口才上升为 Ye 通用规则。用户授权维护 Ye 本身时直接在明确的源仓库中修复；安装副本和其他 Skill 的传播不包含在本地授权中。

## 作者执行的闭环

1. 捕获实际输入、期望和实际输出，分开观察与根因假设。
2. 重开根问题；确认是任务本身变了，还是路由、检索、规则执行或工具失败。
3. 阅读最近已有资产。`nearest_assets` 仅按文件名和关键词初筛，不提供语义正确性保证。
4. 选择 create/merge/discard。已有同职责规则优先合并；正确规则被忽略时修复路由或资源读取，而非增加重复命令。
5. 已授权的改进落到文件，保留有效行为；回放原失败例、近邻负例和已有成功例。
6. 保存证据和回滚点。provisional 是局部待验证，accepted 需与风险匹配的行为证据，quarantined 是隔离或回滚，rejected 是不采用。

`improve` 只生成建议；`evolve record` 保存记录。修改请求不能停在建议报告。作者可以直接保守修改，也可使用下面的受控 CLI。

## 显式变更集

先记录提案，再准备 `changes.json`；它只支持目标包内的源文本文件，不能删除文件、改运行状态、改变 Skill 身份或执行补丁代码：

```json
{
  "source_sha256": "记录提案时的源树摘要",
  "changes": [{"path": "SKILL.md", "content": "完整的新文件文本"}]
}
```

```powershell
python scripts/ye.py evolve <target> apply --packet reports/evolution/<proposal>.json --change-file changes.json
```

默认只预览，在临时目录检查候选结构、Python 语法和信任门禁，返回 `candidate_sha256`。在相同源与候选上实际回放后，保存 `replay.json`：

```json
{
  "source_sha256": "预览返回的源摘要",
  "candidate_sha256": "预览返回的候选摘要",
  "judge_mode": "human-review",
  "cases": [
    {"kind": "observed-failure", "input": "真实失败请求", "expected": "预期行为", "observed": "候选的实际输出", "passed": true},
    {"kind": "near-neighbor", "input": "近邻负例", "expected": "正确退出或路由", "observed": "实际输出", "passed": true}
  ]
}
```

有 `preserved_behaviors` 时另需 `preserved-success` 用例。`judge_mode` 可为 human-review、model-replay 或 same-context-agent；脚本核验记录结构与版本绑定，不代替评审者判断输出正确性，也不把 same-context-agent 说成独立证据。

```powershell
python scripts/ye.py evolve <target> apply --packet reports/evolution/<proposal>.json --change-file changes.json --evidence-file replay.json --apply
python scripts/ye.py evolve <target> rollback --packet reports/evolution/<application>.json
```

应用 Ye 自身另需 `--allow-self-edit`，且此前已有用户授权。应用前保存旧文件；写入失败会尝试恢复，进程中断时可从 prepared 应用记录回滚。回滚先检查文件摘要，后续用户修改不会被覆盖。变更集和 replay 应放在目标的 reports/ 或包外，避免改变源摘要。

应用成功默认仍为 provisional，没有自动传播、自动高风险部署或自动宣称收益。记录保存在目标 `reports/evolution/`，不进入分发包；原始私有数据按最小化原则处理。真实提升需要同案例基线比较和可核查的实际行为证据。
