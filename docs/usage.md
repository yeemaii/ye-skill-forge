# Ye Skill Forge 使用手册

## 1. Ye 解决什么问题

Ye 用来把工作流、SOP、提示词、脚本或已有 skill 整理成可复用、可评测、可维护的 agent skill。它负责 skill 的工程化生命周期，不负责执行目标 skill 的业务任务。

适合交给 Ye 的请求包括：

- 从工作流或 SOP 创建一个 skill
- 审查已有 skill 的职责、触发边界和输出契约
- 根据反馈改进已有 skill
- 补充触发、输出和回归评测
- 检查权限、依赖、路径和跨平台风险
- 准备编译、打包、安装模拟、升级检查或发布门禁

一次性问答、普通翻译、总结材料或直接执行某个业务 skill，不属于 Ye 的职责范围。

## 2. 安装和调用

将仓库中的 `skills/ye-skill-forge/` 目录作为一个完整 skill 包安装到你的 agent skill 目录。包的运行时入口是 `SKILL.md`；不要只复制其中的一个文件。

安装完成后，在 agent 对话中直接说明目标、输入材料和交付要求。例如：

> 请把 `D:\docs\meeting-sop.md` 创建为一个可复用 skill。先确认目标用户、触发条件、输入输出契约和边界，再生成文件。

> 请审查 `D:\skills\invoice-helper`，输出按严重度排序的问题、证据路径、缺少的验证和建议动作，不要修改源文件。

> 请根据 `feedback.jsonl` 改进当前 skill。保留已经验证的行为，补充一个正例、一个近邻负例和一个回归案例，然后报告实际改动。

请求中应尽量提供：目标路径、目标用户、输入材料、期望输出、不能做的事情、授权范围和成功条件。缺少的信息如果会改变设计或风险等级，Ye 会先追问；其他信息会明确标为假设。

## 3. 常用工作流

### 创建

说明要重复执行的工作、目标用户、输入、输出和边界。Ye 会先进行需求建模，再选择合适模板，生成 `SKILL.md`、`manifest.json`、`agents/interface.yaml` 和基本评测。

### 审查

提供已有 skill 的目录，让 Ye 读取入口文件、manifest、interface、脚本、评测样例和已有报告。审查结果会区分已观察事实、推断原因、待验证假设和阻塞项。

### 改进

说明反馈来源和允许修改的范围。Ye 应保留已验证的有效行为，并把每次改动绑定到正例、近邻负例或回归例；只提供方案时，不会把提案描述成已修改。

### 交付准备

当 skill 需要共享、外部发布或进入高风险流程时，可以要求 Ye 依次执行 Skill IR、信任扫描、目标编译、包校验、安装模拟、升级检查和发布门禁。没有运行时或人工证据的部分会标记为缺少证据。

## 4. 输出怎么看

- **创建结果**：源文件、接口文件、评测样例和结构验证结果
- **审查结果**：按严重度排序的发现、门禁状态、证据路径和建议动作
- **改进结果**：实际改动文件、保留行为、回归结果、版本建议和未验证风险
- **交付结果**：目标兼容矩阵、权限与信任报告、归档摘要、安装模拟和升级结果

报告是证据汇总，不会替代源 `SKILL.md`、manifest、interface 或评测样例。没有模型执行、真实客户端或人工审查证据时，不应把静态检查写成效果提升或运行时兼容结论。

## 5. 开发者 CLI

正常使用 Ye 不需要手动运行 CLI。维护 Ye 本身或进行发布验证时，在 `skills/ye-skill-forge/` 目录执行：

```powershell
python scripts/ye.py --help
python scripts/ye.py create "会议纪要整理" --slug note-cleanup --job "把会议记录整理为可核查的纪要"
python scripts/ye.py review <skill-dir>
python scripts/ye.py skill-ir <skill-dir>
python scripts/ye.py trust <skill-dir>
python scripts/ye.py compile <skill-dir> --target openai --target claude --target generic --target vscode
python scripts/ye.py package <skill-dir> --output-dir dist --zip
python scripts/ye.py install-simulate <skill-dir> --package-dir dist
python scripts/ye.py release-check <skill-dir> --package-dir dist
```

验证和测试命令：

```powershell
python -m unittest discover -s tests -v
python scripts/validate.py .
python scripts/evaluate.py .
python scripts/ye.py review .
```

脚本默认把报告写入目标目录的 `reports/`，把打包结果写入指定的 `dist/`；原始遥测、秘密、凭据和私有对话不应进入发布包。

## 6. 相关资料

- `skills/ye-skill-forge/SKILL.md`：agent 运行时入口和行为契约
- `skills/ye-skill-forge/methods/`：设计、证据、生命周期、可移植性和发布方法
- `skills/ye-skill-forge/examples/`：完整示例 skill
- `skills/ye-skill-forge/tests/`：自动化回归测试
