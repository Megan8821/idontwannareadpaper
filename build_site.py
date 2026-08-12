#!/usr/bin/env python3
"""
Build the MIR Daily Paper Digest static site from per-day JSON files.

    python3 build_site.py [data_dir] [out_dir]

Defaults: data_dir="data", out_dir="." (repo root)

Reads every data/YYYY-MM-DD.json and writes:
    index.html               the latest day only
    topics/<subfield>.html   one page per subfield, all days, newest first

The split is deliberate: the front page answers "what is new today", and
everything ever read is reached by topic instead of by date. Browsing by date
does not scale -- a year of daily entries is 365 headings to scroll past,
whereas the topic set stays fixed at six.

Per-day JSON schema:
{
  "date": "2026-08-05",
  "entries": [
    {
      "arxiv_id": "2607.16657",     # unique id used for dedup; for non-arXiv sources
                                     # put the DOI or other stable id here instead
      "title_en": "...", "title_zh": "...",
      "authors": "...", "submitted": "2026-07-18", "categories": "cs.SD",
      "subfield": "generative|representation|transcription|retrieval|cluster|other",
      "deep": true,                 # novel architecture/technique -> deep dive badge
      "fulltext_read": true,        # false => analysis is abstract-level only
      "source_url": "https://transactions.ismir.net/...",  # optional: set for
                                     # non-arXiv papers (e.g. TISMIR/ISMIR/ACM DOI
                                     # pages) so the card links to the real page
                                     # instead of a nonexistent arxiv.org URL
      "source_label": "DOI",        # optional: id prefix shown next to arxiv_id
                                     # when source_url is set (default "ID")
      "why_zh": "...", "why_en": "...",
      "sections": {
        "motivation": {"zh": "...", "en": "..."},
        "intro":      {"zh": "...", "en": "..."},
        "method":     {"zh": "...", "en": "..."},
        "limitation": {"zh": "...", "en": "..."},
        "discussion": {"zh": "...", "en": "..."}
      }
    }
  ]
}

Adding a day = drop a new JSON file into data/ and re-run. Nothing else to edit.
"""

import glob
import html as htmllib
import json
import os
import re
import sys

SUBFIELDS = {
    "generative": {"zh": "生成式音樂模型", "en": "Generative Music Models", "color": "#c2410c"},
    "representation": {"zh": "音源分離與表徵學習", "en": "Separation & Representation", "color": "#1d4ed8"},
    "transcription": {"zh": "轉譜與音高分析", "en": "Transcription & Pitch", "color": "#047857"},
    "retrieval": {"zh": "檢索、推薦與情緒", "en": "Retrieval, RecSys & Emotion", "color": "#7e22ce"},
    "cluster": {"zh": "音樂聚類與相似度", "en": "Music Clustering & Similarity", "color": "#a16207"},
    "other": {"zh": "其他 MIR 主題", "en": "Other MIR Topics", "color": "#475569"},
}

SECTION_LABELS = [
    ("motivation", "動機", "Motivation"),
    ("intro", "背景與相關研究", "Introduction & Prior Work"),
    ("method", "方法", "Method"),
    ("limitation", "限制", "Limitations"),
    ("discussion", "討論", "Discussion"),
]

SECTION_KEYS = tuple(k for k, _, _ in SECTION_LABELS)


def anchor(arxiv_id):
    """Stable in-page anchor for a paper. DOIs carry dots and slashes, so the
    identifier cannot go into a fragment as-is."""
    return "p-" + (re.sub(r"[^a-z0-9]+", "-", (arxiv_id or "").lower()).strip("-") or "unknown")

# Every entry must carry these. The renderer defaults most of them away, which
# is the problem: a missing title or a mistyped subfield produces a page that
# looks fine and is quietly wrong, so the build refuses instead.
REQUIRED_FIELDS = ("arxiv_id", "title_en", "title_zh", "authors", "submitted",
                   "categories", "subfield", "why_zh", "why_en")


def esc(text):
    return htmllib.escape(text or "", quote=True)


def md_inline(text):
    """Minimal inline markup: **bold**, `code`, blank-line paragraphs."""
    out = esc(text)
    parts = out.split("`")
    for i in range(1, len(parts), 2):
        parts[i] = "<code>" + parts[i] + "</code>"
    out = "".join(parts)
    parts = out.split("**")
    for i in range(1, len(parts), 2):
        parts[i] = "<strong>" + parts[i] + "</strong>"
    out = "".join(parts)
    paras = [p.strip() for p in out.split("\n\n") if p.strip()]
    return "".join("<p>" + p.replace("\n", "<br>") + "</p>" for p in paras)


