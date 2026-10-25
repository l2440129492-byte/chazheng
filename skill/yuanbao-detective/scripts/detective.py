# -*- coding: utf-8 -*-
"""
元宝考据侦探 · 机械步骤脚本（只用 Python 标准库）

三个动作，中间的“输入检查/拆解”“补搜计划”“判断”由宿主 AI 按 SKILL.md 完成，数据结构见 references/schemas.md：

  1) 第 1 轮   python detective.py collect --plan plan.json --out work
     先检查 plan.status：需要澄清/超出范围时不搜索，直接写 result.json；可以查时用元宝搜索全网 + 权威知识源站内搜索，
     摘出提到细节的原句并编号，输出诊断（为什么可能查不到、建议的补搜策略、原句里出现的新线索词）。
  2) 补搜     python detective.py collect --out work --round-plan round_plan.json
     第 2、3 轮。上一轮没带来新网页或已到第 3 轮时拒绝执行。
  3) 出报告   python detective.py report --work work --judge judge.json
     逐字核对每条引用、按来源级别做结论保护，写 report.md 和 result.json（status：completed / not_found）。

密钥：环境变量 TENCENTCLOUD_WSA_APIKEY 或 YB_API_KEY（元宝搜索控制台创建的服务 API KEY）。
调试：collect 加 --replay 旧结果.json 可不调接口，直接复用保存过的搜索结果。
"""
import argparse, json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "https://api.wsa.cloud.tencent.com/SearchPro"
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 领域配置
PROFILES = {
    "acg": {
        "name": "二次元原作",
        "sources": [("萌娘百科", "moegirl.org.cn", None), ("Bangumi 番组计划", "bgm.tv", None),
                    ("Mooncell（FGO 中文维基）", "fgo.wiki", r"fate|fgo|型月|月姬|空之境界|魔法使之夜")],
        "tier_rules": [], "tier_label": {},
    },
    "wenshi": {
        "name": "名言·文史",
        "sources": [("维基文库", "zh.wikisource.org", None), ("中国哲学书电子化计划", "ctext.org", None),
                    ("汉典", "zdic.net", None), ("中国互联网联合辟谣平台", "piyao.org.cn", None)],
        "tier_rules": [("官方", r"wikisource\.org|ctext\.org|zdic\.net|guoxuedashi|shuowen|dpm\.org\.cn|chnmuseum\.cn|luxunmuseum|cssn\.cn|cass\.(cn|net)|piyao\.org\.cn|nlc\.cn|npm\.gov\.tw|shuge\.org"),
                       ("问答农场", r"mingyan|juzi|geyan|yulu|ju111|wenzhangba|siandian|zuowen|lizhi|jitang|wenku\.baidu|doc88|book118|360doc")],
        "tier_label": {"官方": "原典/权威"},
    },
    "meme": {
        "name": "热梗",
        "sources": [("Know Your Meme", "knowyourmeme.com", None), ("萌娘百科", "moegirl.org.cn", None), ("百度百科", "baike.baidu.com", None)],
        "tier_rules": [("百科", r"knowyourmeme\.com|wikiwand\.com|urbandictionary\.com|jikipedia\.com"),
                       ("问答农场", r"baijiahao\.baidu|wenku\.baidu|ergngevd|vvikipedla|chped\.com|gtranslate\.net")],
        "tier_label": {},
    },
}

BASE_TIERS = [
    ("官方", r"typemoon\.(com|jp)|fate-go\.jp|fgo\.bilibiligame|aniplex|shueisha|jujutsukaisen\.jp|toei-anim|kadokawa|bandainamco"),
    ("社区", r"forum|bbs\.|spacebattles|sufficientvelocity|reddit\.com|vsbattles|comic-vs-anime|vs-battle|deathbattle|tieba\.baidu|nga\.cn"),
    ("百科", r"moegirl\.org|baike\.baidu|baike\.sogou|baike\.so\.com|baike\.haosou|baike\.com|fandom\.com|wikipedia\.org|fgo\.wiki|wiki\.biligame|huijiwiki|bangumi\.tv|bgm\.tv|wikiwiki\.jp|atwiki"),
    ("问答农场", r"zhidao|wenda|/ask/|yidianzhidao|it224|xunmei365|lygyc|acgnla|fragtop|coboak|fmyly|hiwaifu|grokipedia|chatbox|jingyan|wukong|iask|wenwen|zybang"),
    ("社区", r"bilibili\.com|zhihu\.com|lofter|weibo\.(com|cn)|douban\.com|xiaohongshu|taptap|toutiao\.com|douyin|ixigua|hupu"),
    ("媒体", r"\.gov\.cn|\.edu\.cn|gmw\.cn|cssn\.cn|news|qq\.com/rain|new\.qq\.com|sohu\.com|163\.com|sina\.com|ifeng|thepaper|cctv|xinhua|news\.cn|chinadaily|people\.com"),
]
TIER_W = {"官方": 3, "百科": 2, "媒体": 1.2, "社区": 1.2, "其他": 1, "问答农场": 0.4}


