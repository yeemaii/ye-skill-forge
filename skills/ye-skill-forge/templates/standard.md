---
# {skill_name}

## 目的 / Purpose
{job_description}

## 根问题与使用者 / Root problem and user
- 根问题：{root_problem}
- 使用者：{target_user}
- 用户结果：{user_result}
- 可复用做法：{reusable_method}

## 何时使用 / When to use
当请求符合上面的职责、输入和触发边界时使用；相邻但职责不同的请求按下方边界处理。

## 触发与近邻边界 / Routing boundary
触发示例：
{trigger_examples}

不要触发的近邻请求：
{near_neighbors}

## 输入 / Inputs
{input_description}

## 必要材料与工具 / Materials and tools
- 材料：{materials}
- 工具：{tools}
- 权限：{permissions}

## Workflow / 工作流
{workflow_steps}

## 输出契约 / Output contract
格式：{output_format}

```{output_format_example}
{output_example}
```

## 边界 / Boundaries
{exclusions}

## 质量检查 / Quality checks
{success_signals}

## 失败处理 / Failure handling
缺少必要信息时，只追问会改变结果的细节。标明假设，并区分未知信息与已验证事实。

## 资源 / Resources
{references}

## 组合契约 / Composition contract
{composition_contract}
