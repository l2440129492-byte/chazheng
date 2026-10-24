---
name: yuanbao-detective
description: 用元宝搜索查证一句流传的说法或回答一个考据问题，带回逐字核对过的原文证据和 Markdown 报告；查不到会自动换角度补搜，仍查不到就如实说并请用户给线索。适用于二次元原作设定（“这是原作设定吗”“第几话”）；名人名言、诗词典故、汉字字源、碑帖与历史说法（“鲁迅说过吗”“出自哪里”）；以及国内外网络热梗的意思和出处（“676767 是什么梗”）。用户说“查证/考据/辟谣/是真的吗/出处是哪”时使用。
---

# 元宝考据侦探

查得到，信得过。每个结论都要能指回网页原句；查不到就说查不到。

本 Skill 不依赖特定平台或模型。你要做的判断（第 1、4、5 步）都写成固定结构的 JSON，机械步骤（第 2、3、6 步）交给 `scripts/detective.py`。脚本只用 Python 3 标准库，会校验你写的 JSON：哪个字段不对，它会直接说出来，并以退出码 2 结束。所有结构见 `references/schemas.md`。

## 开始前：确定用什么搜索

按优先级选一种，并在开头告诉用户你用的是哪种：

| 情况 | 怎么搜 |
|---|---|
| 能运行 Python，也有元宝搜索 API KEY（环境变量 `TENCENTCLOUD_WSA_APIKEY`，或当前目录 `.env` 里写 `YB_API_KEY=`） | 脚本直接调接口，不需要你搜 |
| 已连接元宝搜索 MCP（工具 `SearchPro`） | 你调工具，把结果写成结果文件，用 `--results` 交给脚本 |
| 只有平台自带的网页搜索工具 | 同上，用 `--results` 交给脚本。报告的「搜索来源」一栏会如实写明用的是什么，不得冒称元宝搜索 |
| 不能运行 Python | 按 `references/judging.md` 末尾的「手工规则」完成摘句、核对和出报告 |

结果文件格式：`{"source":"元宝搜索 MCP","runs":[{"query":"搜索词","site":"站内搜索的站点，可省略","pages":[{"url":"…","title":"…","content":"摘要或正文"}]}]}`

## 流程

```
① 输入检查 ──需要澄清/超出范围──→ 停，输出问题或原因（不搜索）
   │ 可以查
② 第 1 轮搜索 → ③ 摘原句 + 诊断 → ④ 判断
   │ 结论是“查不到/部分查到”，且脚本没有喊停
   └──→ ⑤ 写补搜计划 → 补搜 → 回到 ④（最多到第 3 轮）
⑥ 核对引用，出报告 → status = completed / not_found
```

### ① 输入检查与拆解：写 plan.json

先读 `references/profiles.md`，选领域：二次元原作设定用 `acg`，名言、典故、字源、碑帖、历史说法用 `wenshi`，网络热梗用 `meme`（热梗要中英文一起搜）。

**先判断能不能查**，填 `status` 字段：

| status | 什么时候用 | 还要填 |
|---|---|---|
| `needs_clarification` | 没有可核实的点（「摩根这个角色怎么样」）、指代不清（「他说过这句话吗」）、主体有歧义且推断不出来（只说了「Archer」）、观点题（「谁最强」） | `questions`：1 到 2 个问题，每个附 2 到 3 个可以直接拿去查的改写 |
| `out_of_scope` | 时政；涉及普通人的信息（家庭、住址、隐私） | `reason` |
| `ok` | 可以查。能从上下文推断出主体时，不要追问，把推断写进 `assumption` | 下面的拆解字段 |