def tier_of(url, site, prof):
    u = url or ""
    for name, rx in prof["tier_rules"] + BASE_TIERS:
        if re.search(rx, u, re.I):
            return name
    if re.search(r"知道|问答|问问|经验", site or ""):
        return "问答农场"
    if re.search(r"百科|wiki", site or "", re.I):
        return "百科"
    return "其他"


# ---------------------------------------------------------------- 搜索
def api_key():
    import credentials
    k, _ = credentials.resolve_key()
    if not k:
        sys.exit("没有找到元宝搜索密钥：请运行 python3 scripts/credentials.py setup，通过本地输入页配置（不要在聊天中粘贴密钥）")
    return k


def search(body, key):
    req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json; charset=UTF-8", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = json.loads(e.read().decode("utf-8", "ignore") or "{}")
    resp = raw.get("Response", raw)
    if "Error" in resp:
        raise RuntimeError("%s: %s" % (resp["Error"].get("Code"), resp["Error"].get("Message")))
    pages = []
    for p in resp.get("Pages", []):
        try:
            pages.append(json.loads(p) if isinstance(p, str) else p)
        except Exception:
            pass
    return pages


# ---------------------------------------------------------------- 找原句
SYN = [["公里", "km", "千米", "キロ"], ["咒文", "咏唱", "詠唱", "呪文", "咒语", "启动语"], ["射程", "攻击范围", "狙击范围"]]


def expand(terms):
    out = []
    for t in terms:
        t = str(t).strip()
        if not t:
            continue
        out.append(t)
        for g in SYN:
            hit = next((x for x in g if x.lower() in t.lower()), None)
            if hit:
                out += [re.sub(re.escape(hit), x, t, flags=re.I) for x in g]
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(公里|千米|km)$", t, re.I)
        if m:
            out += [m.group(1) + u for u in ("公里", "千米", "km", "KM", " km", "キロ")]
    seen, res = set(), []
    for x in out:
        if x.lower() not in seen:
            seen.add(x.lower()); res.append(x)
    return res


def snippets(text, terms, max_n=3):
    t = re.sub(r"\s+", " ", text or "")
    low = t.lower()
    hits = []
    for term in terms:
        k = term.lower(); i = low.find(k)
        while i >= 0 and len(hits) < 12:
            hits.append(i); i = low.find(k, i + len(k))
    hits.sort()
    spans = []
    for i in hits:
        s, e = max(0, i - 90), min(len(t), i + 130)
        ps = t.rfind("。", 0, i)
        if ps > s: s = ps + 1
        pe = t.find("。", i)
        if 0 < pe < e: e = pe + 1
        if spans and s <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], e); continue
        spans.append([s, e])
    return [t[a:b].strip() for a, b in spans[:max_n]]



# ---------------------------------------------------------------- 契约校验
PROFILE_IDS = set(PROFILES)
STATUSES = ("ok", "needs_clarification", "out_of_scope")
STRATEGIES = ("换说法", "放宽", "反向", "权威源", "顺藤摸瓜")
CLAIM_VERDICTS = ("有出处", "说法有偷换", "说法有分歧", "查不到")
Q_VERDICTS = ("查到答案", "部分查到", "来源有分歧", "查不到")
STANCES = ("支持", "反驳", "相关")
MAX_ROUNDS = 3
DEFAULT_CLUES = ["你是在哪里看到这个说法的（帖子、视频、书名）", "是哪个版本（漫画还是动画、哪条路线、哪个译本）", "原文的大概措辞，或者它原本是哪种语言"]


