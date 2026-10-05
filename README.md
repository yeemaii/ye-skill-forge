# Ye Skill Forge

Ye 是中文优先、可独立运行的 agent skill 元设计与工程系统，先从用户结果、真实材料和可复用做法提炼 Skill 设计，再创建单 Skill、工作流包或多 Skill 家族，并覆盖评测、信任检查、跨平台编译、打包、安装模拟、升级和证据驱动进化。

核心职责是 Skill 的创建、审查、改进和维护。提供 Codex、Claude Code 和通用交付适配；业务执行及子 Skill 的使用由宿主 Agent 完成，Ye 不包含运行调度器。适配成功与实际客户端效果分别验证。

不知道从哪里开始时，可直接说“用 Ye 帮我看看有哪些方向”。Ye 会介绍与当前需求相关的入口；目标明确时直接工作。它会检查影响结果的方案假设，以完整解决任务为下限选择结构。先例研究可选：指定参考时只读指定材料，明确要求搜索同类时才展开外部研究。

## 这是一个 Agent Skill

正常使用时，Ye 由 agent 在对话中调用。把 `skills/ye-skill-forge/` 安装到你的 agent skill 目录后，直接提出目标即可，例如：

> 请根据这份会议纪要整理 SOP 创建一个可复用的 skill，先完成需求建模，再生成初版文件和触发评测。

> 请审查 `D:\work\my-skill`，检查触发边界、输出契约、权限风险和发布阻塞项，不要直接修改文件。

> 请根据这轮评测失败改进这个 skill，保留已有有效行为，并补充一个近邻负例和回归验证。

> 我想做一个能处理研究资料的 skill。先问会改变职责和组合方式的问题，不要直接生成一套假设。

> 我还没有 Skill，介绍一下 Ye 能帮我做什么，再帮我选择起点。

> 先研究同类引用笔记 Skill 的来源核对方法，再按我的需求设计；不需要采用它们的目录结构。

不需要为了正常调用 Ye 手动运行 Python 脚本。脚本命令主要面向维护者，用于结构验证、自动化评测、打包和发布前检查。

## Skill 包位置

完整的 skill 包位于 [`skills/ye-skill-forge/`](skills/ye-skill-forge/)。`SKILL.md` 是运行时入口，目录内的脚本、方法、模板、评测和测试共同组成该 skill。

## 快速开始

1. 将 [`skills/ye-skill-forge/`](skills/ye-skill-forge/) 作为一个完整 skill 包安装到 agent 的 skill 目录。
2. 重新加载 agent 或开启新会话。
3. 用自然语言提出创建、审查、改进、评测、打包或发布准备请求。

完整的用户流程见 [`docs/usage.md`](docs/usage.md)。

案例索引见 [`skills/ye-skill-forge/examples/README.md`](skills/ye-skill-forge/examples/README.md)，包含简单整理、复杂诊断、研究组合和改进对照。案例使用 `SKILL.example.md`，安装 Ye 时不会成为正式 Skill；验证时先复制恢复入口。

2.0 至 2.4 的改造说明、验证范围与剩余缺口见 [`docs/upgrade-2.0.md`](docs/upgrade-2.0.md)。

## 开发者验证

运行 CLI 需要 Python 3.10+ 和 `PyYAML` 依赖；首次验证前执行 `python -m pip install -r skills/ye-skill-forge/requirements.txt`。安装依赖只影响本地工程环境，不会写入生成的 Skill 包。

如果你在维护 Ye 本身，进入 `skills/ye-skill-forge/` 目录执行：

```powershell
python -m unittest discover -s tests -v
python scripts/validate.py .
python scripts/evaluate.py .
python scripts/ye.py review . --no-report
```

这些命令用于开发和发布验证，不是最终用户使用 Ye 的主要入口。完整方法见 `skills/ye-skill-forge/methods/`；示例见 `skills/ye-skill-forge/examples/`。生成报告应落在目标 skill 的 `reports/` 下，原始遥测和本地状态不应进入发布包。真实行为验证可用 `python scripts/ye.py behavior-evidence <skill-dir> --evidence-file evidence.json` 绑定当前源版本。

## 许可证

本项目采用 MIT License，详见 [`LICENSE`](LICENSE)。
