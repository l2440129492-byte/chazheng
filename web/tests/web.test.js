// 网页版查证引擎测试：node --test tests/web.test.js
// 从 index.html 里取出 engine / profiles / detective 三段脚本，在 vm 里跑纯函数，不调接口。
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs"), path = require("path"), vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const pick = id => html.match(new RegExp(`<script id="${id}">([\\s\\S]*?)</script>`))[1];
const ctx = { console, URL };
vm.createContext(ctx);
vm.runInContext(pick("engine") + pick("profiles") + pick("detective") + "\nthis.ENGINE=ENGINE;this.PROFILES=PROFILES;this.DETECTIVE=DETECTIVE;", ctx);
const D = ctx.DETECTIVE, P = ctx.PROFILES.wenshi;

const page = (url, title, text) => ({ url, title, content: text, site: "" });
const okPlan = (o = {}) => Object.assign({ status: "ok", type: "claim", claim: "孔子主张以德报怨", subject: ["孔子"],
  detail_terms: ["以德报怨", "以直报怨", "宪问"], queries: ["以德报怨 论语 原文"], what_to_verify: "x" }, o);
const R1 = [{ label: "以德报怨 论语 原文", query: "以德报怨 论语 原文", pages: [
  page("https://zh.wikisource.org/a", "论语/宪问", "或曰：以德报怨，何如？子曰：何以报德？以直报怨，以德报德。见《论语集注》。"),
  page("https://www.zhihu.com/q/1", "孔子说过以德报怨吗", "很多人以为以德报怨是孔子说的，其实出自《论语集注》的讨论。"),
  page("https://baike.baidu.com/item/kongzi", "孔子 - 百度百科", "孔子，名丘，字仲尼，春秋时期鲁国人。")] }];

test("输入检查：可以查 / 需要澄清 / 超出范围", () => {
  assert.deepEqual([...D.validatePlan(okPlan())], []);
  assert.ok(D.validatePlan({ status: "needs_clarification", claim: "他说过吗", questions: [] }).length);
  assert.deepEqual([...D.validatePlan({ status: "needs_clarification", claim: "x", questions: [{ q: "他是谁？", options: [] }] })], []);
  assert.ok(D.validatePlan({ status: "out_of_scope", claim: "x" }).length);
  assert.ok(D.validatePlan(okPlan({ detail_terms: ["一"] })).length);
});

test("只摘提到细节的网页，权威源排第一，编号连续", () => {
  const st = D.buildState(okPlan(), R1, P);
  const urls = st.picked.map(x => x.url);
  assert.equal(urls[0], "https://zh.wikisource.org/a");
  assert.ok(!urls.includes("https://baike.baidu.com/item/kongzi"));
  assert.deepEqual(st.picked.map(x => x.n), urls.map((_, i) => i + 1));
});

test("新线索词：要书名专名，不要引号对白和主体词，合并分隔符变体", () => {
  const picked = [{ snippets: ["孔子说：“怎样叫可耻?”见《论语》《论语·宪问》《论语•宪问》《论语集注》《老子》"] }];
  assert.deepEqual([...D.newTerms(picked, ["以德报怨"], ["孔子", "论语"])], ["论语·宪问", "论语集注", "老子"]);
});

test("引号里的词要在两个来源里出现才算线索", () => {
  const picked = [{ snippets: ["他骂了一句“大便”，又提到“月之眼”"] }, { snippets: ["“月之眼”计划"] }];
  assert.deepEqual([...D.newTerms(picked, ["带土"], [])], ["月之眼"]);
});

test("诊断：搜索词不对 / 来源太弱 / 已有细节", () => {
  const miss = D.buildState(okPlan(), [{ label: "q", query: "q", pages: Array.from({ length: 10 }, (_, i) => page("https://a.com/" + i, "无关", "完全无关")) }], P);
  assert.equal(D.diagnose(miss).kind, "terms_miss");
  assert.ok(D.diagnose(miss).suggest.includes("换说法"));
  const weak = D.buildState(okPlan(), [{ label: "q", query: "q", pages: [0, 1, 2].map(i => page("https://www.zhihu.com/" + i, "讨论", "以德报怨是孔子说的吗 以直报怨")) }], P);
  assert.equal(D.diagnose(weak).kind, "weak_sources");
  assert.equal(D.diagnose(D.buildState(okPlan(), R1, P)).kind, "has_detail");
});