def validate_plan(p):
    e = []
    if not isinstance(p, dict):
        return ["plan.json 必须是一个 JSON 对象"]
    st = p.get("status")
    if st not in STATUSES:
        e.append("status 必须是 %s 之一" % " / ".join(STATUSES))
    if not str(p.get("claim") or "").strip():
        e.append("claim 必填：用户原话")
    if st == "needs_clarification":
        qs = p.get("questions")
        if not isinstance(qs, list) or not 1 <= len(qs) <= 2 or not all(isinstance(q, dict) and q.get("q") for q in qs):
            e.append("questions 必须是 1 到 2 个 {\"q\":\"问题\",\"options\":[建议写法]}")
    if st == "out_of_scope" and not str(p.get("reason") or "").strip():
        e.append("reason 必填：说明为什么不查")
    if st == "ok":
        if p.get("profile") not in PROFILE_IDS:
            e.append("profile 必须是 %s 之一" % " / ".join(sorted(PROFILE_IDS)))
        if p.get("type") not in ("claim", "question"):
            e.append("type 必须是 claim 或 question")
        if not isinstance(p.get("detail_terms"), list) or len([t for t in p["detail_terms"] if str(t).strip()]) < 3:
            e.append("detail_terms 至少 3 个短词")
        q = p.get("queries")
        if not isinstance(q, list) or not 1 <= len([x for x in q if str(x).strip()]) <= 4:
            e.append("queries 必须是 1 到 4 条搜索词")
    return e


def all_queries(state):
    return [q["query"] for r in state["rounds"] for q in r["queries"]]


def validate_round_plan(rp, state):
    e = []
    expect = len(state["rounds"]) + 1
    if rp.get("round") != expect:
        e.append("round 应为 %d" % expect)
    if expect > MAX_ROUNDS:
        e.append("最多补搜到第 %d 轮，已到上限" % MAX_ROUNDS)
    if rp.get("strategy") not in STRATEGIES:
        e.append("strategy 必须是 %s 之一" % " / ".join(STRATEGIES))
    q = [x for x in (rp.get("queries") or []) if str(x).strip()]
    if not 1 <= len(q) <= 4:
        e.append("queries 必须是 1 到 4 条")
    dup = [x for x in q if x in all_queries(state)]
    if dup:
        e.append("queries 和之前的搜索完全重复：%s" % "、".join(dup))
    dg = diagnose(state)
    if dg["stop"] and expect <= MAX_ROUNDS:
        e.append("不应继续补搜：%s" % dg["stop_reason"])
    return e


def validate_judge(j, qtype):
    e = []
    allowed = Q_VERDICTS if qtype == "question" else CLAIM_VERDICTS
    if j.get("verdict") not in allowed:
        e.append("verdict 必须是 %s 之一（%s类）" % (" / ".join(allowed), "问题" if qtype == "question" else "说法"))
    if not str(j.get("summary") or "").strip():
        e.append("summary 必填")
    for i, ev in enumerate(j.get("evidence") or []):
        if not isinstance(ev, dict) or not str(ev.get("quote") or "").strip():
            e.append("evidence[%d].quote 必填" % i)
            continue
        try:
            int(ev.get("id"))
        except Exception:
            e.append("evidence[%d].id 必须是摘录编号" % i)
        if ev.get("stance") not in STANCES:
            e.append("evidence[%d].stance 必须是 支持 / 反驳 / 相关" % i)
    if j.get("need_clues") is not None and not isinstance(j.get("need_clues"), list):
        e.append("need_clues 必须是列表")
    return e


def gate_result(plan):
    st = plan["status"]
    return {"status": st, "claim": plan.get("claim"), "verdict": None, "rating": None, "summary": "",
            "rounds": 0, "evidence": [], "need_clues": [], "questions": plan.get("questions") or [],
            "reason": plan.get("reason") or "", "report_path": None, "claim_review": None}


# ---------------------------------------------------------------- 证据整理（每轮都对全部网页重算）
def _key(url):
    return re.sub(r"^https?://(www\.|m\.|wap)?", "", re.sub(r"[?#].*$", "", url))


def _absorb(raw, runs, round_no):
    """把一轮搜索结果并入原始网页池，返回新增网页数。"""
    new = 0
    for r in runs:
        for p in r.get("pages") or []:
            url = (p or {}).get("url")
            if not url:
                continue
            k = _key(url)
            if k in raw:
                if r.get("label") not in raw[k]["found_by"]:
                    raw[k]["found_by"].append(r.get("label"))
                continue
            new += 1
            raw[k] = {"url": url, "title": p.get("title") or "", "site": p.get("site") or "", "date": (p.get("date") or "")[:10],
                      "text": "。".join([p.get("title") or "", p.get("content") or p.get("passage") or ""]),
                      "found_by": [r.get("label")], "round": round_no}
    return new


