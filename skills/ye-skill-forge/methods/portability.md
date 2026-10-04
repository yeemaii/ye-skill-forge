# IR 与可移植性

Skill IR 至少包含：职责、触发和不触发案例、输入/输出契约、工作流、失败模式、资源、脚本、信任边界、成熟度、owner、review cadence 和目标平台。

核心方法使用动作与输入输出约束，不依赖固定工具名、模型、shell、子 Agent 或 Workflow API。运行前识别宿主的读取、编辑、脚本和验证能力；没有写入能力就交付设计或补丁提案，没有执行能力就报告静态结果和行为缺口，不假装运行成功。

## 三种交付方案

| 目标 | 适配产物 | 安装计划 |
| --- | --- | --- |
| `codex` | 完整源目录、根入口、缺少时生成 `agents/openai.yaml` | 项目 `.agents/skills/<name>/`，以当前客户端配置为准 |
| `claude-code` | 完整源目录和根入口，保留已有 frontmatter | 项目 `.claude/skills/<name>/`，以当前客户端配置为准 |
| `generic` | 完整中立目录和根入口 | 用户应用的 Skill 目录，不猜应用专属 API |

旧参数 `openai`、`claude` 分别别名到前两者；`agent-skills-compatible`、`vscode` 使用通用方案，不宣称额外客户端已适配。

`compile` 写入新的交付目录及 `adapter.json`，只提供安装计划，不写客户端配置或安装目录。单 Skill 保留方法和资源；缺少根入口的 Skill 家族生成薄入口，读取原 Router 后由宿主顺序使用子 Skill。子目录独立发现和调用不是默认保证，独立安装必须另检查资源路径。

Codex 原生元数据与 Ye 的 `agents/interface.yaml` 分开。已有 `openai.yaml` 原样保留，包括 policy、dependencies 和用户字段；没有时只生成必要 UI 字段，不自动禁用隐式调用。`interface.yaml` 中的 compatibility 是 Ye 的描述契约，不是客户端权限配置。若源 Skill 明确依赖 Bash 或 PowerShell，适配器保留并报告该依赖；编译不能把不兼容的脚本自动变为通用脚本。

包根已有自定义入口时优先使用根 interface；缺少时才沿用 Router 的界面信息。生成根原生元数据时继承 Router 的已有调用策略和依赖，并将其图标路径换算为包根相对路径。根已有原生元数据仍保持原样。普通脚本依赖的 `package.json` 不代表 Skill 家族；由清单的 `package_type` 判定。

## 验证范围

目标编译不改变核心语义，也不把固定 shell 写成通用前提。每个目标记录能力、限制、建议路径和运行方式。先验证可发现入口和完整资源，再在目标客户端分别检查加载、正常请求、近邻边界及实际脚本依赖。编译和临时解压通过只证明产物结构；客户端行为、子 Skill 独立触发和权限执行仍需实际证据。能力无法满足必需条件时报告缺口；只有不影响用户结果的可选能力才降级。
