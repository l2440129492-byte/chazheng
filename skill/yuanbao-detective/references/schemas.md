# 输入输出契约

任何平台、任何模型调用本 Skill，都按这里的 JSON 结构交换数据。脚本会校验结构：缺字段或取值不对时，它会报出具体是哪个字段，退出码为 2。

## 1. plan.json：输入检查 + 拆解（由 AI 写）

```json
{
  "status": "ok",
  "profile": "wenshi",
  "claim": "孔子主张以德报怨",
  "work": "论语",
  "type": "claim",
  "subject": ["孔子", "论语"],
  "detail_terms": ["以德报怨", "以直报怨", "何以报德", "宪问"],
  "queries": ["孔子 以德报怨 原文 出处", "以德报怨 误传 不是孔子"],
  "source_query": "论语 以德报怨",
  "what_to_verify": "孔子是否主张以德报怨",
  "assumption": "",
  "clues": ""
}
```

| 字段 | 必填 | 取值 |
|---|---|---|
| status | 是 | `ok` 可以查 / `needs_clarification` 需要澄清 / `out_of_scope` 超出范围 |
| questions | status 为 needs_clarification 时必填 | 1 到 2 个，格式 `{"q":"问题","options":["建议写法1","建议写法2"]}` |
| reason | status 为 out_of_scope 时必填 | 一句话说明为什么不查 |
| profile | status 为 ok 时必填 | `acg`、`wenshi` 或 `meme` |
| claim | 是 | 用户原话 |
| type | status 为 ok 时必填 | `claim` 说法 / `question` 问题 |
| detail_terms | status 为 ok 时必填 | 至少 3 个短词 |
| queries | status 为 ok 时必填 | 1 到 4 条 |
| subject、work、source_query、what_to_verify | 建议填 | |
| assumption | 选填 | 用户没回应澄清、按最合理理解去查时，写明按什么理解查的 |
| clues | 选填 | 用户补充的线索：在哪里看到、什么版本、原文措辞 |

**什么时候必须是 needs_clarification**

- 没有可核实的点，例如「摩根这个角色怎么样」
- 指代不清，例如「他是不是说过这句话」
- 主体有歧义，并且上下文推断不出来，例如只说了「Archer 的射程」
- 观点题，例如「Archer 是不是最强」。这种情况要在 options 里给出可以查证的事实型改写

**什么时候必须是 out_of_scope**：时政，或者涉及普通人的信息（家庭关系、住址、隐私）。

## 2. round_plan.json：补搜计划（由 AI 写，第 2、3 轮用）

```json
{
  "round": 2,
  "strategy": "顺藤摸瓜",
  "why": "第一轮原句里出现了《卡卡西外传》，可能是这件事的出处",
  "add_terms": ["卡卡西外传"],
  "queries": ["卡卡西外传 带土 面具"],
  "sites": []
}
```

- `strategy` 只能取：`换说法`、`放宽`、`反向`、`权威源`、`顺藤摸瓜`。
- `queries` 要写 1 到 4 条，并且不能和之前各轮完全重复。
- `sites` 选填，填了就在这些站点里做站内搜索。
- 最多补搜到第 3 轮。上一轮如果没带来任何新网页，脚本会拒绝继续补搜。

## 3. judge.json：判断（由 AI 写）

```json
{
  "verdict": "说法有偷换",
  "summary": "……[2][3]",
  "true_points": [{"text": "…", "cite": [2]}],
  "false_points": [{"text": "…", "cite": [3]}],
  "unknown_points": ["…"],
  "warrant": "一句话依据",
  "evidence": [{"id": 3, "quote": "逐字原句", "stance": "反驳"}],
  "caveat": "",
  "need_clues": [],
  "timeline": [{"date": "2024-12", "event": "…", "cite": [9]}]
}
```

- `verdict`：说法类取 `有出处 / 说法有偷换 / 说法有分歧 / 查不到`；问题类取 `查到答案 / 部分查到 / 来源有分歧 / 查不到`。
- `evidence[].stance` 取 `支持 / 反驳 / 相关`。
- `timeline`：选填，热梗这类有传播过程的内容使用，只写摘录里有的时间和事件；报告里会出现「传播时间线」一节。
- `need_clues`：verdict 为 `查不到` 或 `部分查到` 时必填，写明需要用户提供哪类线索，例如「在哪里看到的」「是漫画还是动画」。

## 4. result.json：最终输出（由脚本写，交给调用方）

```json
{
  "status": "completed",
  "verdict": "说法有偷换",
  "rating": 2,
  "summary": "……",
  "claim": "孔子主张以德报怨",
  "rounds": 1,
  "evidence": [{"id": 3, "quote": "…", "stance": "反驳", "url": "https://…", "site": "…", "verified": true}],
  "need_clues": [],
  "questions": [],
  "reason": "",
  "report_path": "work/report.md",
  "claim_review": {"@type": "ClaimReview"}
}
```

`status` 一共四种，调用方按状态决定下一步：

| status | 调用方该做什么 |
|---|---|
| completed | 把 report.md 展示给用户 |
| not_found | 照样展示报告；再把 need_clues 问给用户，用户补充后，把线索填进 clues 字段重新查 |
| needs_clarification | 把 questions 问给用户，拿到回答后重写 plan.json |
| out_of_scope | 告诉用户 reason，不要再搜 |