def _pick(state):
    prof = PROFILES[state["plan"]["profile"]]
    terms = expand(state["plan"]["detail_terms"])
    allp = []
    for x in state["raw"].values():
        sn = snippets(x["text"], terms)
        allp.append({"title": x["title"], "url": x["url"], "site": x["site"], "date": x["date"], "round": x["round"],
                     "tier": tier_of(x["url"], x["site"], prof), "snippets": sn,
                     "term_hits": sum(1 for t in terms if t.lower() in x["text"].lower()), "found_by": x["found_by"]})
    ranked = sorted([x for x in allp if x["snippets"]], key=lambda x: -(x["term_hits"] * TIER_W[x["tier"]] + len(x["found_by"])))
    dedup, sig = [], set()
    for x in ranked:
        k = re.sub(r"\s|\[[^\]]*\]", "", "".join(x["snippets"]))[:80]
        if k in sig:
            continue
        sig.add(k); dedup.append(x)
    picked = dedup[:14]
    for i, x in enumerate(picked, 1):
        x["n"] = i
    state["picked"] = picked
    state["others"] = [{"title": x["title"], "url": x["url"], "site": x["site"]} for x in allp if not x["snippets"]][:40]
    state["stats"] = {"total": len(allp), "detail": len(dedup)}
    return state


def _round_entry(n, strategy, why, runs, new_pages):
    return {"round": n, "strategy": strategy, "why": why, "new_pages": new_pages,
            "queries": [{"query": r.get("query"), "site": r.get("site"), "count": len(r.get("pages") or []), "error": r.get("error")} for r in runs]}


def build_state(plan, runs, round_no=1):
    state = {"plan": dict(plan, detail_terms=list(plan["detail_terms"])), "profile": plan["profile"], "raw": {}, "rounds": [],
             "time": time.strftime("%Y-%m-%d %H:%M")}
    n = _absorb(state["raw"], runs, round_no)
    state["rounds"].append(_round_entry(round_no, "初搜", "按拆解出的搜索词全网搜索，并在权威知识源站内搜索", runs, n))
    return _pick(state)


def merge_round(state, rp, runs):
    st = json.loads(json.dumps(state, ensure_ascii=False))
    for t in rp.get("add_terms") or []:
        if t and t not in st["plan"]["detail_terms"]:
            st["plan"]["detail_terms"].append(t)
    n = _absorb(st["raw"], runs, rp["round"])
    st["rounds"].append(_round_entry(rp["round"], rp.get("strategy"), rp.get("why") or "", runs, n))
    return _pick(st)


TITLE_RX = re.compile(r"《([^》]{2,20})》|「([^」]{2,12})」|“([^”]{2,12})”")


def new_terms(picked, existing, limit=6, exclude=()):
    """原句里出现、但还没用过的书名/篇名/专名，用于“顺藤摸瓜”补搜。引号里的整句对白不算。"""
    ex = [str(t).lower() for t in list(existing) + list(exclude) if str(t).strip()]
    cnt, quoted = {}, set()
    for i, x in enumerate(picked):
        for s in x["snippets"]:
            for m in TITLE_RX.finditer(s):
                t = re.sub(r"\s*[•・.．]\s*", "·", next(g for g in m.groups() if g).strip())
                if re.search(r"[,，。.!！?？;；:：、]", t) and not m.group(1):
                    continue                       # 引号里的句子，不是专名
                if t.lower() in ex or any(t.lower() in e or (e in t.lower() and len(t) - len(e) < 2) for e in ex):
                    continue
                if not m.group(1):
                    quoted.add(t)
                cnt.setdefault(t, set()).add(i)
    # 书名号里的专名出现一次就算；引号里的词要在两个不同来源里出现才算，避免把随口的对白当线索
    keep = [(t, len(v)) for t, v in cnt.items() if t not in quoted or len(v) >= 2]
    return [t for t, _ in sorted(keep, key=lambda kv: -kv[1])][:limit]


