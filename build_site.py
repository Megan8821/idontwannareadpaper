#!/usr/bin/env python3
"""
Build the MIR Daily Paper Digest static site from per-day JSON files.

    python3 build_site.py [data_dir] [out_dir]

Defaults: data_dir="data", out_dir="." (repo root)

Reads every data/YYYY-MM-DD.json and writes:
    index.html               most recent RECENT_DAYS days
    archive/YYYY-MM.html     one page per month
    archive/index.html       list of months

Per-day JSON schema:
{
  "date": "2026-08-05",
  "entries": [
    {
      "arxiv_id": "2607.16657",
      "title_en": "...", "title_zh": "...",
      "authors": "...", "submitted": "2026-07-18", "categories": "cs.SD",
      "subfield": "generative|representation|transcription|retrieval|cluster|other",
      "deep": true,                 # novel architecture/technique -> deep dive badge
      "fulltext_read": true,        # false => analysis is abstract-level only
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
import sys

RECENT_DAYS = 60

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
    """Return {date: [entry, ...]} from data/*.json, ignoring malformed files."""
    days = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                blob = json.load(f)
        except (ValueError, OSError) as exc:
            sys.stderr.write("skipping %s: %s\n" % (path, exc))
            continue
        date = blob.get("date") or os.path.splitext(os.path.basename(path))[0]
        entries = blob.get("entries", [])
        if entries:
            days.setdefault(date, []).extend(entries)
    return days


def render_entry(e):
    sf = SUBFIELDS.get(e.get("subfield", "other"), SUBFIELDS["other"])
    aid = e.get("arxiv_id", "")
    deep = bool(e.get("deep"))
    search_blob = " ".join([
        e.get("title_en", ""), e.get("title_zh", ""), e.get("authors", ""),
        aid, sf["zh"], sf["en"],
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

    return """<article class="card%s" data-subfield="%s" data-deep="%s" data-search="%s">
  <header class="card-head" onclick="togglePaper(this)">
    <div class="tags">%s</div>
    <h3 class="t-en">%s</h3>
    <h3 class="t-zh zh-only">%s</h3>
    <div class="meta">%s</div>
    <div class="meta mono">arXiv:%s &middot; %s &middot; <span class="zh-only">投稿</span><span class="en-only">submitted</span> %s</div>
    <div class="links">
      <a href="https://arxiv.org/abs/%s" target="_blank" rel="noopener" onclick="event.stopPropagation()">abs</a>
      <a href="https://arxiv.org/pdf/%s" target="_blank" rel="noopener" onclick="event.stopPropagation()">pdf</a>
      <a href="https://arxiv.org/html/%s" target="_blank" rel="noopener" onclick="event.stopPropagation()">html</a>
      <a href="https://www.semanticscholar.org/search?q=%s" target="_blank" rel="noopener" onclick="event.stopPropagation()">cited by</a>
    </div>
    <span class="chev" aria-hidden="true"></span>
  </header>
  <div class="card-body">
    %s
    %s
  </div>
</article>""" % (
        " is-deep" if deep else "", esc(e.get("subfield", "other")), "1" if deep else "0",
        esc(search_blob), "".join(badges), esc(e.get("title_en", "")), esc(e.get("title_zh", "")),
        esc(e.get("authors", "")), esc(aid), esc(e.get("categories", "")), esc(e.get("submitted", "")),
        esc(aid), esc(aid), esc(aid), esc(aid), why, "".join(secs),
    )


def build_page(days, subtitle_zh, subtitle_en, nav_html, depth=0):
    """days: {date: [entries]} -> full HTML document."""
    dates = sorted(days.keys(), reverse=True)
    entries = [e for d in dates for e in days[d]]

    blocks = []
    for d in dates:
        cards = "\n".join(render_entry(e) for e in days[d])
        blocks.append('<div class="day" data-date="%s">\n<h2 class="day-head"><span class="date mono">%s</span>'
                      '<span class="count">%d <span class="zh-only">篇</span><span class="en-only">papers</span>'
                      '</span></h2>\n%s\n</div>' % (esc(d), esc(d), len(days[d]), cards))

    n_deep = sum(1 for e in entries if e.get("deep"))
    latest = dates[0] if dates else "-"
    chips = "".join(
        '<button class="chip" data-f="%s" onclick="toggleFilter(this)"><span class="dot" style="--tag:%s"></span>'
        '<span class="zh-only">%s</span><span class="en-only">%s</span></button>'
        % (k, v["color"], esc(v["zh"]), esc(v["en"]))
        for k, v in SUBFIELDS.items() if any(e.get("subfield") == k for e in entries)
    )

    out = TEMPLATE
    for k, v in {
        "subtitle_zh": subtitle_zh, "subtitle_en": subtitle_en, "nav": nav_html,
        "n_papers": str(len(entries)), "n_days": str(len(dates)), "n_deep": str(n_deep),
        "latest": esc(latest), "chips": chips, "days": "\n".join(blocks),
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
  :root { --bg:#f7f7f5; --panel:#fff; --ink:#1a1a1a; --ink2:#5b5b5b; --line:#e3e3df;
    --accent:#8c5a2b; --deep:#b45309; --warn:#a16207; --shadow:0 1px 3px rgba(0,0,0,.06); }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#141414; --panel:#1c1c1c; --ink:#ececec; --ink2:#a0a0a0; --line:#2e2e2e;
      --accent:#d4a373; --deep:#f0b429; --warn:#d4a017; --shadow:none; } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
    font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif; }
  .wrap { max-width:920px; margin:0 auto; padding:32px 20px 96px; }
  header.top h1 { font-size:1.6rem; margin:0 0 6px; letter-spacing:-.01em; }
  header.top .sub { color:var(--ink2); font-size:.92rem; margin-bottom:14px; }
  nav.site { font-size:.84rem; margin-bottom:18px; display:flex; gap:14px; flex-wrap:wrap; }
  nav.site a { color:var(--accent); text-decoration:none;
    border-bottom:1px solid color-mix(in srgb, var(--accent) 35%, transparent); }
  nav.site a:hover { border-bottom-color:var(--accent); }
  nav.site .here { color:var(--ink2); border:0; }
  .stats { display:flex; gap:26px; flex-wrap:wrap; padding:14px 18px; background:var(--panel);
    border:1px solid var(--line); border-radius:10px; box-shadow:var(--shadow); margin-bottom:18px; }
  .stat b { display:block; font-size:1.35rem; line-height:1.2; }
  .stat span { font-size:.76rem; color:var(--ink2); text-transform:uppercase; letter-spacing:.06em; }
  .controls { position:sticky; top:0; z-index:10; background:var(--bg); padding:12px 0 14px;
    border-bottom:1px solid var(--line); margin-bottom:22px; }
  input[type=search] { width:100%; padding:11px 14px; font-size:.95rem; color:var(--ink);
    background:var(--panel); border:1px solid var(--line); border-radius:8px; }
  input[type=search]:focus { outline:2px solid var(--accent); outline-offset:1px; }
  .row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:10px; }
  .chip, .toggle { font:inherit; font-size:.82rem; color:var(--ink2); cursor:pointer; background:var(--panel);
    border:1px solid var(--line); border-radius:999px; padding:5px 12px; display:inline-flex; align-items:center; gap:6px; }
  .chip[aria-pressed=true], .toggle[aria-pressed=true] { color:var(--ink); border-color:var(--accent);
    box-shadow:inset 0 0 0 1px var(--accent); }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--tag); }
  .day { margin-bottom:34px; }
  .day-head { display:flex; align-items:baseline; gap:12px; font-size:1rem; font-weight:600;
    padding-bottom:8px; border-bottom:2px solid var(--line); margin:0 0 14px; }
  .day-head .count { font-weight:400; font-size:.82rem; color:var(--ink2); }
  .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  .card { background:var(--panel); border:1px solid var(--line); border-left:3px solid transparent;
    border-radius:10px; box-shadow:var(--shadow); margin-bottom:14px; overflow:hidden; }
  .card.is-deep { border-left-color:var(--deep); }
  .card-head { padding:16px 44px 16px 18px; cursor:pointer; position:relative; }
  .card-head:hover { background:color-mix(in srgb, var(--panel) 92%, var(--accent)); }
  .tags { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:8px; }
  .tag { font-size:.7rem; letter-spacing:.03em; text-transform:uppercase; padding:3px 8px; border-radius:4px;
    color:#fff; background:var(--tag,#475569); }
  .tag.deep { background:var(--deep); }
  .tag.warn { background:var(--warn); }
  .card h3 { margin:0 0 3px; font-size:1.04rem; line-height:1.45; font-weight:650; }
  .card h3.t-zh { font-size:.95rem; font-weight:500; color:var(--ink2); }
  .meta { font-size:.8rem; color:var(--ink2); }
  .links { margin-top:9px; display:flex; gap:12px; }
  .links a { font-size:.78rem; color:var(--accent); text-decoration:none;
    border-bottom:1px solid color-mix(in srgb, var(--accent) 40%, transparent); }
  .links a:hover { border-bottom-color:var(--accent); }
  .chev { position:absolute; right:18px; top:20px; width:9px; height:9px; border-right:2px solid var(--ink2);
    border-bottom:2px solid var(--ink2); transform:rotate(45deg); transition:transform .18s; }
  .card.open .chev { transform:rotate(-135deg); }
  .card-body { display:none; padding:0 18px 18px; border-top:1px solid var(--line); }
  .card.open .card-body { display:block; }
  .why { font-size:.86rem; color:var(--ink2); background:color-mix(in srgb, var(--panel) 88%, var(--accent));
    border-radius:8px; padding:10px 13px; margin:16px 0 4px; }
  .sec { margin-top:18px; }
  .sec h4 { margin:0 0 6px; font-size:.78rem; letter-spacing:.08em; text-transform:uppercase;
    color:var(--accent); border-bottom:1px solid var(--line); padding-bottom:4px; }
  .sec .body p { margin:.55em 0; }
  .sec code { font-family:ui-monospace,Menlo,monospace; font-size:.88em;
    background:color-mix(in srgb, var(--panel) 84%, var(--ink2)); padding:1px 5px; border-radius:4px; }
  .body.en-only { color:var(--ink2); }
  body.lang-zh .en-only { display:none; }
  body.lang-en .zh-only { display:none; }
  .empty { display:none; text-align:center; color:var(--ink2); padding:60px 0; }
  body.no-results .empty { display:block; }
  footer { margin-top:50px; padding-top:18px; border-top:1px solid var(--line); font-size:.78rem; color:var(--ink2); }
</style>
</head>
<body class="lang-zh">
<div class="wrap">
  <header class="top">
    <h1>MIR Daily Paper Digest</h1>
    <div class="sub"><span class="zh-only">{{subtitle_zh}}</span><span class="en-only">{{subtitle_en}}</span></div>
  </header>
  <nav class="site">{{nav}}</nav>

  <div class="stats">
    <div class="stat"><b>{{n_papers}}</b><span class="zh-only">論文</span><span class="en-only">papers</span></div>
    <div class="stat"><b>{{n_days}}</b><span class="zh-only">天數</span><span class="en-only">days</span></div>
    <div class="stat"><b>{{n_deep}}</b><span class="zh-only">深度分析</span><span class="en-only">deep dives</span></div>
    <div class="stat"><b class="mono">{{latest}}</b><span class="zh-only">最新</span><span class="en-only">latest</span></div>
  </div>

  <div class="controls">
    <input type="search" id="q" placeholder="搜尋標題、作者、方法、arXiv ID…  /  search title, author, method, arXiv ID…"
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

  <div id="list">
{{days}}
  </div>
  <div class="empty"><span class="zh-only">沒有符合的論文。</span><span class="en-only">No matching papers.</span></div>

  <footer>
    <span class="zh-only">來源為 arXiv（cs.SD / eess.AS / cs.IR）公開全文。標「僅摘要層級」者代表無法取得全文，分析僅根據摘要。</span>
    <span class="en-only">Sources are open-access arXiv full texts (cs.SD / eess.AS / cs.IR). Entries marked &ldquo;abstract-level only&rdquo; had no retrievable full text.</span>
  </footer>
</div>

<script>
  var filters = new Set(); var deepOnly = false;
  function togglePaper(head) { head.parentElement.classList.toggle('open'); }
  function setAll(open) { document.querySelectorAll('.card').forEach(function (c) { c.classList.toggle('open', open); }); }
  function toggleLang() { document.body.classList.toggle('lang-zh'); document.body.classList.toggle('lang-en'); }
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
    document.querySelectorAll('.day').forEach(function (d) {
      var any = Array.prototype.some.call(d.querySelectorAll('.card'), function (c) { return c.style.display !== 'none'; });
      d.style.display = any ? '' : 'none';
    });
    document.body.classList.toggle('no-results', shown === 0);
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement.id !== 'q') { e.preventDefault(); document.getElementById('q').focus(); }
  });
  var firstDay = document.querySelector('.day');
  if (firstDay) firstDay.querySelectorAll('.card').forEach(function (c) { c.classList.add('open'); });
</script>
</body>
</html>"""


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    days = load_days(data_dir)
    if not days:
        sys.stderr.write("no data files found in %s\n" % data_dir)
        return 1

    all_dates = sorted(days.keys(), reverse=True)
    months = sorted({d[:7] for d in all_dates}, reverse=True)

    os.makedirs(os.path.join(out_dir, "archive"), exist_ok=True)

    # index.html — most recent RECENT_DAYS days
    recent = {d: days[d] for d in all_dates[:RECENT_DAYS]}
    nav = ['<span class="here">最新 / Recent</span>']
    nav += ['<a href="archive/%s.html">%s</a>' % (m, m) for m in months[:6]]
    if len(months) > 6:
        nav.append('<a href="archive/index.html">全部月份 / all months</a>')
    index_html = build_page(
        recent,
        "音樂資訊檢索每日論文摘要 · 為 megan 整理 · 每篇含動機、背景、方法、限制、討論",
        "Music Information Retrieval daily digest · curated for megan · motivation, intro, method, limitations, discussion",
        " ".join(nav))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # one page per month
    for m in months:
        mdays = {d: days[d] for d in all_dates if d.startswith(m)}
        mnav = ['<a href="../index.html">← 最新 / Recent</a>']
        mnav += ['<span class="here">%s</span>' % x if x == m else '<a href="%s.html">%s</a>' % (x, x)
                 for x in months[:6]]
        mnav.append('<a href="index.html">全部月份 / all months</a>')
        with open(os.path.join(out_dir, "archive", "%s.html" % m), "w", encoding="utf-8") as f:
            f.write(build_page(mdays, "%s 月封存" % m, "%s archive" % m, " ".join(mnav)))

    # archive index
    rows = "".join(
        '<li><a href="%s.html">%s</a> — %d <span class="zh-only">篇</span><span class="en-only">papers</span>'
        ' / %d <span class="zh-only">天</span><span class="en-only">days</span></li>'
        % (m, m,
           sum(len(days[d]) for d in all_dates if d.startswith(m)),
           sum(1 for d in all_dates if d.startswith(m)))
        for m in months)
    with open(os.path.join(out_dir, "archive", "index.html"), "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Archive · MIR Daily Paper Digest</title>
<style>body{margin:0;background:#f7f7f5;color:#1a1a1a;font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC",sans-serif}
@media(prefers-color-scheme:dark){body{background:#141414;color:#ececec}}
.wrap{max-width:640px;margin:0 auto;padding:40px 20px}a{color:#8c5a2b}
@media(prefers-color-scheme:dark){a{color:#d4a373}}ul{padding-left:1.2em}li{margin:.4em 0}</style></head>
<body><div class="wrap"><h1>封存 / Archive</h1>
<p><a href="../index.html">← 回到最新 / back to recent</a></p><ul>%s</ul></div></body></html>""" % rows)

    print("built: index.html (%d days, %d papers), %d monthly page(s)"
          % (len(recent), sum(len(v) for v in recent.values()), len(months)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
