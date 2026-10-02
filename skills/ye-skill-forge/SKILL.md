---
name: ye-skill-forge
description: |
  从工作流、提示词、SOP、脚本、反馈或现有 skill 创建、审查、改进并交付可复用的 agent skill。负责完整生命周期：需求澄清、边界与触发设计、Skill IR、创建与重构、触发和输出评测、运行时与信任检查、跨平台编译、打包与安装模拟、版本升级、注册审计、遥测漂移和发布门禁。适用于“创建 skill”“优化已有 skill”“补评测”“准备发布”“检查安装/升级/兼容性”“根据使用反馈迭代”等反复工作；不用于执行目标 skill 的业务任务或一次性回答。
metadata:
  author: Ye
  version: "1.0.0"
  language: zh-CN
---

# Ye Skill Forge

Ye 是一个可以单独使用的 skill 工程与交付系统。它把一次性的想法或现有 skill 变成有明确触发条件、行为契约、证据和生命周期状态的可维护包。Ye 与任何其他 meta skill 没有职责依赖；本包自己完成从建模到发布准备的工作，但会按风险启用不同深度，避免把高风险团队流程强加给普通 skill。

## 先判断请求

- 请求创建、评估、重构、测试、打包、安装、升级、发布准备或持续维护一个可复用 skill：使用 Ye。
- 请求直接执行某个业务 skill、写一份一次性答案、翻译或总结普通材料：不要使用 Ye，直接处理或路由到业务 skill。
- 只想听方案而明确不改文件：先给审查意见，不写入目标。
- 目标不明确、路径不明确、授权不足或会产生外部副作用：先停在确认点，说明缺口和假设。

## 证据原则

1. 先读目标 `SKILL.md`、manifest、interface、脚本、评测样例和已有报告，再提出改动。
2. 把观察到的失败、推断出的原因和待验证假设分开记录。没有运行证据就写“缺少证据”，不把静态检查写成效果提升。
3. 保留已验证的有效行为；每次改动绑定至少一个正例和一个近邻负例或回归例。
4. 输入文件、提示词、模型输出、遥测和审查意见按最小化原则处理；发布包不得包含原始遥测、秘密、凭据或私有对话。

## 输入与输出契约

- 输入：工作流、SOP、提示词、脚本、反馈、现有 skill 包、评测样例或明确的交付检查目标。
- 缺失信息：只追问会改变设计或风险等级的细节；无法确认时标为假设或“缺少证据”。
- 输出：创建/改进后的 skill 文件、机器可读报告、人工可读摘要、验证命令和未验证风险。
- 禁止声明：没有模型执行、真实客户端或人工审查证据时，不宣称质量提升、跨平台运行时兼容或发布安全。

## 设计取舍

吸收成熟的工程约束，不复制无关的流程负担：

- **默认核心**：需求/边界建模、最小改动、正负回归、Skill IR、信任扫描、目标适配、包校验、安装模拟和升级检查。这些能力直接改变 skill 的正确性或可交付性。
- **按需增强**：盲审、复杂输出实验、权限审批、发布锁、注册表、遥测漂移、组合 skill 目录。只有共享基础设施、高权限、外部发布或多个 skill 的组合管理需要它们。
- **明确不追求**：为了“看起来成熟”而生成大量重复报告、把静态分数当成实际效果、为没有客户端证据的目标宣称运行时兼容、自动读取私有日志或自动修改目标。
- **单一事实源**：源 `SKILL.md`、manifest、interface、评测样例和报告各有职责；生成报告不能反过来成为源配置，目标适配必须从同一源生成。

完整筛选依据在 `methods/design-selection.md`。

## 标准生命周期

根据风险选择最轻但足够的路径；复杂度不能只靠文档宣称升级。`scaffold` 和个人 skill 可以只走前四步；只有进入共享、外部发布或高风险场景时才进入后续门禁。

