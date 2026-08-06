"""Browser checks for the generated site. Run from the repo root: python3 verify_site.py"""
import os
import sys
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = "file://" + os.path.join(ROOT, "index.html")
fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (" -- " + str(detail) if detail else ""))
    if not cond:
        fails.append(name)


with sync_playwright() as p:
    b = p.chromium.launch()
    errors = []
    pg = b.new_page(viewport={"width": 1280, "height": 1000})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(INDEX)
    pg.wait_for_timeout(400)

    n = pg.locator(".card").count()
    check("no JS errors on load", not errors, errors)
    check("cards rendered", n > 0, n)
    check("latest day expanded", pg.locator(".card.open").count() > 0)
    check("sections per card == 5", pg.locator(".sec h4").count() == n * 5,
          pg.locator(".sec h4").count())
    check("zh visible / en hidden", pg.locator(".body.zh-only").first.is_visible()
          and not pg.locator(".body.en-only").first.is_visible())

    pg.click("#langBtn"); pg.wait_for_timeout(150)
    check("lang toggle -> en", pg.locator(".body.en-only").first.is_visible())
    pg.click("#langBtn"); pg.wait_for_timeout(150)

    # searching a card's arXiv ID must at minimum surface that card
    aid = pg.locator(".card").first.inner_text().split("arXiv:")[1].split(" ")[0].strip()
    pg.fill("#q", aid); pg.wait_for_timeout(200)
    vis = sum(1 for i in range(n) if pg.locator(".card").nth(i).is_visible())
    check("search by arXiv ID surfaces that paper",
          pg.locator(".card").first.is_visible() and 1 <= vis <= n, "%s -> %d" % (aid, vis))
    # a term unique to one paper must narrow to that one paper
    pg.fill("#q", "flow-matching rendering"); pg.wait_for_timeout(200)
    vis1 = sum(1 for i in range(n) if pg.locator(".card").nth(i).is_visible())
    check("distinctive phrase narrows to one", vis1 == 1, vis1)
    pg.fill("#q", "zzznope"); pg.wait_for_timeout(200)
    check("empty state", pg.locator(".empty").is_visible())
    pg.fill("#q", ""); pg.wait_for_timeout(200)

    pg.click("#deepOnly"); pg.wait_for_timeout(200)
    deep_vis = sum(1 for i in range(n) if pg.locator(".card").nth(i).is_visible())
    check("deep-only filter", deep_vis == pg.locator('.card[data-deep="1"]').count(), deep_vis)
    pg.click("#deepOnly"); pg.wait_for_timeout(200)

    pg.click("text=全部收合"); pg.wait_for_timeout(150)
    check("collapse all", pg.locator(".card.open").count() == 0)
    pg.click("text=全部展開"); pg.wait_for_timeout(150)
    check("expand all", pg.locator(".card.open").count() == n)

    # nav to monthly archive and back
    month_link = pg.locator("nav.site a").first
    href = month_link.get_attribute("href")
    check("nav points at archive", href and href.startswith("archive/"), href)
    month_link.click()
    pg.wait_for_load_state()
    pg.wait_for_timeout(300)
    check("monthly page has cards", pg.locator(".card").count() > 0)
    back = pg.locator('nav.site a[href="../index.html"]')
    check("monthly page links back", back.count() == 1)
    back.first.click()
    pg.wait_for_load_state()
    pg.wait_for_timeout(300)
    check("back on index", pg.locator(".card").count() == n)

    # archive index
    pg.goto("file://" + os.path.join(ROOT, "archive", "index.html"))
    pg.wait_for_timeout(200)
    check("archive index lists months", pg.locator("li a").count() > 0)

    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    check("no localStorage", "localStorage" not in src and "sessionStorage" not in src)
    check("self-contained", "<link" not in src and "<script src" not in src)
    check("no JS errors overall", not errors, errors)

    m = b.new_page(viewport={"width": 390, "height": 844})
    m.goto(INDEX); m.wait_for_timeout(300)
    check("no mobile overflow",
          not m.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"))
    b.close()

print("\n%d checks failed" % len(fails))
sys.exit(1 if fails else 0)