def diagnose(state):
    total, detail = state["stats"]["total"], state["stats"]["detail"]
    strong = [x for x in state["picked"] if x["tier"] in ("官方", "百科")]
    if detail == 0 or (total >= 10 and detail / total < 0.1):
        kind, suggest = "terms_miss", ["换说法", "放宽", "反向"]
        why = "搜到的网页几乎都没提到细节词，多半是搜索词或细节词的说法不对"
    elif not strong:
        kind, suggest = "weak_sources", ["权威源", "反向", "顺藤摸瓜"]
        why = "提到细节的只有社区、问答或其他弱来源，缺官方或百科原文"
    else:
        kind, suggest = "has_detail", ["顺藤摸瓜", "反向"]
        why = "已有权威来源谈到细节；如果判断后仍答不上，多半是方向偏了，可以顺着原句里的新线索继续"
    stop, reason = False, ""
    if len(state["rounds"]) >= MAX_ROUNDS:
        stop, reason = True, "已到第 %d 轮上限" % MAX_ROUNDS
    elif len(state["rounds"]) > 1 and state["rounds"][-1]["new_pages"] == 0:
        stop, reason = True, "上一轮没有带来任何新网页，再搜也是同一批结果"
    return {"kind": kind, "why": why, "suggest": suggest, "new_terms": new_terms(state["picked"], state["plan"]["detail_terms"],
                                   exclude=list(state["plan"].get("subject") or []) + [state["plan"].get("work") or ""]),
            "stop": stop, "stop_reason": reason, "rounds": len(state["rounds"])}


# ---------------------------------------------------------------- 搜索执行
class ResultsFormatError(Exception):
    pass


RESULTS_FORMAT = ('结果文件格式：{"source":"用的什么搜索","runs":[{"query":"搜索词","site":"站内搜索的站点，可省略",'
                  '"pages":[{"url":"…","title":"…","content":"网页摘要或正文"}]}]}')


def load_results(path):
    old = json.load(open(path, encoding="utf-8"))
    runs = old.get("runs") or old.get("raw_runs") if isinstance(old, dict) else None
    if not isinstance(runs, list) or not all(isinstance(r, dict) and isinstance(r.get("pages", []), list) for r in runs):
        raise ResultsFormatError("搜索结果文件缺少 runs 列表。" + RESULTS_FORMAT)
    src = old.get("source") or "回放的元宝搜索结果"
    return [{"label": r.get("label") or r.get("query"), "query": r.get("query"), "site": r.get("site"), "pages": r.get("pages") or []}
            for r in runs], src


def run_jobs(jobs, replay=None):
    if replay:
        return load_results(replay)[0]
    key = api_key()
    def one(j):
        try:
            return {"label": j["label"], "query": j["body"]["Query"], "site": j.get("site"), "pages": search(j["body"], key)}
        except Exception as ex:
            return {"label": j["label"], "query": j["body"]["Query"], "site": j.get("site"), "pages": [], "error": str(ex)}
    with ThreadPoolExecutor(max_workers=4) as ex:   # 旗舰版限 5 QPS
        return list(ex.map(one, jobs))


def first_round_jobs(plan):
    prof = PROFILES[plan["profile"]]
    claim, work = plan.get("claim", ""), plan.get("work", "") or ""
    queries = [q for q in plan["queries"] if str(q).strip()][:4]
    base = ((work + " ") if work and work not in claim else "") + claim
    if plan.get("clues"):
        base = base + " " + plan["clues"]
    if base not in queries:
        queries.append(base)
    src_q = plan.get("source_query") or " ".join(plan["detail_terms"][:3])
    jobs = [{"label": q, "body": {"Query": q, "Mode": 0, "Cnt": 20}} for q in queries]
    for label, site, when in prof["sources"]:
        if when and not re.search(when, claim + " " + work, re.I):
            continue
        jobs.append({"label": "知识源·" + label, "site": site, "body": {"Query": ((work + " ") if work else "") + src_q, "Site": site, "Mode": 0, "Cnt": 10}})
    return jobs


def round_jobs(rp):
    jobs = [{"label": q, "body": {"Query": q, "Mode": 0, "Cnt": 20}} for q in rp["queries"] if str(q).strip()]
    for s in rp.get("sites") or []:
        jobs.append({"label": "站内·" + s, "site": s, "body": {"Query": rp["queries"][0], "Site": s, "Mode": 0, "Cnt": 10}})
    return jobs


# ---------------------------------------------------------------- 输出
def save_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def print_collect(state):
    prof = PROFILES[state["profile"]]
    tl = prof["tier_label"]
    r = state["rounds"][-1]
    print("# 第 %d 轮搜索（%s）" % (r["round"], r["strategy"]))
    for q in r["queries"]:
        print("- 元宝搜索「%s」%s：%s" % (q["query"], "（站内 " + q["site"] + "）" if q.get("site") else "", "出错 " + q["error"] if q.get("error") else "%d 条" % q["count"]))
    print("- 本轮新增网页 %d 个；累计 %d 个网页，%d 个提到细节\n" % (r["new_pages"], state["stats"]["total"], state["stats"]["detail"]))
    dg = diagnose(state)
    print("# 诊断")
    print("- 情况：%s" % dg["why"])
    print("- 如果判断后仍是“查不到/部分查到”，建议补搜策略：%s" % "、".join(dg["suggest"]))
    print("- 原句里出现的新线索词：%s" % ("、".join(dg["new_terms"]) or "无"))
    print("- %s\n" % ("不要再补搜：" + dg["stop_reason"] if dg["stop"] else "还可以补搜（最多到第 %d 轮）" % MAX_ROUNDS))
    print("# 摘录（判断时只能引用这里的原句，id 用方括号里的编号）")
    for x in state["picked"]:
        print("[%d] 来源：%s（%s）%s\n%s\n" % (x["n"], x["site"] or x["url"], tl.get(x["tier"], x["tier"]), x["url"], " …… ".join(x["snippets"])))
    if not state["picked"]:
        print("（没有任何网页原句提到这个细节。）")


