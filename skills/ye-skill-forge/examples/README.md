# 示例

`note-cleanup/` 是一个完整的 standard 模板示例，包含 manifest、接口元数据和正/负/近邻路由样例。

在 skill 根目录运行 `python scripts/validate.py examples/note-cleanup` 和 `python scripts/evaluate.py examples/note-cleanup` 可检查结构。路由样例供人工或模型复核；静态评估器不会直接执行它们。

`research-package/` 展示多 Skill 组合：Router、来源筛选、证据综合、共享证据结构，以及正例、包外负例、歧义和顺序编排样例。它是一份教学参考，尚未证明真实模型路由准确率。

在 skill 根目录运行 `python scripts/ye.py package-validate examples/research-package`、`route-eval` 和 `handoff-check` 可检查包级结构；`review` 会同时审查 Router 和全部子 Skill。命令写出的 `reports/` 是本地报告，不属于案例源文件。
