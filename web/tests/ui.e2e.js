// 界面端到端测试：用 Playwright 打开 index.html，模拟本地服务、元宝搜索和模型返回。node tests/ui.e2e.js
const {chromium} = require("playwright"); const path = require("path"); const assert = require("assert/strict");
const file = "file://" + path.join(__dirname, "..", "index.html");
const page = (url, title, text) => JSON.stringify({url, title, content: text, site: ""});

async function withPage(llmReplies, searchFn, fn){
  const b = await chromium.launch(); const p = await b.newPage();
  const errors = []; p.on("pageerror", e => errors.push(e.message));
  let llmCalls = 0, searchCalls = 0;
  await p.route("**/*", route => {
    const u = route.request().url();
    if (u.includes("/api/status")) return route.fulfill({contentType:"application/json", body: JSON.stringify({key:true, llm:true, model:"mock", calls:0})});
    if (u.includes("/api/llm")) { const r = llmReplies[Math.min(llmCalls++, llmReplies.length-1)]; return route.fulfill({contentType:"application/json", body: JSON.stringify({choices:[{message:{content: JSON.stringify(r)}}]})}); }
    if (u.includes("/api/search")) { searchCalls++; const body = JSON.parse(route.request().postData()); return route.fulfill({contentType:"application/json", body: JSON.stringify({Response:{Pages: searchFn(body), Version:"standard"}})}); }
    if (u.includes("/api/save")) return route.fulfill({contentType:"application/json", body: '{"file":"reports\\\\x.md"}'});
    if (u.startsWith("file:")) return route.continue();
    return route.fulfill({status:200, body:""});   // 字体、mermaid 等外部资源
  });
  // file:// 下 fetch("/api/...") 会指向 file:///api/...，这里统一改到一个假 http 源
  await p.addInitScript(() => { const f = window.fetch; window.fetch = (u, o) => f(String(u).startsWith("/api") ? "http://mock.local" + u : u, o); });
  await p.goto(file); await p.waitForTimeout(300);
  await fn(p, () => ({llmCalls, searchCalls}), errors);
  await b.close();
}

(async () => {
  // 1. 输入检查：需要澄清 → 不搜索，显示问题和改写
  await withPage([{status:"needs_clarification", claim:"x", questions:[{q:"“他”指的是谁？", options:["鲁迅说过“不在沉默中爆发……”","爱因斯坦说过“疯狂就是……”"]}]}], () => [], async (p, stats, errors) => {
    await p.fill("#claim", "他是不是说过这句话"); await p.click("#go"); await p.waitForSelector(".gate-opt");
    const txt = await p.textContent("#result");
    assert.match(txt, /先问清楚/); assert.match(txt, /“他”指的是谁/);
    assert.equal(stats().searchCalls, 0, "需要澄清时不应搜索");
    assert.deepEqual(errors, []);
    console.log("✓ 需要澄清：不搜索，显示问题和可点的改写");
  });

  // 2. 超出范围
  await withPage([{status:"out_of_scope", claim:"x", reason:"涉及普通人的隐私，不查。"}], () => [], async (p, stats) => {
    await p.fill("#claim", "帮我查邻居的住址"); await p.click("#go"); await p.waitForSelector(".case");
    assert.match(await p.textContent("#result"), /涉及普通人的隐私/); assert.equal(stats().searchCalls, 0);
    console.log("✓ 超出范围：不搜索，说明原因");
  });

  // 3. 查不到 → 自动补搜 → 仍查不到 → 显示线索框；补充线索后带着线索重查
  const plan = {status:"ok", type:"claim", subject:["鲁迅"], detail_terms:["沉默","爆发","灭亡"], queries:["鲁迅 沉默 爆发 原文"], source_query:"沉默 爆发", what_to_verify:"出处"};
  const notFound = {verdict:"查不到", summary:"没有原句谈到。", evidence:[], true_points:[], false_points:[], unknown_points:["出处"], warrant:"无", caveat:"", need_clues:["你在哪里看到的"]};
  const round = {strategy:"换说法", why:"换成原文措辞", add_terms:["纪念刘和珍君"], queries:["纪念刘和珍君 沉默"], sites:[]};
  let n = 0;
  await withPage([plan, notFound, round, notFound, Object.assign({}, round, {queries:["第三轮的词"]}), notFound, plan, notFound],
    body => [page("https://x.com/" + (n++), "讨论帖", "有人说沉默和爆发这句话出处不明")], async (p, stats, errors) => {
    await p.fill("#claim", "不在沉默中爆发就在沉默中灭亡是鲁迅说的"); await p.click("#go");
    await p.waitForSelector("#clueInput", {timeout: 8000});
    const txt = await p.textContent("#result");
    assert.match(txt, /还差一点线索/); assert.match(txt, /你在哪里看到的/);
    assert.match(txt, /第 2 轮（换说法）/); assert.match(txt, /第 3 轮/);
    assert.doesNotMatch(txt, /第 4 轮/, "最多 3 轮");
    const before = stats().searchCalls;
    await p.fill("#clueInput", "在一篇高中语文课文里看到的"); await p.click("#clueGo");
    await p.waitForFunction(() => document.querySelector("#result").textContent.includes("用户补充的线索"), null, {timeout: 8000});
    assert.ok(stats().searchCalls > before, "带线索重查应再次搜索");
    assert.deepEqual(errors, []);
    console.log("✓ 查不到：自动补搜到第 3 轮封顶，显示线索框；补充线索后重新搜索，报告里写明线索");
  });
  // 4. 一个提到细节的网页都没有：程序直接判查不到（不问模型），再让模型出补搜计划
  let m = 0;
  await withPage([plan, round, notFound, plan, notFound], body => [page("https://y.com/" + (m++), "无关", m > 4 ? "沉默 爆发 灭亡 原文出自纪念刘和珍君" : "完全无关")], async (p, stats, errors) => {
    await p.fill("#claim", "某句话是鲁迅说的"); await p.click("#go");
    await p.waitForSelector(".case", {timeout: 8000});
    const txt = await p.textContent("#result");
    assert.match(txt, /第 2 轮（换说法）/, "第一轮零命中也要补搜");
    assert.deepEqual(errors, []);
    console.log("✓ 第一轮零命中：直接进入补搜，第 2 轮搜到了提到细节的网页");
  });
  console.log("全部通过");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