def collect_cmd(args):
    out = args.out
    if args.replay:
        try:
            source = load_results(args.replay)[1]
        except ResultsFormatError as ex:
            print(str(ex)); return 2
    else:
        source = "元宝搜索 API"
    if args.round_plan:
        st_path = os.path.join(out, "evidence.json")
        if not os.path.exists(st_path):
            print("找不到 %s：请先跑第 1 轮 collect --plan" % st_path); return 2
        state = json.load(open(st_path, encoding="utf-8"))
        rp = json.load(open(args.round_plan, encoding="utf-8"))
        errs = validate_round_plan(rp, state)
        if errs:
            print("round_plan.json 有问题：\n- " + "\n- ".join(errs)); return 2
        state = merge_round(state, rp, run_jobs(round_jobs(rp), args.replay))
    else:
        plan = json.load(open(args.plan, encoding="utf-8"))
        errs = validate_plan(plan)
        if errs:
            print("plan.json 有问题：\n- " + "\n- ".join(errs)); return 2
        if plan["status"] != "ok":
            res = gate_result(plan)
            save_json(os.path.join(out, "result.json"), res)
            if plan["status"] == "needs_clarification":
                print("# 需要先问清楚（没有搜索）")
                for q in res["questions"]:
                    print("- %s" % q["q"])
                    for o in q.get("options") or []:
                        print("  · 可以这样问：%s" % o)
            else:
                print("# 不查（没有搜索）\n%s" % res["reason"])
            return 0
        state = build_state(plan, run_jobs(first_round_jobs(plan), args.replay), round_no=1)
    state["search_source"] = source if not args.round_plan else state.get("search_source", source)
    save_json(os.path.join(out, "evidence.json"), state)
    print_collect(state)
    return 0


RATING = {"有出处": 5, "查到答案": 5, "部分查到": 3, "社区说法": 3, "说法有偷换": 2, "说法有分歧": 3, "来源有分歧": 3, "查不到": 1}


def norm(s):
    return re.sub(r"[\s\"“”'‘’。，,.!！?？…·「」『』()（）\-—:：;；]", "", s or "").lower()


def mm(t, n):
    return re.sub(r"\s+", " ", re.sub(r"[\"'`<>{}\[\]()|#;&\n\r]", " ", str(t or ""))).strip()[:n]


def wrap(t, w):
    return "<br/>".join(t[i:i + w] for i in range(0, len(t), w))


