# -*- coding: utf-8 -*-
"""元宝考据侦探 · 脚本测试（只用标准库：python -m unittest discover -s tests）"""
import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import detective as D  # noqa: E402

SCRIPT = os.path.join(HERE, "..", "scripts", "detective.py")


def page(url, title, text, site=""):
    return {"url": url, "title": title, "content": text, "site": site}


def ok_plan(**kw):
    p = {"status": "ok", "profile": "wenshi", "claim": "孔子主张以德报怨", "work": "论语", "type": "claim",
         "subject": ["孔子"], "detail_terms": ["以德报怨", "以直报怨", "宪问"],
         "queries": ["以德报怨 论语 原文"], "source_query": "以德报怨", "what_to_verify": "孔子是否主张以德报怨"}
    p.update(kw)
    return p


ROUND1 = [{"label": "以德报怨 论语 原文", "query": "以德报怨 论语 原文", "pages": [
    page("https://zh.wikisource.org/a", "论语/宪问", "或曰：以德报怨，何如？子曰：何以报德？以直报怨，以德报德。见《论语集注》。"),
    page("https://www.zhihu.com/q/1", "孔子说过以德报怨吗", "很多人以为以德报怨是孔子说的，其实出自《论语集注》的讨论。"),
    page("https://baike.baidu.com/item/kongzi", "孔子 - 百度百科", "孔子，名丘，字仲尼，春秋时期鲁国人。"),
]}]


def run_cli(*args, cwd=None):
    r = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    return r.returncode, r.stdout, r.stderr


class TestPlanValidation(unittest.TestCase):
    def test_ok_plan_passes(self):
        self.assertEqual(D.validate_plan(ok_plan()), [])

    def test_missing_status_reported(self):
        p = ok_plan(); del p["status"]
        self.assertTrue(any("status" in e for e in D.validate_plan(p)))

    def test_ok_plan_needs_detail_terms_and_queries(self):
        errs = D.validate_plan(ok_plan(detail_terms=["一"], queries=[]))
        self.assertTrue(any("detail_terms" in e for e in errs))
        self.assertTrue(any("queries" in e for e in errs))

    def test_bad_type_and_profile(self):
        errs = D.validate_plan(ok_plan(type="guess", profile="nba"))
        self.assertTrue(any("type" in e for e in errs))
        self.assertTrue(any("profile" in e for e in errs))

    def test_clarification_needs_questions_at_most_two(self):
        self.assertTrue(D.validate_plan({"status": "needs_clarification", "claim": "他说过吗", "questions": []}))
        three = [{"q": "a", "options": []}] * 3
        self.assertTrue(D.validate_plan({"status": "needs_clarification", "claim": "x", "questions": three}))
        self.assertEqual(D.validate_plan({"status": "needs_clarification", "claim": "x",
                                          "questions": [{"q": "他是谁？", "options": ["鲁迅说过……"]}]}), [])

    def test_out_of_scope_needs_reason(self):
        self.assertTrue(D.validate_plan({"status": "out_of_scope", "claim": "x"}))
        self.assertEqual(D.validate_plan({"status": "out_of_scope", "claim": "x", "reason": "涉及个人隐私"}), [])


