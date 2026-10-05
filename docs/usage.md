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

Ye 的核心方法不依赖特定 Agent 工具。Codex、Claude Code 和其他兼容应用都使用完整目录；需要交付适配时使用三种目标，见 `methods/portability.md`。适配器提供根入口、必要元数据和安装计划，不安装、不启动子 Agent。只有读取能力时可做设计和审查；编辑与脚本能力分别决定能否修改文件、运行工程检查。缺少能力时报告相应验证缺口。

安装完成后，在 agent 对话中直接说明目标、输入材料和交付要求。例如：

> 请把 `D:\docs\meeting-sop.md` 创建为一个可复用 skill。先确认目标用户、触发条件、输入输出契约和边界，再生成文件。

> 请审查 `D:\skills\invoice-helper`，输出按严重度排序的问题、证据路径、缺少的验证和建议动作，不要修改源文件。

> 请根据 `feedback.jsonl` 改进当前 skill。保留已经验证的行为，补充一个正例、一个近邻负例和一个回归案例，然后报告实际改动。

请求中应尽量提供：目标路径、目标用户、输入材料、期望输出、不能做的事情、授权范围和成功条件。缺少的信息如果会改变设计或风险等级，Ye 会先追问；其他信息会明确标为假设。

### 不知道从哪里开始

可以直接说“介绍一下 Ye 能做什么”或“我想做 Skill，但不知道怎么开始”。Ye 会简短介绍创建、审查、改进、验证或交付等入口，并结合你的处境建议下一步。只询问能力不会创建文件，不需要先填写所有字段或学习命令。

目标明确时直接说明任务即可，无需每次选择模式。可选先例研究、组合与跨平台交付只在有需要时启用，不逐项询问开关。

## 3. 常用工作流

### 从模糊想法开始

先让 Ye 输出意图模型：用户结果、目标使用者、重复任务、输入材料、可复用做法、输入输出、触发/近邻边界和设计模式。每轮提出一到两条高信息量问题；关键职责不清楚时保持 `clarify`，低风险缺口记录为假设后继续。脚本整理字段和问题，领域理解由 agent 完成。

维护者可运行：

```powershell
python scripts/ye.py intent --idea "我想做一个能处理研究资料的 skill"
```

### 创建

说明要重复执行的工作、目标用户、用户最终结果、输入、必要材料、工具、权限和边界。Ye 会先进行需求建模，再从已有做法和材料中提炼领域方法，选择合适模板，生成 `SKILL.md`、`manifest.json`、`agents/interface.yaml` 和基本评测。

已有简报可保存为 JSON，运行 `intent --brief-file brief.json`，再用 `create --brief-file brief.json --require-ready` 生成。CLI 只提供骨架和已有真实触发样例，agent 继续完成具体领域流程和输出案例；省略准备度检查只能得到 draft。简报格式见 `skills/ye-skill-forge/methods/intent.md`。

简报中的非空 `description` 会保留并传到入口和 manifest；缺失或空白时才自动生成。Agent 仍应审查其准确性。字段准备度不证明方法有效，用户提出的事实假设、拆分方式和流程仍需检查。复杂任务第一版应覆盖约定范围内的必要分支、工具和恢复逻辑；仅在明确接受原型时缩小范围。

自动描述把执行约束写为中性的“边界”，只有近邻任务写为“不要用于”，避免将“不编造事实”反转为路由排除。输入内容中的字面参数（如 `{title}`、`{output_format}`）保持原样；结构检查只提示复核，Agent 需区分正常参数与未完成骨架。

### 可选先例研究

默认直接根据需求、材料和现有资产设计。提供参考时只分析指定内容；希望外部搜索时明确提出，例如：

> 先研究同类 Skill 如何验证引用完整性，再按我的输入输出要求设计。允许不采用任何现有方案。

研究围绕具体设计问题，按相关性阅读真实入口和资源，并说明采用、调整和舍弃理由。它不强制 skills.sh、SkillsMP、排名或固定候选数，也不将研究设为创建门禁。必要的领域资料、事实核查和工具文档照常按任务需要读取。

这是宿主 Agent 按 `methods/prior-art.md` 执行的对话流程，CLI 不自动搜索。来源无法访问时说明缺口，继续可以完成的工作，不编造研究结果。

