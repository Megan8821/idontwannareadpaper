"""Unit tests for build_site.py.

    python3 -m unittest discover        # or: python3 test_build_site.py

Standard library only, and no browser -- these cover the data layer, which the
browser checks in verify_site.py cannot reach. verify_site.py answers "is the
rendered site right"; this answers "is the data sound and does each piece render
what it should", which is where a mistyped subfield or a missing section hides.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site as bs


def entry(**over):
    """A valid entry; keyword arguments override or, set to None, remove a field."""
    e = {
        "arxiv_id": "2608.00001",
        "title_en": "A Title",
        "title_zh": "一個標題",
        "authors": "A. Author, B. Author",
        "submitted": "2026-08-01",
        "categories": "cs.SD",
        "subfield": "generative",
        "deep": False,
        "fulltext_read": True,
        "why_zh": "理由",
        "why_en": "reason",
        "sections": {k: {"zh": "中文" + k, "en": "english " + k} for k in bs.SECTION_KEYS},
    }
    for k, v in over.items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    return e


class DataDir:
    """Context manager giving a temp data dir plus a write(name, blob) helper."""

    def __enter__(self):
        self.path = tempfile.mkdtemp()
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)

    def write(self, name, blob):
        with open(os.path.join(self.path, name), "w", encoding="utf-8") as f:
            if isinstance(blob, str):
                f.write(blob)
            else:
                json.dump(blob, f, ensure_ascii=False)

    def day(self, date, entries):
        self.write("%s.json" % date, {"date": date, "entries": entries})


class TestLoadDays(unittest.TestCase):
    def test_groups_by_date_and_attaches_read_date(self):
        with DataDir() as d:
            d.day("2026-08-01", [entry(arxiv_id="1"), entry(arxiv_id="2")])
            d.day("2026-08-02", [entry(arxiv_id="3")])
            days, problems = bs.load_days(d.path)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(days), ["2026-08-01", "2026-08-02"])
        self.assertEqual(len(days["2026-08-01"]), 2)
        # every entry has to know its own date, since a topic page has no date heading
        self.assertTrue(all(e["read_date"] == "2026-08-01" for e in days["2026-08-01"]))
        self.assertEqual(days["2026-08-02"][0]["read_date"], "2026-08-02")

    def test_unreadable_file_is_reported_not_skipped(self):
        # A stray comma used to drop the whole day while the build still passed.
        with DataDir() as d:
            d.day("2026-08-01", [entry()])
            d.write("2026-08-02.json", '{"date": "2026-08-02", "entries": [},]}')
            days, problems = bs.load_days(d.path)
        self.assertNotIn("2026-08-02", days)
        self.assertTrue(any("2026-08-02.json" in p and "cannot be read" in p for p in problems),
                        problems)

    def test_date_field_must_match_filename(self):
        with DataDir() as d:
            d.write("2026-08-02.json", {"date": "2026-08-09", "entries": [entry()]})
            _, problems = bs.load_days(d.path)
        self.assertTrue(any("filename" in p for p in problems), problems)

    def test_empty_and_malformed_containers_are_reported(self):
        with DataDir() as d:
            d.write("2026-08-01.json", {"date": "2026-08-01", "entries": []})
            d.write("2026-08-02.json", {"date": "2026-08-02", "entries": {"a": 1}})
            d.write("2026-08-03.json", [1, 2, 3])
            _, problems = bs.load_days(d.path)
        joined = " | ".join(problems)
        self.assertIn("no entries", joined)
        self.assertIn("must be a list", joined)
        self.assertIn("must be an object", joined)


class TestValidateDays(unittest.TestCase):
    def check(self, *entries):
        days = {}
        for i, e in enumerate(entries):
            date = "2026-08-%02d" % (i + 1)
            e["read_date"] = date
            days[date] = [e]
        return bs.validate_days(days)

    def test_valid_entry_has_no_problems(self):
        self.assertEqual(self.check(entry()), [])

    def test_real_data_is_valid(self):
        """The committed data must satisfy the validator, or CI is red for real."""
        root = os.path.dirname(os.path.abspath(__file__))
        days, problems = bs.load_days(os.path.join(root, "data"))
        self.assertEqual(problems, [])
        self.assertEqual(bs.validate_days(days), [])
        self.assertTrue(days, "expected committed data to load")

    def test_each_required_field_is_required(self):
        for field in bs.REQUIRED_FIELDS:
            with self.subTest(field=field):
                problems = self.check(entry(**{field: None}))
                self.assertTrue(any(field in p for p in problems), problems)

    def test_blank_field_counts_as_missing(self):
        problems = self.check(entry(title_en="   "))
        self.assertTrue(any("title_en" in p for p in problems), problems)

    def test_unknown_subfield_is_caught(self):
        # The renderer silently falls back to "other", so a typo would ship.
        problems = self.check(entry(subfield="retreival"))
        self.assertTrue(any("unknown subfield" in p for p in problems), problems)

    def test_every_section_is_required(self):
        for key in bs.SECTION_KEYS:
            with self.subTest(section=key):
                secs = {k: v for k, v in entry()["sections"].items() if k != key}
                problems = self.check(entry(sections=secs))
                self.assertTrue(any("sections.%s" % key in p for p in problems), problems)

    def test_section_needs_both_languages(self):
        secs = entry()["sections"]
        secs["method"] = {"zh": "只有中文", "en": ""}
        problems = self.check(entry(sections=secs))
        self.assertTrue(any("sections.method.en" in p for p in problems), problems)

    def test_unexpected_section_is_caught(self):
        secs = entry()["sections"]
        secs["conclusion"] = {"zh": "x", "en": "y"}
        problems = self.check(entry(sections=secs))
        self.assertTrue(any("unexpected section" in p for p in problems), problems)

    def test_missing_sections_object(self):
        problems = self.check(entry(sections=None))
        self.assertTrue(any("sections is missing" in p for p in problems), problems)

    def test_flags_must_be_boolean(self):
        for flag in ("deep", "fulltext_read"):
            with self.subTest(flag=flag):
                problems = self.check(entry(**{flag: "true"}))
                self.assertTrue(any(flag in p and "true or false" in p for p in problems),
                                problems)

    def test_source_label_without_url(self):
        problems = self.check(entry(source_label="DOI"))
        self.assertTrue(any("source_label" in p for p in problems), problems)

    def test_source_url_with_label_is_fine(self):
        self.assertEqual(
            self.check(entry(source_url="https://example.org/a", source_label="DOI")), [])

    def test_duplicate_across_days_is_caught(self):
        problems = self.check(entry(arxiv_id="same"), entry(arxiv_id="same"))
        self.assertTrue(any("already read on" in p for p in problems), problems)

    def test_distinct_ids_are_fine(self):
        self.assertEqual(self.check(entry(arxiv_id="a"), entry(arxiv_id="b")), [])


class TestRenderEntry(unittest.TestCase):
    def test_arxiv_entry_links_to_arxiv(self):
        html = bs.render_entry(entry(arxiv_id="2608.03920"))
        self.assertIn("arXiv:2608.03920", html)
        self.assertIn('href="https://arxiv.org/abs/2608.03920"', html)
        self.assertIn('href="https://arxiv.org/pdf/2608.03920"', html)

    def test_non_arxiv_entry_never_emits_an_arxiv_link(self):
        # The bug this guards: a DOI pasted into an arxiv.org URL 404s.
        html = bs.render_entry(entry(
            arxiv_id="10.5334/tismir.368", source_label="DOI",
            source_url="https://transactions.ismir.net/en/articles/10.5334/tismir.368"))
        self.assertNotIn("arxiv.org", html)
        self.assertIn("DOI:10.5334/tismir.368", html)
        self.assertIn('href="https://transactions.ismir.net/en/articles/10.5334/tismir.368"', html)

    def test_badges_reflect_flags(self):
        plain = bs.render_entry(entry())
        self.assertNotIn("深度分析", plain)
        self.assertNotIn("僅摘要層級", plain)
        deep = bs.render_entry(entry(deep=True))
        self.assertIn("深度分析", deep)
        self.assertIn("is-deep", deep)
        self.assertIn('data-deep="1"', deep)
        abstract = bs.render_entry(entry(fulltext_read=False))
        self.assertIn("僅摘要層級", abstract)

    def test_read_date_is_shown_and_searchable(self):
        html = bs.render_entry(entry(read_date="2026-08-10"))
        self.assertIn("2026-08-10", html)
        self.assertIn("date-tag", html)
        blob = html.split('data-search="')[1].split('"')[0]
        self.assertIn("2026-08-10", blob)

    def test_search_blob_covers_visible_prose(self):
        html = bs.render_entry(entry(why_en="flow matching rendering",
                                    title_zh="標題中文"))
        blob = html.split('data-search="')[1].split('"')[0]
        for term in ("a title", "標題中文", "flow matching rendering", "english method"):
            self.assertIn(term, blob)

    def test_header_is_keyboard_operable(self):
        html = bs.render_entry(entry())
        self.assertIn('role="button"', html)
        self.assertIn('tabindex="0"', html)
        self.assertIn('aria-expanded="false"', html)

    def test_links_sit_outside_the_clickable_header(self):
        # Nested interactive elements inside role=button is the thing to avoid.
        html = bs.render_entry(entry())
        head = html.split('<div class="card-links">')[0]
        self.assertNotIn("<a ", head)
        self.assertNotIn("stopPropagation", html)

    def test_html_is_escaped(self):
        html = bs.render_entry(entry(title_en='Cats & <script>alert(1)</script>',
                                     authors='O"Brien'))
        self.assertNotIn("<script>", html)
        self.assertIn("Cats &amp;", html)
        self.assertIn("&quot;", html)

    def test_all_five_sections_render(self):
        html = bs.render_entry(entry())
        self.assertEqual(html.count('<section class="sec">'), 5)


class TestMdInline(unittest.TestCase):
    def test_bold_and_code(self):
        self.assertIn("<strong>x</strong>", bs.md_inline("a **x** b"))
        self.assertIn("<code>y</code>", bs.md_inline("a `y` b"))

    def test_blank_line_splits_paragraphs(self):
        self.assertEqual(bs.md_inline("one\n\ntwo").count("<p>"), 2)

    def test_single_newline_is_a_break(self):
        self.assertIn("<br>", bs.md_inline("one\ntwo"))

    def test_escapes_before_markup(self):
        self.assertNotIn("<b>", bs.md_inline("<b>not bold</b>"))
        self.assertIn("&lt;b&gt;", bs.md_inline("<b>not bold</b>"))


class TestBuildPage(unittest.TestCase):
    def page(self, **kw):
        kw.setdefault("groups", [("標題", "Heading", [entry()])])
        kw.setdefault("stats", (1, 1, 0, "2026-08-01"))
        return bs.build_page(kw["groups"], "zh sub", "en sub", "<nav></nav>",
                             kw["stats"], show_stale=kw.get("show_stale", False),
                             expand_first=kw.get("expand_first", False))

    def test_no_placeholders_left(self):
        self.assertNotIn("{{", self.page())

    def test_stats_are_passed_through_not_derived(self):
        html = self.page(stats=(12, 4, 6, "2026-08-11"))
        self.assertIn("<b>12</b>", html)
        self.assertIn("<b>4</b>", html)
        self.assertIn("<b>6</b>", html)
        self.assertIn("2026-08-11", html)

    def test_stale_banner_only_when_asked(self):
        self.assertNotIn('id="stale"', self.page())
        html = self.page(show_stale=True, stats=(1, 1, 0, "2026-08-01"))
        self.assertIn('id="stale"', html)
        self.assertIn('data-latest="2026-08-01"', html)

    def test_expand_first_only_when_asked(self):
        self.assertNotIn("data-expand-first", self.page())
        self.assertIn('data-expand-first="1"', self.page(expand_first=True))

    def test_chips_only_for_subfields_present(self):
        html = self.page(groups=[("g", "g", [entry(subfield="generative")])])
        self.assertIn('data-f="generative"', html)
        self.assertNotIn('data-f="retrieval"', html)

    def test_group_heading_shows_both_languages_and_a_count(self):
        html = self.page(groups=[("中文標題", "English Heading", [entry(), entry()])])
        self.assertIn("中文標題", html)
        self.assertIn("English Heading", html)
        self.assertIn("<span class=\"count\">2", html)


class TestMainEndToEnd(unittest.TestCase):
    def build(self, data_dir):
        """Run main() into a temp dir, keeping its own reporting out of the test log."""
        out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out, True)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = bs.main([data_dir, out])
        return code, out

    def read(self, out, *parts):
        with open(os.path.join(out, *parts), encoding="utf-8") as f:
            return f.read()

    def test_index_holds_only_the_latest_day(self):
        with DataDir() as d:
            d.day("2026-08-01", [entry(arxiv_id="old", title_en="Older Paper")])
            d.day("2026-08-02", [entry(arxiv_id="new", title_en="Newest Paper")])
            code, out = self.build(d.path)
        self.assertEqual(code, 0)
        index = self.read(out, "index.html")
        self.assertIn("Newest Paper", index)
        self.assertNotIn("Older Paper", index)
        self.assertEqual(index.count('<article class="card'), 1)

    def test_topic_page_holds_every_day_of_that_subfield_only(self):
        with DataDir() as d:
            d.day("2026-08-01", [entry(arxiv_id="g1", subfield="generative",
                                       title_en="Gen One")])
            d.day("2026-08-02", [entry(arxiv_id="g2", subfield="generative",
                                       title_en="Gen Two"),
                                 entry(arxiv_id="r1", subfield="retrieval",
                                       title_en="Ret One")])
            code, out = self.build(d.path)
        self.assertEqual(code, 0)
        gen = self.read(out, "topics", "generative.html")
        self.assertIn("Gen One", gen)
        self.assertIn("Gen Two", gen)
        self.assertNotIn("Ret One", gen)
        self.assertNotIn('data-subfield="retrieval"', gen)

    def test_only_topics_with_papers_get_a_page(self):
        with DataDir() as d:
            d.day("2026-08-01", [entry(subfield="generative")])
            code, out = self.build(d.path)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(out, "topics", "generative.html")))
        self.assertFalse(os.path.exists(os.path.join(out, "topics", "cluster.html")))
        self.assertNotIn("cluster", self.read(out, "topics", "index.html"))

    def test_topic_pages_carry_no_stale_banner(self):
        with DataDir() as d:
            d.day("2026-08-01", [entry()])
            code, out = self.build(d.path)
        self.assertEqual(code, 0)
        self.assertIn('id="stale"', self.read(out, "index.html"))
        self.assertNotIn('id="stale"', self.read(out, "topics", "generative.html"))

    def test_bad_data_fails_the_build_and_writes_nothing(self):
        with DataDir() as d:
            d.day("2026-08-01", [entry(subfield="nonsense")])
            code, out = self.build(d.path)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(out, "index.html")))

    def test_duplicate_fails_the_build(self):
        with DataDir() as d:
            d.day("2026-08-01", [entry(arxiv_id="dup")])
            d.day("2026-08-02", [entry(arxiv_id="dup")])
            code, _ = self.build(d.path)
        self.assertEqual(code, 1)

    def test_missing_data_dir_fails(self):
        code, _ = self.build(os.path.join(tempfile.gettempdir(), "definitely-not-here"))
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