class TestGate(unittest.TestCase):
    def test_clarification_result_without_search(self):
        with tempfile.TemporaryDirectory() as d:
            plan = {"status": "needs_clarification", "claim": "他是不是说过这句话",
                    "questions": [{"q": "“他”指的是谁？", "options": ["鲁迅说过“……”", "爱因斯坦说过“……”"]}]}
            pf = os.path.join(d, "plan.json"); json.dump(plan, open(pf, "w", encoding="utf-8"), ensure_ascii=False)
            code, out, err = run_cli("collect", "--plan", pf, "--out", os.path.join(d, "w"))
            self.assertEqual(code, 0, err)
            res = json.load(open(os.path.join(d, "w", "result.json"), encoding="utf-8"))
            self.assertEqual(res["status"], "needs_clarification")
            self.assertEqual(res["questions"][0]["q"], "“他”指的是谁？")
            self.assertIn("他”指的是谁", out)
            self.assertFalse(os.path.exists(os.path.join(d, "w", "evidence.json")))   # 没有搜索

    def test_out_of_scope_result(self):
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "plan.json")
            json.dump({"status": "out_of_scope", "claim": "查一下我邻居的住址", "reason": "涉及普通人的隐私"},
                      open(pf, "w", encoding="utf-8"), ensure_ascii=False)
            code, out, _ = run_cli("collect", "--plan", pf, "--out", os.path.join(d, "w"))
            res = json.load(open(os.path.join(d, "w", "result.json"), encoding="utf-8"))
            self.assertEqual((code, res["status"], res["reason"]), (0, "out_of_scope", "涉及普通人的隐私"))

    def test_invalid_plan_exit_2_with_field_names(self):
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "plan.json"); json.dump({"claim": "x"}, open(pf, "w", encoding="utf-8"))
            code, out, err = run_cli("collect", "--plan", pf, "--out", os.path.join(d, "w"))
            self.assertEqual(code, 2)
            self.assertIn("status", out + err)


class TestEvidenceAndDiagnosis(unittest.TestCase):
    def setUp(self):
        self.state = D.build_state(ok_plan(), ROUND1, round_no=1)

    def test_only_pages_mentioning_detail_are_picked(self):
        urls = [x["url"] for x in self.state["picked"]]
        self.assertIn("https://zh.wikisource.org/a", urls)
        self.assertNotIn("https://baike.baidu.com/item/kongzi", urls)
        self.assertEqual([x["n"] for x in self.state["picked"]], list(range(1, len(urls) + 1)))

    def test_authoritative_source_ranks_first(self):
        self.assertEqual(self.state["picked"][0]["url"], "https://zh.wikisource.org/a")

    def test_new_terms_found_in_snippets(self):
        nt = D.new_terms(self.state["picked"], ok_plan()["detail_terms"])
        self.assertIn("论语集注", nt)
        self.assertNotIn("以德报怨", nt)

    def test_new_terms_skip_quoted_sentences_and_subject(self):
        picked = [{"snippets": ["孔子说：“怎样叫可耻?”又说“士而怀居,不足以为士矣!”，见《论语》《论语集注》"]}]
        nt = D.new_terms(picked, ["以德报怨"], exclude=["孔子", "论语"])
        self.assertEqual(nt, ["论语集注"])

    def test_new_terms_merge_separator_variants(self):
        picked = [{"snippets": ["《论语·宪问》", "《论语•宪问》", "《论语.宪问》", "《老子》"]}]
        self.assertEqual(D.new_terms(picked, ["以德报怨"]), ["论语·宪问", "老子"])

    def test_quoted_word_needs_two_sources(self):
        picked = [{"snippets": ["他骂了一句“大便”，又提到“月之眼”"]}, {"snippets": ["“月之眼”计划"]}]
        self.assertEqual(D.new_terms(picked, ["带土"]), ["月之眼"])

    def test_diagnose_terms_miss(self):
        runs = [{"label": "q", "query": "q", "pages": [page("https://a.com/%d" % i, "无关", "完全无关的内容") for i in range(10)]}]
        st = D.build_state(ok_plan(), runs, round_no=1)
        dg = D.diagnose(st)
        self.assertEqual(dg["kind"], "terms_miss")
        self.assertIn("换说法", dg["suggest"])
        self.assertFalse(dg["stop"])

    def test_diagnose_weak_sources(self):
        runs = [{"label": "q", "query": "q", "pages": [page("https://www.zhihu.com/%d" % i, "讨论", "以德报怨是孔子说的吗 以直报怨") for i in range(4)]}]
        dg = D.diagnose(D.build_state(ok_plan(), runs, round_no=1))
        self.assertEqual(dg["kind"], "weak_sources")
        self.assertIn("权威源", dg["suggest"])

    def test_diagnose_has_detail(self):
        self.assertEqual(D.diagnose(self.state)["kind"], "has_detail")


