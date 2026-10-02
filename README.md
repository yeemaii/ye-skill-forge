# Ye Skill Forge

Ye 是中文优先、可独立运行的 agent skill 工程系统，覆盖可复用 skill 的创建、审查、改进、评测、信任检查、跨平台编译、打包、安装模拟、升级和发布门禁。

## 这是一个 Agent Skill

正常使用时，Ye 由 agent 在对话中调用。把 `skills/ye-skill-forge/` 安装到你的 agent skill 目录后，直接提出目标即可，例如：

> 请根据这份会议纪要整理 SOP 创建一个可复用的 skill，先完成需求建模，再生成初版文件和触发评测。

> 请审查 `D:\work\my-skill`，检查触发边界、输出契约、权限风险和发布阻塞项，不要直接修改文件。

> 请根据这轮评测失败改进这个 skill，保留已有有效行为，并补充一个近邻负例和回归验证。

不需要为了正常调用 Ye 手动运行 Python 脚本。脚本命令主要面向维护者，用于结构验证、自动化评测、打包和发布前检查。

## Skill 包位置

完整的 skill 包位于 [`skills/ye-skill-forge/`](skills/ye-skill-forge/)。`SKILL.md` 是运行时入口，目录内的脚本、方法、模板、评测和测试共同组成该 skill。

## 快速开始

1. 将 [`skills/ye-skill-forge/`](skills/ye-skill-forge/) 作为一个完整 skill 包安装到 agent 的 skill 目录。
2. 重新加载 agent 或开启新会话。
3. 用自然语言提出创建、审查、改进、评测、打包或发布准备请求。

完整的用户流程见 [`docs/usage.md`](docs/usage.md)。

## 开发者验证

如果你在维护 Ye 本身，进入 `skills/ye-skill-forge/` 目录执行：

```powershell
python -m unittest discover -s tests -v
python scripts/validate.py .
python scripts/evaluate.py .
python scripts/ye.py review .
```

这些命令用于开发和发布验证，不是最终用户使用 Ye 的主要入口。完整方法见 `skills/ye-skill-forge/methods/`；示例见 `skills/ye-skill-forge/examples/`。生成报告应落在目标 skill 的 `reports/` 下，原始遥测和本地状态不应进入发布包。

## 许可证

本项目采用 MIT License，详见 [`LICENSE`](LICENSE)。