### 审查

提供已有 skill 的目录，让 Ye 读取入口文件、manifest、interface、脚本、评测样例和已有报告。审查结果会区分已观察事实、推断原因、待验证假设和阻塞项。

同时沿具体请求检查决策矛盾、资源是否被加载、缺失输入和交接失败。每项发现说明请求、对应指令、错误行为和复现方式；CLI 的结构清单不替代语义审查。方法见 `methods/semantic-review.md`。

### 改进

说明反馈来源和允许修改的范围。Ye 应保留已验证的有效行为，并把每次改动绑定到正例、近邻负例或回归例；只提供方案时，不会把提案描述成已修改。

维护同时考虑合并、删除重复规则和更新过期依赖，检查调用者后只验证受影响行为；不默认通过增加更多指令修复问题。

### 交付准备

当 skill 需要共享、外部发布或进入高风险流程时，可以要求 Ye 依次执行 Skill IR、信任扫描、目标编译、包校验、安装模拟、升级检查和发布门禁。没有运行时或人工证据的部分会标记为缺少证据。

### 多 Skill 包

需要多个独立职责时，先创建包骨架，再补全 Router、子 Skill 和路由样例：

```powershell
python scripts/ye.py package-init research-workbench --child source-triage --child evidence-synthesis --output-dir ../../.ye/skills/research-workbench
python scripts/ye.py package-validate ../../.ye/skills/research-workbench
python scripts/ye.py route-eval ../../.ye/skills/research-workbench
python scripts/ye.py handoff-check ../../.ye/skills/research-workbench
python scripts/ye.py review ../../.ye/skills/research-workbench
```

这些命令假定当前目录为 `skills/ye-skill-forge/`，生成位置在项目 `.ye/` 中。单任务多个步骤使用一个入口的 workflow-pack，独立职责才拆为 family。路由案例包括正例、包外负例、歧义和有序执行计划；Router/子 Skill 的结构通过不能代表真实路由准确率。

实际使用时同一宿主 Agent 可以读取 Router 和子 Skill 并顺序完成。跨应用编译为缺少根入口的包生成 `SKILL.md`，完整保留相对路径，避免依赖递归发现。子 Skill 若需要独立安装和触发，另外验证客户端注册及共享资源路径。Ye 不提供子 Skill 或子 Agent 的调度引擎。

### 反馈进化

`improve` 只生成提案；`evolve record` 追加 evidence packet，不会悄悄修改 Skill：

```powershell
python scripts/ye.py evolve <skill-dir> record --feedback "问题：输出遗漏来源"
python scripts/ye.py evolve <skill-dir> summary
```

已授权的改进继续应用到文件。受控入口默认只预览：

```powershell
python scripts/ye.py evolve <skill-dir> apply --packet reports/evolution/<proposal>.json --change-file changes.json
python scripts/ye.py evolve <skill-dir> apply --packet reports/evolution/<proposal>.json --change-file changes.json --evidence-file replay.json --apply
python scripts/ye.py evolve <skill-dir> rollback --packet reports/evolution/<application>.json
```

需要回放原失败例、近邻负例和保留行为，并绑定源/候选摘要。应用会备份旧文件，回滚拒绝覆盖后续修改。进化对象既可为生成 Skill，也可为 Ye；修改 Ye 另需已授权的 `--allow-self-edit`。局部应用默认仍为 provisional，不自动同步安装副本或改历史产物。格式和证据限制见 `methods/evolution.md`。

## 4. 输出怎么看

- **创建结果**：源文件、接口文件、评测样例和结构验证结果
- **审查结果**：按严重度排序的发现、门禁状态、证据路径和建议动作
- **改进结果**：实际改动文件、保留行为、回归结果、版本建议和未验证风险
- **交付结果**：目标兼容矩阵、权限与信任报告、归档摘要、安装模拟和升级结果

报告是证据汇总，不会替代源 `SKILL.md`、manifest、interface 或评测样例。没有模型执行、真实客户端或人工审查证据时，不应把静态检查写成效果提升或运行时兼容结论。