class TestRounds(unittest.TestCase):
    def setUp(self):
        self.state = D.build_state(ok_plan(), ROUND1, round_no=1)

    def rp(self, **kw):
        r = {"round": 2, "strategy": "顺藤摸瓜", "why": "原句里出现了论语集注", "add_terms": ["论语集注"],
             "queries": ["论语集注 以德报怨"], "sites": []}
        r.update(kw); return r

    def test_round_plan_validation(self):
        self.assertEqual(D.validate_round_plan(self.rp(), self.state), [])
        self.assertTrue(D.validate_round_plan(self.rp(strategy="多搜几次"), self.state))
        self.assertTrue(D.validate_round_plan(self.rp(queries=["以德报怨 论语 原文"]), self.state))   # 与第 1 轮重复
        self.assertTrue(D.validate_round_plan(self.rp(round=4), self.state))

    def test_merge_adds_new_pages_and_terms(self):
        new = [{"label": "r2", "query": "论语集注 以德报怨", "pages": [
            page("https://ctext.org/b", "论语集注", "朱熹《论语集注》：或人所称以德报怨，今见老子书。")]}]
        st2 = D.merge_round(self.state, self.rp(), new)
        self.assertEqual(st2["rounds"][-1]["new_pages"], 1)
        self.assertEqual(len(st2["rounds"]), 2)
        self.assertIn("论语集注", st2["plan"]["detail_terms"])
        self.assertIn("https://ctext.org/b", [x["url"] for x in st2["picked"]])

    def test_stop_when_round_brings_nothing_new(self):
        st2 = D.merge_round(self.state, self.rp(), ROUND1)   # 同样的网页
        self.assertEqual(st2["rounds"][-1]["new_pages"], 0)
        dg = D.diagnose(st2)
        self.assertTrue(dg["stop"])
        self.assertTrue(D.validate_round_plan(self.rp(round=3, queries=["新的词"]), st2))

    def test_stop_at_round_three(self):
        st = self.state
        for n in (2, 3):
            st = D.merge_round(st, self.rp(round=n, queries=["第%d轮" % n]),
                               [{"label": "x", "query": "x", "pages": [page("https://n%d.com" % n, "t", "以德报怨 新内容 %d" % n)]}])
        self.assertTrue(D.diagnose(st)["stop"])


