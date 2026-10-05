# Evidence schema

所有阶段使用下面的 `records` 来源表。筛选阶段产出它，综合阶段消费它；Router 原样交接，不生成研究结论。

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `source` | string | 必需；来源 URL、文件路径或资料编号，保留页码/段落定位 |
| `claim` | string 或 null | 从来源提取的相关陈述；未读取正文时为 null，不根据标题补写 |
| `support` | string 或 null | 对应原文摘录或可核查依据；不可得时为 null |
| `status` | string | 必需；selected、duplicate、excluded 或 unknown |
| `origin` | string 或 null | 已核查的原始出处；不能确定时为 null，不根据域名猜测独立性 |
| `duplicate_of` | string 或 null | duplicate 指向所保留记录的 source；其他状态为 null |
| `assessment` | object | provenance 为 primary/secondary/unknown；basis 说明已核查依据，limitations 为 string[]；不等于事实真实性评分 |
| `uncertainty` | string[] | 必需；记录来源不可得、筛选条件缺失、冲突等，明确无已知缺口时为 [] |

`source-triage` 的结果为 `{"records": [...], "unresolved": [...]}`。duplicate/excluded 不作为独立支持证据，保留行与原因以供追溯。综合阶段可讨论 unknown，但不能据此宣称事实已验证。

每条 source 标识一个可定位的主张片段。同一文件的不同主张使用不同页码、段落或片段编号；不能复用同一标识代表不同主张。duplicate_of 必须指向表内非 duplicate 记录，不能指向自身或形成循环；同源不同主张不必重复，但不增加独立出处数量。

`evidence-synthesis` 的结果为 `{"conclusions": [...], "records": [...], "unresolved": [...]}`。每个 conclusion 包含 `claim`（string）、`sources`（对应 records.source 的 string[]）、`status`（agreed/conflicted/unknown/attributed）、`support`（string 或 null）和 `uncertainty`（string[]）；结论的引用和缺口必须能回到输入 records。agreed 表示可比的独立来源一致，不表示真理已获证明；attributed 表示仅能归因于一个原始出处。没有可用依据时 conclusions 为 []。

交接状态包含已完成阶段、筛选约束、假设、未解决问题和证据等级。子 Skill 不静默改写来源定位、不删除未知或冲突；需要修正时说明原因并保留原值。前置结果缺少 records 或必要字段时先补齐或报告断点，不自行伪造。