def load_days(data_dir):
    """Return ({date: [entry, ...]}, [problem, ...]) from data/*.json.

    Each entry gets a "read_date" key. On a topic page a card no longer sits
    under a date heading, so it has to carry the date it was read itself.

    An unreadable file is reported rather than skipped. Skipping it would drop a
    whole day out of the site while the build still succeeded -- a stray comma in
    today's JSON would look exactly like a day nobody wrote.
    """
    days = {}
    problems = []
    for path in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                blob = json.load(f)
        except (ValueError, OSError) as exc:
            problems.append("%s: cannot be read (%s)" % (name, exc))
            continue
        if not isinstance(blob, dict):
            problems.append("%s: top level must be an object" % name)
            continue
        stem = os.path.splitext(name)[0]
        date = blob.get("date") or stem
        if blob.get("date") and blob["date"] != stem:
            problems.append("%s: date field says %s but the filename says %s"
                            % (name, blob["date"], stem))
        entries = blob.get("entries")
        if not entries:
            problems.append("%s: no entries" % name)
            continue
        if not isinstance(entries, list):
            problems.append("%s: entries must be a list" % name)
            continue
        for e in entries:
            if not isinstance(e, dict):
                problems.append("%s: every entry must be an object" % name)
                continue
            e["read_date"] = date
            days.setdefault(date, []).append(e)
    return days, problems


def validate_days(days):
    """Return a list of problems with the loaded entries; empty means sound.

    The renderer is forgiving by design -- it defaults a missing field away and
    falls back to the "other" subfield -- so nothing downstream notices bad data.
    This is what notices.
    """
    problems = []
    seen = {}
    for date in sorted(days):
        for i, e in enumerate(days[date]):
            aid = e.get("arxiv_id")
            where = "%s entry %d" % (date, i + 1)
            if aid:
                where += " (%s)" % aid

            for field in REQUIRED_FIELDS:
                if not str(e.get(field, "") or "").strip():
                    problems.append("%s: %s is missing or empty" % (where, field))

            sf = e.get("subfield")
            if sf and sf not in SUBFIELDS:
                problems.append("%s: unknown subfield %r -- expected one of %s"
                                % (where, sf, ", ".join(SUBFIELDS)))

            secs = e.get("sections")
            if not isinstance(secs, dict):
                problems.append("%s: sections is missing" % where)
            else:
                for key in SECTION_KEYS:
                    body = secs.get(key)
                    if not isinstance(body, dict):
                        problems.append("%s: sections.%s is missing" % (where, key))
                        continue
                    for lang in ("zh", "en"):
                        if not str(body.get(lang, "") or "").strip():
                            problems.append("%s: sections.%s.%s is empty" % (where, key, lang))
                for key in secs:
                    if key not in SECTION_KEYS:
                        problems.append("%s: unexpected section %r" % (where, key))

            for flag in ("deep", "fulltext_read"):
                if flag in e and not isinstance(e[flag], bool):
                    problems.append("%s: %s must be true or false, got %r"
                                    % (where, flag, e[flag]))

            # source_label only ever renders alongside source_url, so setting it
            # alone means a link was meant to point somewhere and does not.
            if e.get("source_label") and not e.get("source_url"):
                problems.append("%s: source_label set without source_url" % where)

            # Three papers nobody has read yet is the whole premise, and only
            # this enforces it.
            if aid:
                if aid in seen:
                    problems.append("%s: already read on %s" % (where, seen[aid]))
                else:
                    seen[aid] = date
    return problems