def build_report(state, judge):
    j = json.loads(json.dumps(judge, ensure_ascii=False))
    plan, picked = state["plan"], state["picked"]
    prof = PROFILES[state["profile"]]
    tl = lambda t: prof["tier_label"].get(t, t)
    by_n = {x["n"]: x for x in picked}
    isq = plan.get("type") == "question"

    for e in j.get("evidence") or []:
        src = by_n.get(int(e.get("id") or 0))
        e["verified"] = bool(src and norm(e.get("quote"))[:40] and norm(e.get("quote"))[:40] in norm("".join(src["snippets"])))
    evs = j.get("evidence") or []
    bad = [e for e in evs if not e["verified"]]

    if j.get("verdict") in ("有出处", "查到答案"):
        sup = [by_n[int(e["id"])] for e in evs if e["verified"] and e.get("stance") == "支持"]
        if sup and not any(s["tier"] in ("官方", "百科") for s in sup):
            j["original_verdict"] = j["verdict"]; j["verdict"] = "社区说法"
            j["caveat"] = "支持这个结论的原句全部来自论坛或同人站，没有找到官方资料或百科原文。" + (j.get("caveat") or "")

    not_found = j["verdict"] == "查不到"
    clues = [c for c in (j.get("need_clues") or []) if str(c).strip()]
    if not_found and not clues:
        clues = list(DEFAULT_CLUES)
    lv = RATING.get(j["verdict"], 1)
    rounds = state["rounds"]

    L = ["# 查证报告：%s" % plan.get("claim", ""), "",
         "| 评级 | %s %s |" % (j["verdict"], "●" * lv + "○" * (5 - lv)), "|---|---|",
         "| 领域 | %s |" % prof["name"], "| 类型 | %s |" % ("问题（找答案）" if isq else "说法（核实真假）"),
         "| 相关 | %s |" % (plan.get("work") or "未指定"), "| 搜索轮次 | %d 轮 |" % len(rounds), "| 搜索来源 | %s |" % state.get("search_source", "元宝搜索 API"), "| 查证时间 | %s |" % state["time"], ""]
    if plan.get("assumption"):
        L += ["> 按这个理解查的：%s" % plan["assumption"], ""]
    L += ["## 结论", j.get("summary", ""), ""]
    if j.get("caveat"):
        L += ["> %s%s" % (j["caveat"], "（原判“%s”，因来源级别不够已自动降级）" % j["original_verdict"] if j.get("original_verdict") else ""), ""]
    if bad:
        L += ["> ⚠ 有 %d 条引用在原文中找不到，已标出，不计入结论依据。" % len(bad), ""]

    def pts(arr):
        out = []
        for p in arr or []:
            if isinstance(p, dict):
                out.append("- %s%s" % (p.get("text", ""), " " + "".join("[%s]" % c for c in p.get("cite") or []) if p.get("cite") else ""))
            else:
                out.append("- %s" % p)
        return out or ["- 无"]
    tl_items = [t for t in (j.get("timeline") or []) if isinstance(t, dict) and t.get("event")]
    if tl_items:
        L += ["## 传播时间线", ""]
        for t in tl_items:
            L.append("- **%s** %s%s" % (t.get("date") or "时间不详", t["event"], " " + "".join("[%s]" % c for c in t.get("cite") or []) if t.get("cite") else ""))
        L.append("")
    L += ["## 拆开来看", "", "**原文能证实的**", *pts(j.get("true_points")), "",
          "**%s**" % ("和流传说法不一样的" if isq else "原文不支持的"), *pts(j.get("false_points")), "",
          "**没查到的**", *pts(j.get("unknown_points")), ""]

    if evs:
        L += ["## 证据清单", "", "| 来源 | 原句 | 立场 | 网站 | 核对 |", "|---|---|---|---|---|"]
        for e in evs:
            s = by_n.get(int(e.get("id") or 0), {})
            L.append("| [%s](%s) | 「%s」 | %s | %s（%s） | %s |" % (e.get("id"), s.get("url", ""), str(e.get("quote", "")).replace("|", "｜"),
                     e.get("stance"), s.get("site", "?"), tl(s.get("tier", "?")), "原文一致" if e["verified"] else "⚠ 原文找不到"))
        L.append("")

    G = ["flowchart TB", 'C["%s：%s"]' % ("问题" if isq else "说法", wrap(mm(plan.get("claim"), 48), 16)), 'V{{"结论：%s"}}' % mm(j["verdict"], 12)]
    done = set()
    good = [e for e in evs if e["verified"]]
    for i, e in enumerate(good):
        s = by_n[int(e["id"])]
        sid = "S%d" % s["n"]
        if sid not in done:
            done.add(sid); G.append('%s(["[%d] %s<br/>%s"])' % (sid, s["n"], mm(s["site"] or s["title"], 14), tl(s["tier"])))
        G += ['E%d["「%s」"]' % (i, wrap(mm(e.get("quote"), 42), 14)), "%s --> E%d" % (sid, i), "E%d -->|%s| C" % (i, e.get("stance"))]
    if not good:
        G.append('N["没有可引用的原句"] -.-> C')
    G.append('C -->|"%s"| V' % wrap("依据：" + mm(j.get("warrant") or "见证据", 40), 16))
    L += ["## 论证图", "", "```mermaid", *G, "```", ""]

    if not_found:
        L += ["## 试过的搜索", ""]
        for r in rounds:
            for q in r["queries"]:
                L.append("- 第 %d 轮：「%s」%s，%s" % (r["round"], q["query"], "（站内 " + q["site"] + "）" if q.get("site") else "", "出错" if q.get("error") else "%d 条" % q["count"]))
        L.append("")
    if clues and j["verdict"] in ("查不到", "部分查到"):
        L += ["## 需要你提供的线索", "", "补充下面任意一条，就能带着线索再查一次：", *["- %s" % c for c in clues], ""]

    L += ["## 调查过程", "", "- 要%s：%s" % ("回答" if isq else "核实", plan.get("what_to_verify", "")), "- 细节词：%s" % "、".join(plan.get("detail_terms", []))]
    if plan.get("clues"):
        L.append("- 用户补充的线索：%s" % plan["clues"])
    for r in rounds:
        L.append("- 第 %d 轮（%s）：%s；新增网页 %d 个" % (r["round"], r["strategy"], r["why"], r["new_pages"]))
        for q in r["queries"]:
            L.append("  - 元宝搜索「%s」%s：%s" % (q["query"], "（站内 " + q["site"] + "）" if q.get("site") else "", "出错" if q.get("error") else "%d 条" % q["count"]))
    L += ["- 共 %d 个网页，%d 个提到细节，取前 %d 个交给判断" % (state["stats"]["total"], state["stats"]["detail"], len(picked)),
          "- 引用 %d 句，原文核对通过 %d 句" % (len(evs), len(evs) - len(bad)), "", "## 来源列表（编号与上文一致）", ""]
    for x in picked:
        L.append("%d. [%s](%s) · %s · %s" % (x["n"], x["title"] or x["url"], x["url"], tl(x["tier"]), x["site"]))
    cr = {"@context": "https://schema.org", "@type": "ClaimReview", "datePublished": time.strftime("%Y-%m-%d"),
          "claimReviewed": plan.get("claim"), "author": {"@type": "Organization", "name": "元宝考据侦探"},
          "reviewRating": {"@type": "Rating", "ratingValue": lv, "bestRating": 5, "worstRating": 1, "alternateName": j["verdict"]},
          "itemReviewed": {"@type": "Claim", "appearance": [{"@type": "CreativeWork", "url": by_n[int(e["id"])]["url"]} for e in good]}}
    L += ["", "<details><summary>ClaimReview（schema.org 事实核查标准格式）</summary>", "", "```json", json.dumps(cr, ensure_ascii=False, indent=1), "```", "</details>", ""]

    res = {"status": "not_found" if not_found else "completed", "verdict": j["verdict"], "rating": lv, "summary": j.get("summary", ""),
           "claim": plan.get("claim"), "rounds": len(rounds),
           "evidence": [{"id": e.get("id"), "quote": e.get("quote"), "stance": e.get("stance"), "url": by_n.get(int(e.get("id") or 0), {}).get("url"),
                         "site": by_n.get(int(e.get("id") or 0), {}).get("site"), "verified": e["verified"]} for e in evs],
           "need_clues": clues if j["verdict"] in ("查不到", "部分查到") else [], "questions": [], "reason": "", "timeline": tl_items,
           "report_path": None, "claim_review": cr}
    return "\n".join(L), res