维护 Ye 的生成效果时，应分别检查创建结果与生成 Skill 的实际使用：新会话读取完整入口、声明资源和新输入，观察它是否仍能完成任务。已有行为案例是测试计划，不表示已经运行。完整跨任务比较用于维护迭代，不要求每次普通创建都做大型实验。

## 5. 开发者 CLI

正常使用 Ye 不需要手动运行 CLI。维护 Ye 本身或进行发布验证时，在 `skills/ye-skill-forge/` 目录执行：

CLI 需要 Python 3.10+。首次运行前执行 `python -m pip install -r requirements.txt` 安装 PyYAML；没有脚本执行能力的宿主仍可使用 Ye 的方法完成设计和审查，但应报告工程验证缺口。

```powershell
python scripts/ye.py --help
python scripts/ye.py intent --idea "我想做一个能处理研究资料的 skill"
python scripts/ye.py create "会议纪要整理" --slug note-cleanup --job "把会议记录整理为可核查的纪要" --output-dir ../../.ye/skills/note-cleanup
python scripts/ye.py review <skill-dir>
python scripts/ye.py review <skill-dir> --no-report
python scripts/ye.py review <skill-dir> --profile production
python scripts/ye.py skill-ir <skill-dir>
python scripts/ye.py trust <skill-dir>
python scripts/ye.py compile <skill-dir> --target codex --target claude-code --target generic
python scripts/ye.py package <skill-dir> --output-dir dist --zip
python scripts/ye.py install-simulate <skill-dir> --package-dir dist
python scripts/ye.py release-check <skill-dir> --package-dir dist
```

`review` 默认按 maturity_tier 选择 local、production 或 distribution，综合结果只保存 review.json 和 review.md；`--no-report` 不写文件。静态 checked 表示检查完成，不表示行为质量通过。发布预检始终使用 distribution，严格发布仍阻断行为证据缺口。完整选择依据见 `methods/lifecycle.md`。

案例入口使用 SKILL.example.md，以免安装时被当成正常 Skill。要验证案例，先执行 `python scripts/materialize_example.py note-cleanup --output-dir <new-directory>`，然后检查新目录。不要在 examples/ 源目录直接运行需要 SKILL.md 的命令。

验证和测试命令：

```powershell
python -m unittest discover -s tests -v
python scripts/validate.py .
python scripts/evaluate.py .
python scripts/ye.py review .
```

脚本默认把未指定的 Skill 写入当前项目 `.ye/skills/`，报告写入目标目录的 `reports/`，打包结果写入指定的 `dist/`；原始遥测、秘密、凭据和私有对话不应进入发布包。本地 .env、虚拟环境和编辑器状态会统一排除；有意分发的 .env.example/sample/template 会检查凭据，保留空值、明确占位符和变量引用。信任扫描的秘密阻断项会阻止编译或归档，但静态扫描不能保证检出所有敏感数据。

编译完整复制运行所需引用、脚本和资产；目标可选 `codex`、`claude-code`、`generic`，旧参数 `openai`、`claude` 分别兼容为前两者。输出目录在源包内时必须位于 dist/。编译目标子目录非空会拒绝写入，避免旧资源残留。先沿正式入口运行代表性请求，推荐固定完整 `suite` 并保存通过、失败和未执行项，再运行 `python scripts/ye.py behavior-evidence <skill-dir> --evidence-file evidence.json`。需要比较旧版和候选版时使用 `python scripts/ye.py behavior-compare --baseline-file baseline.json --candidate-file candidate.json`。`review` 会读取与当前源绑定的行为证据；缺少、失败、未执行或过期记录都不会被写成行为通过，不能靠静态样例通过。

触发分组必须是请求字符串或含 input 的对象列表；输出 JSON/JSONL 必须包含 input 与期望结果或评审标准。格式无效返回 findings 并阻断 review，不能靠文本行数获得通过。

## 6. 相关资料

- `skills/ye-skill-forge/SKILL.md`：agent 运行时入口和行为契约
- `skills/ye-skill-forge/methods/`：设计、证据、生命周期、可移植性和发布方法
- `skills/ye-skill-forge/examples/`：完整示例 skill
- `skills/ye-skill-forge/tests/`：自动化回归测试