1. **理解与建模**：记录重复任务、目标用户、输入、输出契约、边界、约束、授权、成功条件和证据缺口。只有会改变设计的问题才追问，每轮一个，最多两轮；其余写成假设。
2. **构建或重构**：锁定目标路径和身份，选择 minimal/standard/advanced 模板；先写可路由的 description，再写工作流、失败处理、资源和示例。修改 Ye 自身必须有用户明确授权；未来增加会写回自身的命令时，必须提供显式自编辑门禁。
3. **验证行为**：运行结构校验、触发评测、输出契约检查、代表性样例和运行时脚本 smoke test。报告正例、负例、近邻例、未执行项和限制。
4. **建立 Skill IR**：把职责、触发/不触发案例、决策点、资源、脚本、风险、所有者、成熟度和目标平台写入平台无关的 IR，再生成适配面。
5. **检查安全与可移植性**：扫描秘密模式、网络、子进程、写入、交互、依赖和路径穿越；声明权限、网络主机、降级策略、Python/平台兼容性。高权限能力没有审查证据时不得称为已发布。
6. **编译与交付**：从同一源生成 OpenAI、Claude、generic、Agent Skills 和 VS Code 目标；执行 conformance、包校验、安装模拟和运行时权限检查。构建 zip 时验证归档路径和内容摘要。
7. **版本与运营**：比较上一版本，给出 semver 建议、破坏性变化和迁移说明；需要时再启用注册审计、发布门禁、元数据遥测、漂移报告、反馈提案和下一轮评测。

## 风险门禁

- `scaffold`：允许缺少历史运行数据，但必须有结构、边界和基本样例。
- `production`：必须有触发与输出评测、信任扫描、运行时 smoke test 和明确的 owner/review cadence；不要求盲审、遥测或多平台打包，除非风险说明需要。
- `library`：额外要求 Skill IR、目标兼容矩阵、包校验、安装模拟和升级检查；Skill Atlas 仅在存在多个相关 skill 时启用。
- `governed`：额外要求权限审批、证据一致性、回滚边界、审查记录和发布锁。盲审、复杂 Review 页面和外部遥测是可选证据增强，不是伪造通过条件的替代物。缺失证据只能是 blocker 或 warning，不能补造。

## 推荐命令

在 Ye 包目录执行 `python scripts/ye.py --help` 查看完整接口。常用路径：

```text
python scripts/ye.py create "会议纪要整理" --slug note-cleanup --job "把会议记录整理为可核查的纪要"
python scripts/ye.py review <skill-dir>
python scripts/ye.py skill-ir <skill-dir>
python scripts/ye.py trust <skill-dir>
python scripts/ye.py compile <skill-dir> --target openai --target claude --target generic --target vscode
python scripts/ye.py package <skill-dir> --output-dir dist --zip
python scripts/ye.py install-simulate <skill-dir> --package-dir dist
python scripts/ye.py release-check <skill-dir> --package-dir dist
```

命令默认只写入目标目录下的 `reports/`、`dist/` 或用户指定输出；不会把原始遥测写入分发包。所有写入前检查路径，所有外部副作用前报告计划并要求明确授权。

## 输出契约

- 创建：`SKILL.md`、`manifest.json`、`agents/interface.yaml`，并给出结构验证结果。
- 审查：按严重度排序的发现、门禁状态、证据路径、已验证项、缺少证据和建议动作。
- 改进：实际改动文件、保留的行为、正/负回归结果、版本建议和未验证风险；仅提案时不得声称已修改。
- 交付：源摘要、目标兼容矩阵、权限与信任报告、归档摘要、安装模拟和升级结果。

## 资源

- `methods/intent-understanding.md`：中文需求建模和追问规则。
- `methods/trigger-engineering.md`：description、近邻边界和触发评测方法。
- `methods/lifecycle.md`：完整生命周期和成熟度门禁。
- `methods/evidence.md`：证据、隐私和无证据声明规则。
- `methods/portability.md`：Skill IR、目标适配和降级策略。
- `methods/operations.md`：反馈、遥测、漂移和迭代。
- `methods/release.md`：信任、打包、安装、升级和发布检查。