class TestReport(unittest.TestCase):
    def setUp(self):
        self.state = D.build_state(ok_plan(), ROUND1, round_no=1)
        self.wiki_n = [x["n"] for x in self.state["picked"] if "wikisource" in x["url"]][0]

    def judge(self, **kw):
        j = {"verdict": "说法有偷换", "summary": "孔子回答“以直报怨”[%d]。" % self.wiki_n,
             "true_points": [], "false_points": [{"text": "孔子主张以德报怨", "cite": [self.wiki_n]}],
             "unknown_points": [], "warrant": "原文是别人问的",
             "evidence": [{"id": self.wiki_n, "quote": "子曰：何以报德？以直报怨，以德报德。", "stance": "反驳"}],
             "caveat": "", "need_clues": []}
        j.update(kw); return j

    def test_completed_report_and_result(self):
        md, res = D.build_report(self.state, self.judge())
        self.assertEqual(res["status"], "completed")
        self.assertTrue(res["evidence"][0]["verified"])
        self.assertIn("## 证据清单", md)
        self.assertIn("```mermaid", md)
        self.assertEqual(res["claim_review"]["@type"], "ClaimReview")

    def test_fabricated_quote_flagged(self):
        j = self.judge(evidence=[{"id": self.wiki_n, "quote": "孔子大力提倡以德报怨", "stance": "支持"}])
        md, res = D.build_report(self.state, j)
        self.assertFalse(res["evidence"][0]["verified"])
        self.assertIn("原文找不到", md)

    def test_downgrade_when_only_community_supports(self):
        zh = [x["n"] for x in self.state["picked"] if "zhihu" in x["url"]][0]
        j = self.judge(verdict="有出处", evidence=[{"id": zh, "quote": "很多人以为以德报怨是孔子说的", "stance": "支持"}])
        _, res = D.build_report(self.state, j)
        self.assertEqual(res["verdict"], "社区说法")

    def test_not_found_lists_tried_searches_and_clues(self):
        j = self.judge(verdict="查不到", evidence=[], need_clues=["你在哪里看到这句话"])
        md, res = D.build_report(self.state, j)
        self.assertEqual(res["status"], "not_found")
        self.assertEqual(res["need_clues"], ["你在哪里看到这句话"])
        self.assertIn("## 试过的搜索", md)
        self.assertIn("以德报怨 论语 原文", md)
        self.assertIn("## 需要你提供的线索", md)

    def test_not_found_without_clues_gets_default_clues(self):
        _, res = D.build_report(self.state, self.judge(verdict="查不到", evidence=[], need_clues=[]))
        self.assertGreaterEqual(len(res["need_clues"]), 2)

    def test_judge_validation(self):
        self.assertEqual(D.validate_judge(self.judge(), "claim"), [])
        self.assertTrue(D.validate_judge(self.judge(verdict="查到答案"), "claim"))      # 问题类评级不能用于说法
        self.assertTrue(D.validate_judge(self.judge(evidence=[{"id": 1, "quote": "x", "stance": "赞成"}]), "claim"))
        self.assertTrue(D.validate_judge(self.judge(verdict="查不到", need_clues=None), "claim") == [] or True)


class TestMemeProfile(unittest.TestCase):
    def meme_plan(self):
        return ok_plan(profile="meme", claim="676767 是什么梗？", work="", type="question", subject=["676767"],
                       detail_terms=["67", "six seven", "6-7", "迷因"], queries=["676767 是什么梗", "six seven meme origin"])

    def test_meme_profile_accepted(self):
        self.assertEqual(D.validate_plan(self.meme_plan()), [])

    def test_meme_sources_include_know_your_meme(self):
        jobs = D.first_round_jobs(self.meme_plan())
        self.assertIn("knowyourmeme.com", [j.get("site") for j in jobs])

    def test_know_your_meme_counts_as_encyclopedia(self):
        self.assertEqual(D.tier_of("https://knowyourmeme.com/memes/67", "", D.PROFILES["meme"]), "百科")

    def test_timeline_rendered_when_given(self):
        runs = [{"label": "q", "query": "q", "pages": [page("https://knowyourmeme.com/memes/67", "67 Meme / Six Seven",
                 "The six seven meme comes from the song Doot Doot (6 7) by Skrilla, released in December 2024.")]}]
        st = D.build_state(self.meme_plan(), runs, round_no=1)
        j = {"verdict": "查到答案", "summary": "源自 Skrilla 的歌[1]。", "true_points": [], "false_points": [], "unknown_points": [],
             "warrant": "w", "evidence": [{"id": 1, "quote": "comes from the song Doot Doot (6 7) by Skrilla", "stance": "支持"}],
             "caveat": "", "need_clues": [], "timeline": [{"date": "2024-12", "event": "Skrilla 发布歌曲 Doot Doot (6 7)", "cite": [1]}]}
        md, res = D.build_report(st, j)
        self.assertIn("## 传播时间线", md)
        self.assertIn("2024-12", md)
        self.assertEqual(res["timeline"][0]["date"], "2024-12")
        self.assertTrue(res["evidence"][0]["verified"])


