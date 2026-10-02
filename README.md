# Ye Skill Forge

Ye 是中文优先、可独立运行的 agent skill 工程系统，覆盖可复用 skill 的创建、审查、改进、评测、信任检查、跨平台编译、打包、安装模拟、升级和发布门禁。

## Skill 包位置

完整的 skill 包位于 [`skills/ye-skill-forge/`](skills/ye-skill-forge/)。`SKILL.md` 是运行时入口，目录内的脚本、方法、模板、评测和测试共同组成该 skill。

## 快速开始

```powershell
cd skills/ye-skill-forge
python scripts/ye.py --help
python scripts/ye.py create "会议纪要整理" --slug note-cleanup --job "把会议记录整理为可核查的纪要" --output-dir .\generated
python scripts/ye.py review .\generated\note-cleanup
```

## 开发和验证

在 `skills/ye-skill-forge/` 目录执行：

```powershell
python -m unittest discover -s tests -v
python scripts/validate.py .
python scripts/evaluate.py .
python scripts/ye.py review .
```

完整方法见 `skills/ye-skill-forge/methods/`；示例见 `skills/ye-skill-forge/examples/`。生成报告应落在目标 skill 的 `reports/` 下，原始遥测和本地状态不应进入发布包。

## 许可证

本项目采用 MIT License，详见 [`LICENSE`](LICENSE)。
