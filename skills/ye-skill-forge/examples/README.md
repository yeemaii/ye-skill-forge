# 示例

案例入口统一为 `SKILL.example.md`，避免安装 Ye 时被递归发现为正式 Skill。需要独立验证或使用时先复制到新目录，复制工具会将入口改为 `SKILL.md`，不修改案例源文件。

| 案例 | 展示的方法 |
| --- | --- |
| `note-cleanup/` | 简单单 Skill：更正、缺值、试探性想法与来源核对 |
| `incident-diagnosis/` | 复杂单 Skill：假设、反证、依赖、授权与恢复验证 |
| `research-package/` | 独立职责组合：路由、同源去重、证据交接与冲突综合 |
| `note-cleanup-improvement/` | 改进对照：候选缺口、原成功行为与待执行回归 |

按当前设计问题只读取相关案例的 design.md 和必要入口；不要默认加载全部案例。worked-example.md 是教学输入与预期结果，evals/ 是测试计划，都不等于实际运行证据。改进案例使用 before/ 和另一个案例的最终入口，不应作为单 Skill 整体安装；复制工具会拒绝该对照目录，候选版使用 note-cleanup 独立复制。

在 Ye 根目录执行：

```text
python scripts/materialize_example.py note-cleanup --output-dir <new-directory>
python scripts/ye.py review <new-directory> --no-report
```

研究包同样先 materialize，再运行 package-validate、route-eval、handoff-check 或 review。编译/打包测试使用临时目录中的副本。临时目录放在 Skill 搜索根之外；准备正式使用时再按已有安装授权放到目标目录。

真实效果验证按 [两层验证方法](../methods/behavior-testing.md) 执行；跨任务比较计划见 [generation-suite.json](../evals/generation-suite.json)。没有新会话或独立执行条件时保留缺口，不将测试计划和作者自评包装成效果提升。
