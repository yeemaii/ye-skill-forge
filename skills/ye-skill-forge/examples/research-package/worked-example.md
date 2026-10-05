# 贯穿筛选和综合的案例

## 输入

研究问题：同一城市、同一周，方案甲是否降低平均通勤时间？纳入条件：该城市该周的对照记录；保留有支持及反证的资料。

- A#p1：原始记录 A 表示对照为 30 分钟、甲为 25 分钟；未说明样本量。
- B#p2：明确转载 A#p1，同样写 30 与 25 分钟，无新增数据。
- C#p3：独立原始记录 C，城市与周次相同，表示对照为 30、甲为 35 分钟；未说明抽样方法。
- D#p4：另一个城市的去年数据，表示甲减少 8 分钟。
- E#title：仅提供标题“甲提高出行效率”，正文不可得。

## 筛选结果

```json
{
  "records": [
    {"source":"A#p1","claim":"甲组平均通勤25分钟，对照30分钟","support":"对照30，甲25","status":"selected","origin":"A","duplicate_of":null,"assessment":{"provenance":"primary","basis":"用户提供的原始对照记录","limitations":["样本量未知"]},"uncertainty":["样本量未知"]},
    {"source":"B#p2","claim":"甲组平均通勤25分钟，对照30分钟","support":"转载A：对照30，甲25","status":"duplicate","origin":"A","duplicate_of":"A#p1","assessment":{"provenance":"secondary","basis":"正文明确标注转载A","limitations":["没有新增数据"]},"uncertainty":[]},
    {"source":"C#p3","claim":"甲组平均通勤35分钟，对照30分钟","support":"对照30，甲35","status":"selected","origin":"C","duplicate_of":null,"assessment":{"provenance":"primary","basis":"用户提供的独立原始记录","limitations":["抽样方法未知"]},"uncertainty":["抽样方法未知"]},
    {"source":"D#p4","claim":"甲减少8分钟","support":"另一城市去年数据：减少8分钟","status":"excluded","origin":"D","duplicate_of":null,"assessment":{"provenance":"primary","basis":"提供的数据记录","limitations":["城市和时间不满足纳入条件"]},"uncertainty":["排除：城市和时间不同"]},
    {"source":"E#title","claim":null,"support":null,"status":"unknown","origin":null,"duplicate_of":null,"assessment":{"provenance":"unknown","basis":"只有标题","limitations":["正文不可得"]},"uncertainty":["不能从标题推导研究结果"]}
  ],
  "unresolved":["A样本量未知","C抽样方法未知","E正文不可得"]
}
```

## 综合结果

conclusions 中保留一项 conflicted 判断：关于甲是否降低通勤时间，A#p1 支持下降、C#p3 支持上升，现有资料无法解释差异。sources 指向这两条记录，support 分别列出 30 到 25 和 30 到 35 的依据，uncertainty 保留方法缺口。

返回上述原始 records 和 unresolved；B 不能作为第二份支持票，D 不符合纳入范围，E 不证明事实。进一步结论需要核查样本和测量条件。若只剩 A，则结论为 attributed；若没有可用记录，则 conclusions 为 []，说明没有可用证据。