test("补搜：合并新网页、加细节词；没新网页就停；第 3 轮封顶", () => {
  const st = D.buildState(okPlan(), R1, P);
  const rp = { round: 2, strategy: "顺藤摸瓜", why: "w", add_terms: ["论语集注"], queries: ["论语集注 以德报怨"] };
  assert.deepEqual([...D.validateRoundPlan(rp, st)], []);
  assert.ok(D.validateRoundPlan(Object.assign({}, rp, { queries: ["以德报怨 论语 原文"] }), st).length);
  assert.ok(D.validateRoundPlan(Object.assign({}, rp, { strategy: "多搜几次" }), st).length);
  const st2 = D.mergeRound(st, rp, [{ label: "r2", query: "论语集注 以德报怨", pages: [page("https://ctext.org/b", "论语集注", "朱熹《论语集注》：或人所称以德报怨，今见老子书。")] }], P);
  assert.equal(st2.rounds.at(-1).new_pages, 1);
  assert.ok(st2.plan.detail_terms.includes("论语集注"));
  assert.ok(st2.picked.some(x => x.url === "https://ctext.org/b"));
  const same = D.mergeRound(st, rp, R1, P);
  assert.equal(same.rounds.at(-1).new_pages, 0);
  assert.equal(D.diagnose(same).stop, true);
  let s3 = st;
  for (const n of [2, 3]) s3 = D.mergeRound(s3, Object.assign({}, rp, { round: n, queries: ["第" + n + "轮"] }), [{ label: "x", query: "x", pages: [page("https://n" + n + ".com", "t", "以德报怨 新内容 " + n)] }], P);
  assert.equal(D.diagnose(s3).stop, true);
});

test("该不该补搜：只有查不到/部分查到且没触发停止时才补", () => {
  const st = D.buildState(okPlan(), R1, P);
  assert.equal(D.needMoreRounds({ verdict: "查不到" }, st), true);
  assert.equal(D.needMoreRounds({ verdict: "部分查到" }, st), true);
  assert.equal(D.needMoreRounds({ verdict: "说法有偷换" }, st), false);
  const same = D.mergeRound(st, { round: 2, strategy: "反向", why: "", queries: ["别的词"] }, R1, P);
  assert.equal(D.needMoreRounds({ verdict: "查不到" }, same), false);
});

test("查不到时：默认线索至少两条", () => {
  assert.ok(D.cluesFor({ verdict: "查不到", need_clues: [] }).length >= 2);
  assert.deepEqual([...D.cluesFor({ verdict: "查不到", need_clues: ["在哪看到的"] })], ["在哪看到的"]);
  assert.deepEqual([...D.cluesFor({ verdict: "有出处", need_clues: [] })], []);
});

test("热梗领域：Know Your Meme 当百科、站内搜索里有它", () => {
  const M = ctx.PROFILES.meme;
  assert.ok(M, "要有 meme 领域");
  assert.ok(M.sources.some(s => s.site === "knowyourmeme.com"));
  const st = D.buildState(Object.assign(okPlan(), {claim:"676767 是什么梗", detail_terms:["67","six seven","迷因"], type:"question"}),
    [{label:"q", query:"q", pages:[page("https://knowyourmeme.com/memes/67", "67 Meme", "The six seven meme comes from a song")]}], M);
  assert.equal(st.picked[0].tier, "百科");
});

test('媒体：相关来源页无说明配图保留，标识横幅过滤；多选作品逐个匹配', () => {
  const picked=[{title:'孔子与论语',snippets:['以直报怨'],pics:[{origin_url:'https://x.test/page.jpg'},{origin_url:'https://x.test/logo.jpg',caption:'网站logo'},{origin_url:'https://x.test/portrait.jpg',caption:'孔子画像'}]}];
  const result=D.collectMedia(picked,[],{subject:[],detail_terms:['以直报怨']},'孔子、论语',P);
  assert.equal(result.picked[0].pics.length,2);
  assert.equal(result.picked[0].pics[0].contextOnly,true);
  assert.equal(result.picked[0].pics[1].contextOnly,false);
});

test('媒体：视频按正文匹配，支持BV和av，且不引入无关视频', () => {
  const result=D.collectMedia([], [
    {url:'https://www.bilibili.com/video/BV1234567890',title:'经典解读',content:'孔子 以直报怨'},
    {url:'https://www.bilibili.com/video/av12345',title:'论语解读'},
    {url:'https://www.bilibili.com/video/BV0000000000',title:'无关内容'}
  ],{subject:['孔子','论语'],detail_terms:[]},'',P);
  assert.equal(result.videos.length,2);
  assert.equal(result.videos[1].aid,'12345');
});