def report_cmd(args):
    st_path = os.path.join(args.work, "evidence.json")
    if not os.path.exists(st_path):
        print("找不到 %s：请先跑 collect" % st_path); return 2
    state = json.load(open(st_path, encoding="utf-8"))
    j = json.load(open(args.judge, encoding="utf-8"))
    errs = validate_judge(j, state["plan"].get("type"))
    if errs:
        print("judge.json 有问题：\n- " + "\n- ".join(errs)); return 2
    md, res = build_report(state, j)
    rp = os.path.join(args.work, "report.md")
    open(rp, "w", encoding="utf-8").write(md)
    res["report_path"] = rp
    save_json(os.path.join(args.work, "result.json"), res)
    print(md)
    print("\n（报告：%s；结果：%s；status=%s；核对通过 %d / %d 句）" % (rp, os.path.join(args.work, "result.json"), res["status"],
          sum(1 for e in res["evidence"] if e["verified"]), len(res["evidence"])), file=sys.stderr)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="元宝考据侦探")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("collect", help="第 1 轮用 --plan；补搜用 --round-plan")
    a.add_argument("--plan"); a.add_argument("--round-plan"); a.add_argument("--out", default="work"); a.add_argument("--results", "--replay", dest="replay", help="用平台自带搜索工具（或元宝搜索 MCP）的结果代替脚本直接调接口")
    b = sub.add_parser("report"); b.add_argument("--work", default="work"); b.add_argument("--judge", required=True)
    args = ap.parse_args()
    if args.cmd == "collect" and not (args.plan or args.round_plan):
        ap.error("collect 需要 --plan（第 1 轮）或 --round-plan（补搜）")
    sys.exit(collect_cmd(args) if args.cmd == "collect" else report_cmd(args))