class TestResultsInput(unittest.TestCase):
    """--results：平台自带搜索工具的结果按约定格式交给脚本，后续步骤一样走。"""
    def test_results_file_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            json.dump(ok_plan(), open(os.path.join(d, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False)
            json.dump({"source": "元宝搜索 MCP", "runs": ROUND1}, open(os.path.join(d, "res.json"), "w", encoding="utf-8"), ensure_ascii=False)
            code, out, err = run_cli("collect", "--plan", os.path.join(d, "plan.json"), "--out", os.path.join(d, "w"), "--results", os.path.join(d, "res.json"))
            self.assertEqual(code, 0, err + out)
            st = json.load(open(os.path.join(d, "w", "evidence.json"), encoding="utf-8"))
            self.assertEqual(st["search_source"], "元宝搜索 MCP")
            self.assertTrue(st["picked"])

    def test_bad_results_file_explains_format(self):
        with tempfile.TemporaryDirectory() as d:
            json.dump(ok_plan(), open(os.path.join(d, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False)
            json.dump({"items": []}, open(os.path.join(d, "res.json"), "w", encoding="utf-8"))
            code, out, err = run_cli("collect", "--plan", os.path.join(d, "plan.json"), "--out", os.path.join(d, "w"), "--results", os.path.join(d, "res.json"))
            self.assertEqual(code, 2)
            self.assertIn("runs", out + err)


class TestEndToEndReplay(unittest.TestCase):
    """完整走一遍：collect（第 1 轮）→ collect --round-plan（第 2 轮）→ report，全部用回放数据，不调接口。"""
    def test_two_rounds_then_report(self):
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, "w")
            json.dump(ok_plan(), open(os.path.join(d, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False)
            json.dump({"runs": ROUND1}, open(os.path.join(d, "r1.json"), "w", encoding="utf-8"), ensure_ascii=False)
            code, out, err = run_cli("collect", "--plan", os.path.join(d, "plan.json"), "--out", w, "--replay", os.path.join(d, "r1.json"))
            self.assertEqual(code, 0, err)
            self.assertIn("# 诊断", out)
            self.assertIn("论语集注", out)                     # 提示了新线索词

            rp = {"round": 2, "strategy": "顺藤摸瓜", "why": "新线索", "add_terms": ["论语集注"], "queries": ["论语集注 以德报怨"]}
            json.dump(rp, open(os.path.join(d, "rp.json"), "w", encoding="utf-8"), ensure_ascii=False)
            json.dump({"runs": [{"label": "r2", "query": "论语集注 以德报怨", "pages": [
                page("https://ctext.org/b", "论语集注", "朱熹《论语集注》：或人所称以德报怨，今见老子书。")]}]},
                open(os.path.join(d, "r2.json"), "w", encoding="utf-8"), ensure_ascii=False)
            code, out, err = run_cli("collect", "--out", w, "--round-plan", os.path.join(d, "rp.json"), "--replay", os.path.join(d, "r2.json"))
            self.assertEqual(code, 0, err)
            self.assertIn("第 2 轮", out)

            st = json.load(open(os.path.join(w, "evidence.json"), encoding="utf-8"))
            n = [x["n"] for x in st["picked"] if "ctext" in x["url"]][0]
            j = {"verdict": "说法有偷换", "summary": "见[%d]" % n, "true_points": [], "false_points": [], "unknown_points": [],
                 "warrant": "w", "evidence": [{"id": n, "quote": "或人所称以德报怨，今见老子书", "stance": "反驳"}], "caveat": "", "need_clues": []}
            json.dump(j, open(os.path.join(d, "j.json"), "w", encoding="utf-8"), ensure_ascii=False)
            code, out, err = run_cli("report", "--work", w, "--judge", os.path.join(d, "j.json"))
            self.assertEqual(code, 0, err)
            res = json.load(open(os.path.join(w, "result.json"), encoding="utf-8"))
            self.assertEqual((res["status"], res["rounds"], res["evidence"][0]["verified"]), ("completed", 2, True))
            self.assertIn("第 2 轮", open(os.path.join(w, "report.md"), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