`status` 为 `ok` 时，再填拆解字段：
- `type`：要核实真假的说法填 `claim`；要找答案的问题填 `question`。
- `detail_terms`：8 到 12 个短词（2 到 8 字），用来在原文里逐字定位句子。中文、日文、英文写法都给，拆成单个概念，不要拼成长短语。**要核实的是细节，不是主体**：只搜人物名，只会搜回整页人物词条。
- `queries`：3 到 4 条搜索词。至少一条找原始出处，至少一条找辟谣、争议或误传。
- `source_query`：2 到 4 个词，用于站内搜索。
- `clues`：用户补充过线索时填进来。

### ② 第 1 轮搜索 + ③ 摘原句与诊断

```bash
python scripts/detective.py collect --plan plan.json --out work                       # 脚本自己调元宝搜索
python scripts/detective.py collect --plan plan.json --out work --results r1.json     # 用 MCP 或平台搜索的结果
```

`status` 不是 `ok` 时，脚本不搜索，直接写 `work/result.json`，你把问题或原因转告用户，到此结束。

用 `--results` 时，搜索词要和 plan 一致：plan 里的每条 query 都搜一次（每次 20 条结果）；再对 `profiles.md` 里该领域的每个知识源各做一次站内搜索，搜索词用 `source_query`。

脚本输出三部分：
- 搜索概况
- 诊断：为什么可能查不到、建议的补搜策略、原句里出现的新线索词、能不能继续补搜
- 带编号的摘录 `[1]…[14]`

### ④ 判断：写 judge.json

先读 `references/judging.md`。**只能依据摘录下结论，不能用自己的记忆补事实**，哪怕你确信自己知道答案。结论是「查不到」或「部分查到」时，`need_clues` 里写明需要用户提供哪类线索。

### ⑤ 查不到就补搜（最多补到第 3 轮）

条件：判断结论是「查不到」或「部分查到」，**并且**诊断里没有写「不要再补搜」。满足时，写 `round_plan.json`：

```json
{"round": 2, "strategy": "顺藤摸瓜", "why": "原句里出现了《论语集注》", "add_terms": ["论语集注"], "queries": ["论语集注 以德报怨"], "sites": []}
```

- 策略照诊断的建议选：`换说法` / `放宽` / `反向` / `权威源` / `顺藤摸瓜`。
- 每种策略什么时候用，见 `judging.md`。
- 不能重复已经搜过的词。

```bash
python scripts/detective.py collect --out work --round-plan round_plan.json [--results r2.json]
```

然后回到第 ④ 步，对新的摘录重新判断。以下任一情况出现就停，不要硬凑结论：
- 脚本拒绝执行（上一轮没有带来新网页，或者已到第 3 轮）
- 判断出了结论（不再是查不到或部分查到）

### ⑥ 核对并出报告

```bash
python scripts/detective.py report --work work --judge judge.json
```

脚本会做三件事：
- **逐字核对**：每条引用必须真的出现在对应编号的摘录里，对不上的标红，不算依据。
- **结论保护**：支持结论的原句全部来自论坛时，自动降为「社区说法」。
- 写出 `work/report.md` 和 `work/result.json`。

## 交付：按 result.json 的 status 回复用户

| status | 回复用户什么 |
|---|---|
| `completed` | 展示 report.md。至少包括评级、结论、证据表，并保留所有来源链接 |
| `not_found` | 展示 report.md，明确说「查不到」，列出试过的搜索，再把 `need_clues` 问给用户。用户补充后，把线索写进 plan.json 的 `clues`，从第 ① 步重来 |
| `needs_clarification` | 只问 `questions`，并附上改写建议，不要给结论 |
| `out_of_scope` | 只说 `reason` |

如果报告里有引用被标红，要明确告诉用户这几句已经不算证据。

## 不做的事

- 不碰时政，不查普通人的信息。
- 碑帖真伪、断代这类学术争议：只并列各方观点和出处，不替学界下结论。
- 名言只在语录站、鸡汤文里出现的，算「未找到原始出处」。
- 不为了凑出答案无限搜索，也不放宽「必须引用原句」的规则。

## 自检

```bash
python -m unittest discover -s tests      # 35 个测试，全部用回放数据，不调接口
```