def render_entry(e):
    sf = SUBFIELDS.get(e.get("subfield", "other"), SUBFIELDS["other"])
    aid = e.get("arxiv_id", "")
    src_url = e.get("source_url")  # set for non-arXiv sources (e.g. TISMIR DOI pages)
    id_label = "arXiv" if not src_url else e.get("source_label", "ID")
    deep = bool(e.get("deep"))
    # Everything visible on the card is searchable, the why line included --
    # it is prose the reader can see, so leaving it out makes search lie.
    # The read date is in here because browsing by date is gone -- searching
    # "2026-08-10" is now the way to ask what a particular day's papers were.
    search_blob = " ".join([
        e.get("title_en", ""), e.get("title_zh", ""), e.get("authors", ""),
        aid, sf["zh"], sf["en"], e.get("why_zh", ""), e.get("why_en", ""),
        e.get("read_date", ""),
        *[v.get(k, "") for v in e.get("sections", {}).values() for k in ("zh", "en")],
    ]).lower()

    badges = ['<span class="tag" style="--tag:%s"><span class="zh-only">%s</span>'
              '<span class="en-only">%s</span></span>' % (sf["color"], esc(sf["zh"]), esc(sf["en"]))]
    if deep:
        badges.append('<span class="tag deep">★ <span class="zh-only">新穎架構・深度分析</span>'
                      '<span class="en-only">Novel architecture &middot; deep dive</span></span>')
    if not e.get("fulltext_read", True):
        badges.append('<span class="tag warn"><span class="zh-only">僅摘要層級</span>'
                      '<span class="en-only">Abstract-level only</span></span>')
    # On a topic page the cards are not under a date heading, so each one states
    # the day it was read. Harmless on the index, where it repeats the heading.
    if e.get("read_date"):
        badges.append('<span class="tag date-tag mono">%s</span>' % esc(e["read_date"]))

    secs = []
    for key, zh_label, en_label in SECTION_LABELS:
        body = e.get("sections", {}).get(key)
        if not body:
            continue
        secs.append(
            '<section class="sec"><h4><span class="zh-only">%s</span><span class="en-only">%s</span></h4>'
            '<div class="body zh-only">%s</div><div class="body en-only">%s</div></section>'
            % (zh_label, en_label, md_inline(body.get("zh", "")), md_inline(body.get("en", "")))
        )

    why = ""
    if e.get("why_zh") or e.get("why_en"):
        why = ('<div class="why"><span class="zh-only"><b>為什麼挑這篇：</b>%s</span>'
               '<span class="en-only"><b>Why this one:</b> %s</span></div>'
               % (esc(e.get("why_zh", "")), esc(e.get("why_en", ""))))

    # The links sit outside the clickable header, so the header can be a real
    # keyboard control without interactive elements nested inside it -- which is
    # also what retires the stopPropagation on every link.
    if src_url:
        links = ('<a href="%s" target="_blank" rel="noopener">source</a>'
                 '<a href="https://www.semanticscholar.org/search?q=%s" target="_blank" '
                 'rel="noopener">cited by</a>') % (esc(src_url), esc(aid))
    else:
        links = ('<a href="https://arxiv.org/abs/%s" target="_blank" rel="noopener">abs</a>'
                 '<a href="https://arxiv.org/pdf/%s" target="_blank" rel="noopener">pdf</a>'
                 '<a href="https://arxiv.org/html/%s" target="_blank" rel="noopener">html</a>'
                 '<a href="https://www.semanticscholar.org/search?q=%s" target="_blank" '
                 'rel="noopener">cited by</a>') % (esc(aid), esc(aid), esc(aid), esc(aid))

    return """<article class="card%s" id="%s" data-paper-id="%s" data-subfield="%s" data-deep="%s" data-search="%s">
  <header class="card-head" role="button" tabindex="0" aria-expanded="false"
          onclick="togglePaper(this)" onkeydown="cardKey(event, this)">
    <div class="tags">%s</div>
    <div class="titles">
      <h3 class="t-en">%s</h3>
      <h3 class="t-zh zh-only">%s</h3>
    </div>
    <div class="meta">%s</div>
    <div class="meta mono">%s:%s &middot; %s &middot; <span class="zh-only">投稿</span><span class="en-only">submitted</span> %s</div>
    <span class="chev" aria-hidden="true"></span>
  </header>
  <div class="card-links">
    %s
  </div>
  <div class="card-body">
    %s
    %s
  </div>
</article>""" % (
        " is-deep" if deep else "", anchor(aid), esc(aid),
        esc(e.get("subfield", "other")), "1" if deep else "0",
        esc(search_blob), "".join(badges), esc(e.get("title_en", "")), esc(e.get("title_zh", "")),
        esc(e.get("authors", "")), esc(id_label), esc(aid), esc(e.get("categories", "")), esc(e.get("submitted", "")),
        links, why, "".join(secs),
    )


def search_index(all_entries):
    """A compact record per paper, for finding papers that live on another page.

    Titles, authors, identifier and date only -- no analysis prose. Every page
    carries the whole thing, so it has to stay small: the full text of a year of
    entries would be megabytes, while this is a couple of hundred bytes each.

    Fields are single letters and the searchable haystack is rebuilt in the
    browser rather than stored: spelling it out here duplicated the titles it is
    made of and doubled the payload every page carries.
    """
    return [{
        "i": e.get("arxiv_id", ""),
        "a": anchor(e.get("arxiv_id", "")),
        "f": e.get("subfield", "other"),
        "d": e.get("read_date", ""),
        "t": e.get("title_en", ""),
        "z": e.get("title_zh", ""),
        "u": e.get("authors", ""),
    } for e in all_entries]


