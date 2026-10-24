# chazheng · 元宝考据侦探

查得到，信得过：把一句流传的说法交给它，它会用**元宝搜索**找原文，只拿原文说话；查不到会换个角度补搜，仍然查不到就说查不到。

这是 WaytoAGI 1024 超能 Coding 周末「侦探赛道」的参赛作品。

## 能查什么

| 领域 | 例子 |
|---|---|
| 二次元原作 | Archer 的狙击范围是 4 公里以内？异闻带摩根是什么身份？ |
| 名言·文史 | 孔子主张以德报怨？《兰亭序》真迹陪葬昭陵？ |
| 热梗 | 676767 是什么梗？“I am inevitable”为什么成了梗？ |

## 怎么做到「信得过」

1. **输入检查**：说法太模糊、指代不清，或者是观点题，先问清楚；涉及时政或个人隐私的，不查。
2. **元宝搜索**：全网搜索，加上权威知识源的站内搜索（维基文库、汉典、萌娘百科、Know Your Meme 等）。
3. **找原句**：只留下真正谈到这个细节的句子，不让整页人物词条淹没证据。
4. **判断**：模型只能引用原句下结论，不能凭记忆补充。
5. **核对**：程序把模型的每句引用拿回原文逐字比对，对不上的标红，不算证据；支持结论的原句全部来自论坛时，自动降级。
6. **补搜**：查不到时诊断原因，换说法、换权威源、顺着新线索再搜，最多 3 轮；仍查不到就请用户提供线索。

报告格式参照 schema.org 的 ClaimReview（事实核查标准格式），论证图按 Toulmin 论证模型绘制。

## 目录

```
web/        本地网页版：index.html（前端和查证引擎）+ server.ps1（PowerShell 本地服务，无需安装任何东西）
skill/      Skill 版：任何 AI 平台、任何模型都能调用；脚本只用 Python 标准库
tools/      元宝搜索覆盖面探测脚本
docs/       实测报告样例
HANDOFF.md  交接文档：现状、架构、决策、待办，接手前先读它
```

## 快速开始

**网页版（Windows）**
1. 把 `web/.env.example` 复制成 `web/.env`，填入元宝搜索 API KEY 和 DeepSeek key。
2. 双击 `web/启动考据侦探.bat`，浏览器打开 `http://localhost:8765`。

**Skill 版**：见 `skill/yuanbao-detective/SKILL.md`。

**测试**
```bash
python -m unittest discover -s skill/yuanbao-detective/tests   # 35 个
node --test web/tests/web.test.js                              # 9 个
node web/tests/ui.e2e.js                                       # 4 个，需要 playwright
```