def build_page(groups, subtitle_zh, subtitle_en, nav_html, show_stale=False,
               expand_first=False, index_data=None, link_prefix="", latest=""):
    """Render a full page.

    groups: [(heading_zh, heading_en, [entry, ...]), ...] in display order. A
        group is a day on the index and a whole subfield on a topic page.
    latest: newest date in the whole collection, for the freshness banner. Only
        meaningful with show_stale.
    show_stale: index only. The banner reports that the daily run has stopped,
        which is meaningless on a topic page -- a topic goes quiet whenever
        nothing in it happens to be read, and that is not a failure.
    expand_first: open the first group's cards on load. Wanted on the index,
        where the first group is today, but not on a topic page, where it would
        expand the entire topic's full text at once.
    index_data: search_index() over every paper, so a search run here can point
        at matches that live on another page. Without it the index page searches
        three papers and reports the other hundreds as "no match".
    link_prefix: path from this page to topics/, for links into that index.
    """
    entries = [e for _, _, es in groups for e in es]

    blocks = []
    for zh, en, es in groups:
        cards = "\n".join(render_entry(e) for e in es)
        blocks.append(
            '<div class="group">\n<h2 class="group-head">'
            '<span class="label mono zh-only">%s</span><span class="label mono en-only">%s</span>'
            '<span class="count">%d <span class="zh-only">篇</span><span class="en-only">papers</span>'
            '</span></h2>\n%s\n</div>' % (esc(zh), esc(en), len(es), cards))

    chips = "".join(
        '<button class="chip" data-f="%s" onclick="toggleFilter(this)"><span class="dot" style="--tag:%s"></span>'
        '<span class="zh-only">%s</span><span class="en-only">%s</span></button>'
        % (k, v["color"], esc(v["zh"]), esc(v["en"]))
        for k, v in SUBFIELDS.items() if any(e.get("subfield") == k for e in entries)
    )

    stale = ('<div class="stale" id="stale" role="status" data-latest="%s" hidden></div>' % esc(latest)
             if show_stale else "")

    # Inline JSON, so "</script>" appearing inside a title cannot end the block.
    payload = json.dumps(index_data or [], ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")

    out = TEMPLATE
    for k, v in {
        "subtitle_zh": subtitle_zh, "subtitle_en": subtitle_en, "nav": nav_html,
        "chips": chips, "stale": stale,
        "expand_first": ' data-expand-first="1"' if expand_first else "",
        "groups": "\n".join(blocks),
        "search_index": payload, "link_prefix": json.dumps(link_prefix),
        "subfield_labels": json.dumps(
            {k: [v["zh"], v["en"]] for k, v in SUBFIELDS.items()},
            ensure_ascii=False, separators=(",", ":")),
    }.items():
        out = out.replace("{{%s}}" % k, v)
    return out


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MIR Daily Paper Digest</title>
<style>
  /* Neutrals are warmed toward the brown accent rather than left pure grey, so
     the greys and the accent read as one set. Both themes define every token;
     no component reaches for a literal colour. */
  :root { --bg:#f6f5f2; --panel:#fffefc; --ink:#191714; --ink2:#615b52; --line:#e4e0d8;
    --accent:#8a5423; --deep:#b45309; --warn:#8a6410; --shadow:0 1px 3px rgba(60,45,25,.07);
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;
    /* Latin paper titles only. A journal-ish serif that ships with the OS --
       the page must stay self-contained, and a CJK webfont would be megabytes,
       so the pairing comes from stacks rather than downloads. */
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua","Times New Roman",Georgia,serif;
    --mono:ui-monospace,SFMono-Regular,Menlo,monospace;
    --fs-xs:.75rem; --fs-sm:.8125rem; --fs-md:.9375rem; --fs-base:1rem;
    --fs-lg:1.1875rem; --fs-xl:1.5rem;
    --measure:68ch; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#131211; --panel:#1c1a18; --ink:#ecebe7; --ink2:#9d968b; --line:#302d29;
      --accent:#d9a86f; --deep:#f0b429; --warn:#d2a63f; --shadow:none; }
    /* The subfield hues are picked to sit on paper. Lifting them as a set keeps
       them legible on a dark ground without maintaining a second palette. */
    .tag { background:color-mix(in srgb, var(--tag,#475569) 78%, #fff); }
    .dot { background:color-mix(in srgb, var(--tag) 78%, #fff); } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:var(--fs-base)/1.7 var(--sans); }
  .wrap { max-width:920px; margin:0 auto; padding:32px 20px 96px;
    display:flex; flex-direction:column; gap:18px; }
  header.top { display:flex; flex-direction:column; gap:6px; }
  header.top h1 { font-size:var(--fs-xl); margin:0; letter-spacing:-.015em; text-wrap:balance; }
  header.top .sub { color:var(--ink2); font-size:var(--fs-md); max-width:var(--measure); }
  nav.site { font-size:var(--fs-sm); display:flex; gap:14px; flex-wrap:wrap; }
  nav.site a { color:var(--accent); text-decoration:none;
    border-bottom:1px solid color-mix(in srgb, var(--accent) 35%, transparent); }
  nav.site a:hover { border-bottom-color:var(--accent); }
  nav.site .here { color:var(--ink2); border:0; }
  /* Shown only when the newest entry is behind today -- the site reporting on
     its own freshness, so a run that dies without pushing is still visible. */
  .stale { padding:12px 16px; border-radius:10px; font-size:var(--fs-md);
    background:color-mix(in srgb, var(--warn) 12%, var(--panel));
    border:1px solid color-mix(in srgb, var(--warn) 45%, var(--line)); }
  .stale b { color:var(--warn); }
  .controls { position:sticky; top:0; z-index:10; background:var(--bg); padding:12px 0 14px;
    border-bottom:1px solid var(--line); display:flex; flex-direction:column; gap:10px; }
  input[type=search] { width:100%; padding:11px 14px; font-size:var(--fs-md); color:var(--ink);
    font-family:var(--sans); background:var(--panel); border:1px solid var(--line); border-radius:8px; }
  .row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
  .chip, .toggle { font:inherit; font-size:var(--fs-sm); color:var(--ink2); cursor:pointer; background:var(--panel);
    border:1px solid var(--line); border-radius:999px; padding:5px 12px; display:inline-flex; align-items:center; gap:6px; }
  .chip[aria-pressed=true], .toggle[aria-pressed=true] { color:var(--ink); border-color:var(--accent);
    box-shadow:inset 0 0 0 1px var(--accent); }
  /* One visible focus treatment for every control, including the card headers,
     which are keyboard-operable and previously showed nothing at all. */
  :focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:4px; }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--tag); }
  #list { display:flex; flex-direction:column; gap:34px; }
  .group { display:flex; flex-direction:column; gap:14px; }
  .group-head { display:flex; align-items:baseline; gap:12px; font-size:var(--fs-base); font-weight:600;
    padding-bottom:8px; border-bottom:2px solid var(--line); margin:0; }
  .group-head .label { font-variant-numeric:tabular-nums; }
  .group-head .count { font-weight:400; font-size:var(--fs-sm); color:var(--ink2); font-family:var(--sans); }
  .mono { font-family:var(--mono); }
  .card { background:var(--panel); border:1px solid var(--line); border-left:3px solid transparent;
    border-radius:10px; box-shadow:var(--shadow); overflow:hidden; }
  .card.is-deep { border-left-color:var(--deep); }
  .card-head { padding:16px 44px 16px 18px; cursor:pointer; position:relative;
    display:flex; flex-direction:column; gap:7px; }
  .card-head:hover { background:color-mix(in srgb, var(--panel) 92%, var(--accent)); }
  .tags { display:flex; gap:6px; flex-wrap:wrap; }
  .tag { font-size:var(--fs-xs); letter-spacing:.03em; text-transform:uppercase; padding:3px 8px;
    border-radius:4px; color:#fff; background:var(--tag,#475569); }
  .tag.deep { background:var(--deep); }
  .tag.warn { background:var(--warn); }
  .tag.date-tag { background:transparent; color:var(--ink2); border:1px solid var(--line);
    text-transform:none; letter-spacing:0; font-variant-numeric:tabular-nums; }
  .titles { display:flex; flex-direction:column; gap:3px; }
  /* The serif is the English title's alone; the Chinese title stays in the sans
     stack, where the installed CJK face is the one that actually renders well. */
  .card h3 { margin:0; font-size:var(--fs-lg); line-height:1.4; font-weight:600;
    font-family:var(--serif); text-wrap:balance; max-width:var(--measure); }
  .card h3.t-zh { font-size:var(--fs-md); font-weight:500; color:var(--ink2);
    font-family:var(--sans); line-height:1.55; }
  .meta { font-size:var(--fs-sm); color:var(--ink2); }
  .meta.mono { font-variant-numeric:tabular-nums; }
  .card-links { display:flex; gap:12px; padding:0 18px 14px; }
  .card-links a { font-size:var(--fs-sm); color:var(--accent); text-decoration:none;
    border-bottom:1px solid color-mix(in srgb, var(--accent) 40%, transparent); }
  .card-links a:hover { border-bottom-color:var(--accent); }
  .chev { position:absolute; right:18px; top:20px; width:9px; height:9px; border-right:2px solid var(--ink2);
    border-bottom:2px solid var(--ink2); transform:rotate(45deg); transition:transform .18s; }
  .card.open .chev { transform:rotate(-135deg); }
  .card-body { display:none; padding:0 18px 18px; border-top:1px solid var(--line); }
  .card.open .card-body { display:flex; flex-direction:column; gap:18px; }
  .why { font-size:var(--fs-md); color:var(--ink2); background:color-mix(in srgb, var(--panel) 88%, var(--accent));
    border-radius:8px; padding:10px 13px; margin:16px 0 0; max-width:var(--measure); }
  .sec { display:flex; flex-direction:column; gap:6px; }
  .sec h4 { margin:0; font-size:var(--fs-xs); letter-spacing:.08em; text-transform:uppercase;
    color:var(--accent); border-bottom:1px solid var(--line); padding-bottom:4px; }
  /* The analysis is long-form reading, so it is held to a column rather than
     spanning the full card -- 920px of 16px text is over 100 characters a line. */
  .sec .body { max-width:var(--measure); }
  .sec .body p { margin:.55em 0; }
  .sec code { font-family:var(--mono); font-size:.88em;
    background:color-mix(in srgb, var(--panel) 84%, var(--ink2)); padding:1px 5px; border-radius:4px; }
  .body.en-only { color:var(--ink2); }
  body.lang-zh .en-only { display:none; }
  body.lang-en .zh-only { display:none; }
  .empty { display:none; text-align:center; color:var(--ink2); padding:60px 0; }
  body.no-results .empty { display:block; }
  /* Matches that live on another page. Every paper sits on its topic page, so
     this is what stops a search on the index reporting "nothing" for a paper
     the site definitely has. */
  .elsewhere { border:1px dashed color-mix(in srgb, var(--accent) 45%, var(--line));
    border-radius:10px; padding:14px 16px; display:flex; flex-direction:column; gap:10px; }
  /* display:flex would otherwise beat the browser's [hidden] rule and leave an
     empty dashed box on the page whenever there is nothing to report. */
  .elsewhere[hidden] { display:none; }
  .elsewhere h3 { margin:0; font-size:var(--fs-sm); font-weight:600; color:var(--accent);
    text-transform:uppercase; letter-spacing:.06em; }
  .elsewhere ol { margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:9px; }
  .elsewhere a { color:var(--ink); text-decoration:none; display:flex; flex-direction:column; gap:2px; }
  .elsewhere a:hover .ti { border-bottom-color:var(--accent); }
  .elsewhere .ti { font-family:var(--serif); font-size:var(--fs-md); line-height:1.35;
    border-bottom:1px solid transparent; align-self:flex-start; }
  .elsewhere .wh { font-size:var(--fs-xs); color:var(--ink2); font-variant-numeric:tabular-nums; }
  .elsewhere .more { font-size:var(--fs-xs); color:var(--ink2); }
  footer { margin-top:32px; padding-top:18px; border-top:1px solid var(--line);
    font-size:var(--fs-sm); color:var(--ink2); max-width:var(--measure); }
  @media (prefers-reduced-motion: reduce) { * { transition:none !important; animation:none !important; } }
</style>
</head>
<body class="lang-zh">
<div class="wrap">
  <header class="top">
    <h1>MIR Daily Paper Digest</h1>
    <div class="sub"><span class="zh-only">{{subtitle_zh}}</span><span class="en-only">{{subtitle_en}}</span></div>
  </header>
  <nav class="site">{{nav}}</nav>

  {{stale}}

  <div class="controls">
    <input type="search" id="q" aria-label="搜尋論文 / Search papers"
           placeholder="搜尋標題、作者、方法、日期、arXiv ID…  /  search title, author, method, date, arXiv ID…"
           oninput="applyFilters()" autocomplete="off">
    <div class="row">
      {{chips}}
      <button class="toggle" id="deepOnly" aria-pressed="false" onclick="toggleDeep(this)">★
        <span class="zh-only">只看深度分析</span><span class="en-only">deep dives only</span></button>
      <button class="toggle" id="langBtn" onclick="toggleLang()">中 / EN</button>
      <button class="toggle" onclick="setAll(true)"><span class="zh-only">全部展開</span><span class="en-only">expand all</span></button>
      <button class="toggle" onclick="setAll(false)"><span class="zh-only">全部收合</span><span class="en-only">collapse all</span></button>
    </div>
  </div>

  <div id="list"{{expand_first}}>
{{groups}}
  </div>
  <div class="elsewhere" id="elsewhere" hidden></div>
  <div class="empty"><span class="zh-only">沒有符合的論文。</span><span class="en-only">No matching papers.</span></div>

  <footer>
    <span class="zh-only">主要來源為 arXiv（cs.SD / eess.AS / cs.IR）公開全文，每週一另掃 ISMIR / TISMIR（完全開放獲取）與 ICASSP、IEEE、ACM 的開放部分。標「僅摘要層級」者代表無法取得全文，分析僅根據摘要。</span>
    <span class="en-only">Mainly open-access arXiv full texts (cs.SD / eess.AS / cs.IR), with a Monday sweep of ISMIR / TISMIR (fully open access) and the open portions of ICASSP, IEEE and ACM. Entries marked &ldquo;abstract-level only&rdquo; had no retrievable full text.</span>
  </footer>
</div>

<script>
  // The freshness banner is computed in the browser, not at build time, because
  // the failure it reports on is precisely the case where nothing gets rebuilt.
  // A run that dies before pushing leaves yesterday's page in place; that page
  // still notices, every time someone opens it.
  function updateStale() {
    var el = document.getElementById('stale'); if (!el) { return; }
    el.hidden = true;
    var latest = el.dataset.latest; if (!/^\d{4}-\d{2}-\d{2}$/.test(latest)) { return; }
    var p = latest.split('-'), now = new Date();
    var days = Math.floor(
      (Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) -
       Date.UTC(+p[0], +p[1] - 1, +p[2])) / 86400000);
    if (days < 2) { return; }   // today or yesterday is normal
    el.innerHTML =
      '<span class="zh-only"><b>已經 ' + days + ' 天沒有更新。</b>' +
      '最新一天是 ' + latest + '。每日任務應該每天都會加一天，所以這代表它壞了。</span>' +
      '<span class="en-only"><b>No update for ' + days + ' days.</b> ' +
      'The newest day is ' + latest + '. The daily run should add one every day, so this means it is broken.</span>';
    el.hidden = false;
  }
  updateStale();

  var filters = new Set(); var deepOnly = false;
  // aria-expanded has to follow the class, or a screen reader is told every card
  // is collapsed no matter what is on screen.
  function syncCard(card) {
    var head = card.querySelector('.card-head');
    if (head) head.setAttribute('aria-expanded', card.classList.contains('open') ? 'true' : 'false');
  }
  function togglePaper(head) {
    var card = head.parentElement;
    card.classList.toggle('open');
    syncCard(card);
  }
  // The header is a div with role=button, so Enter and Space do not activate it
  // for free the way they would on a real button.
  function cardKey(ev, head) {
    if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
      ev.preventDefault();
      togglePaper(head);
    }
  }
  function setAll(open) {
    document.querySelectorAll('.card').forEach(function (c) {
      c.classList.toggle('open', open);
      syncCard(c);
    });
  }
  function toggleLang() {
    document.body.classList.toggle('lang-zh');
    document.body.classList.toggle('lang-en');
    // Tell assistive tech and the hyphenator which language is actually showing.
    document.documentElement.lang = document.body.classList.contains('lang-en') ? 'en' : 'zh-Hant';
    applyFilters();   // the cross-page results are built in one language
  }
  function toggleFilter(btn) {
    var k = btn.dataset.f, on = btn.getAttribute('aria-pressed') === 'true';
    btn.setAttribute('aria-pressed', on ? 'false' : 'true');
    if (on) { filters.delete(k); } else { filters.add(k); }
    applyFilters();
  }
  function toggleDeep(btn) {
    deepOnly = btn.getAttribute('aria-pressed') !== 'true';
    btn.setAttribute('aria-pressed', deepOnly ? 'true' : 'false');
    applyFilters();
  }
  // Every paper lives on its topic page, and a page only holds its own slice.
  // Without this, searching the index -- which is one day -- reports every other
  // paper on the site as "no match", which reads as "we do not have it".
  var PAPER_INDEX = {{search_index}};
  var SUBFIELD_LABELS = {{subfield_labels}};
  var LINK_PREFIX = {{link_prefix}};
  var ON_PAGE = {};
  document.querySelectorAll('[data-paper-id]').forEach(function (c) { ON_PAGE[c.dataset.paperId] = 1; });
  var ELSEWHERE_MAX = 20;

  // Built here rather than shipped: storing it would repeat the titles it is
  // made of in every record, on every page.
  function haystack(p) {
    if (p._h === undefined) {
      p._h = [p.t, p.z, p.u, p.i, p.d, (SUBFIELD_LABELS[p.f] || []).join(' ')]
        .join(' ').toLowerCase();
    }
    return p._h;
  }

  function renderElsewhere(q) {
    var box = document.getElementById('elsewhere');
    if (!box) { return 0; }
    if (!q) { box.hidden = true; box.innerHTML = ''; return 0; }
    var hits = PAPER_INDEX.filter(function (p) {
      return !ON_PAGE[p.i] && haystack(p).indexOf(q) !== -1;
    });
    if (!hits.length) { box.hidden = true; box.innerHTML = ''; return 0; }
    var zh = document.body.classList.contains('lang-zh');
    var items = hits.slice(0, ELSEWHERE_MAX).map(function (p) {
      var href = LINK_PREFIX + encodeURIComponent(p.f) + '.html#' + p.a;
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = href;
      var t = document.createElement('span');
      t.className = 'ti';
      t.textContent = zh && p.z ? p.z : p.t;
      var w = document.createElement('span');
      w.className = 'wh';
      w.textContent = p.d + ' · ' + p.i;
      a.appendChild(t); a.appendChild(w); li.appendChild(a);
      return li;
    });
    box.innerHTML = '';
    var h = document.createElement('h3');
    h.textContent = zh ? '在其他頁面找到 ' + hits.length + ' 篇'
                       : hits.length + ' more on other pages';
    var ol = document.createElement('ol');
    items.forEach(function (li) { ol.appendChild(li); });
    box.appendChild(h); box.appendChild(ol);
    if (hits.length > ELSEWHERE_MAX) {
      var more = document.createElement('div');
      more.className = 'more';
      more.textContent = zh ? '還有 ' + (hits.length - ELSEWHERE_MAX) + ' 篇未列出'
                            : (hits.length - ELSEWHERE_MAX) + ' not listed';
      box.appendChild(more);
    }
    box.hidden = false;
    return hits.length;
  }

  function applyFilters() {
    var q = document.getElementById('q').value.trim().toLowerCase(), shown = 0;
    document.querySelectorAll('.card').forEach(function (c) {
      var ok = true;
      if (filters.size && !filters.has(c.dataset.subfield)) ok = false;
      if (deepOnly && c.dataset.deep !== '1') ok = false;
      if (ok && q) ok = c.dataset.search.indexOf(q) !== -1;
      c.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    document.querySelectorAll('.group').forEach(function (g) {
      var any = Array.prototype.some.call(g.querySelectorAll('.card'), function (c) { return c.style.display !== 'none'; });
      g.style.display = any ? '' : 'none';
    });
    // Only a search looks beyond this page; the chips and the deep toggle are
    // filters over what is here.
    var away = renderElsewhere(filters.size || deepOnly ? '' : q);
    document.body.classList.toggle('no-results', shown === 0 && away === 0);
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement.id !== 'q') { e.preventDefault(); document.getElementById('q').focus(); }
  });
  // Only the index opts in: there the first group is today, which is the whole
  // point of the page. On a topic page it would unfold every paper in the topic.
  var list = document.getElementById('list');
  if (list && list.dataset.expandFirst === '1') {
    var firstGroup = list.querySelector('.group');
    if (firstGroup) firstGroup.querySelectorAll('.card').forEach(function (c) {
      c.classList.add('open');
      syncCard(c);
    });
  }

  // Arriving from a cross-page search result: open that paper and go to it,
  // otherwise the link lands on a collapsed card in a long list.
  function openFromHash() {
    if (!/^#p-[a-z0-9-]+$/.test(location.hash)) { return; }
    var card = document.getElementById(location.hash.slice(1));
    if (!card || !card.classList.contains('card')) { return; }
    card.classList.add('open');
    syncCard(card);
    card.scrollIntoView({block: 'start'});
  }
  openFromHash();
  window.addEventListener('hashchange', openFromHash);
</script>
</body>
</html>"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data_dir = argv[0] if len(argv) > 0 else "data"
    out_dir = argv[1] if len(argv) > 1 else "."
    days, problems = load_days(data_dir)
    problems += validate_days(days)
    if problems:
        sys.stderr.write("bad data, refusing to build:\n  %s\n" % "\n  ".join(problems))
        return 1
    if not days:
        sys.stderr.write("no data files found in %s\n" % data_dir)
        return 1

    all_dates = sorted(days.keys(), reverse=True)
    all_entries = [e for d in all_dates for e in days[d]]

    # Topics that actually have papers. An empty subfield gets no page and no
    # nav link rather than a page reading "0 papers".
    topics = [k for k in SUBFIELDS if any(e.get("subfield") == k for e in all_entries)]

    os.makedirs(os.path.join(out_dir, "topics"), exist_ok=True)

    def topic_nav(current=None):
        """Nav shared by both page types; `current` marks the page you are on.

        Labels follow the page's language toggle instead of printing both at
        once -- six bilingual topic names wrap the nav onto three lines.
        """
        prefix = "" if current is None else "../"
        home = ('<span class="zh-only">最新</span><span class="en-only">Latest</span>' if current is None
                else '<span class="zh-only">← 最新</span><span class="en-only">← Latest</span>')
        out = ['<span class="here">%s</span>' % home if current is None
               else '<a href="../index.html">%s</a>' % home]
        for k in topics:
            label = ('<span class="zh-only">%s</span><span class="en-only">%s</span>'
                     % (esc(SUBFIELDS[k]["zh"]), esc(SUBFIELDS[k]["en"])))
            out.append('<span class="here">%s</span>' % label if k == current
                       else '<a href="%stopics/%s.html">%s</a>' % (prefix, k, label))
        return " ".join(out)

    idx = search_index(all_entries)

    # index.html -- the latest day only
    latest = all_dates[0]
    index_html = build_page(
        [(latest, latest, days[latest])],
        "音樂資訊檢索每日論文摘要 · 為 megan 整理 · 每篇含動機、背景、方法、限制、討論"
        " · 以往的論文依主題整理，見上方連結",
        "Music Information Retrieval daily digest · curated for megan · motivation, intro,"
        " method, limitations, discussion · earlier papers are organised by topic, linked above",
        topic_nav(), show_stale=True, expand_first=True,
        index_data=idx, link_prefix="topics/", latest=latest)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # one page per topic, every day it ever appeared, newest first
    for k in topics:
        es = [e for d in all_dates for e in days[d] if e.get("subfield") == k]
        sf = SUBFIELDS[k]
        with open(os.path.join(out_dir, "topics", "%s.html" % k), "w", encoding="utf-8") as f:
            f.write(build_page(
                [(sf["zh"], sf["en"], es)],
                "%s · 累積 %d 篇 · 由新到舊" % (sf["zh"], len(es)),
                "%s · %d papers so far · newest first" % (sf["en"], len(es)),
                topic_nav(k), index_data=idx))

    # No topics/index.html: the nav already lists every topic on every page, so
    # a separate list of them was a page nothing linked to.
    print("built: index.html (%s, %d papers), %d topic page(s), %d papers total"
          % (latest, len(days[latest]), len(topics), len(all_entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
