"""Browser checks for the generated site.

    python3 verify_site.py                                        # local files
    python3 verify_site.py https://megan8821.github.io/idontwannareadpaper/

The site is one index page showing the latest day plus one page per topic
holding everything ever read in that subfield, so the checks below assert that
split: the index stays a single day, and a topic page stays a single topic.

With no argument the local build in this directory is checked; pass a base URL
to run the same checks against the deployed site.
"""
import os
import sys
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = sys.argv[1] if len(sys.argv) > 1 else "file://" + ROOT + "/"
if not BASE.endswith("/"):
    BASE += "/"
INDEX = BASE + "index.html"
print("checking " + BASE)
fails = []


def fetch(path):
    with urllib.request.urlopen(BASE + path) as r:
        return r.read().decode("utf-8")


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (" -- " + str(detail) if detail else ""))
    if not cond:
        fails.append(name)


with sync_playwright() as p:
    # PW_CHROMIUM lets a machine with a preinstalled browser point at it
    # instead of the copy Playwright downloads for itself.
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    b = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None,
                          proxy={"server": proxy} if proxy else None)
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
    # The index is one day; everything older is reached by topic. If a second
    # group ever appears here the two views have started overlapping.
    check("index lists exactly one day", pg.locator(".group").count() == 1,
          pg.locator(".group").count())
    check("sections per card == 5", pg.locator(".sec h4").count() == n * 5,
          pg.locator(".sec h4").count())
    check("zh visible / en hidden", pg.locator(".body.zh-only").first.is_visible()
          and not pg.locator(".body.en-only").first.is_visible())

    pg.click("#langBtn"); pg.wait_for_timeout(150)
    check("lang toggle -> en", pg.locator(".body.en-only").first.is_visible())
    # The root lang attribute has to follow the toggle, or a screen reader keeps
    # reading English prose with a Chinese voice.
    check("lang toggle updates root lang",
          pg.get_attribute("html", "lang") == "en", pg.get_attribute("html", "lang"))
    pg.click("#langBtn"); pg.wait_for_timeout(150)
    check("lang toggle back to zh", pg.get_attribute("html", "lang") == "zh-Hant",
          pg.get_attribute("html", "lang"))

    # The whole analysis is reachable only by expanding a card, so the card
    # headers must be operable without a mouse.
    head = pg.locator(".card-head").nth(1)
    was_open = "open" in (pg.locator(".card").nth(1).get_attribute("class") or "")
    head.focus()
    pg.keyboard.press("Enter"); pg.wait_for_timeout(150)
    now_open = "open" in (pg.locator(".card").nth(1).get_attribute("class") or "")
    check("card toggles by keyboard", now_open != was_open, "%s -> %s" % (was_open, now_open))
    check("aria-expanded tracks the card",
          head.get_attribute("aria-expanded") == ("true" if now_open else "false"),
          head.get_attribute("aria-expanded"))
    pg.keyboard.press("Enter"); pg.wait_for_timeout(150)

    # Long-form prose held to a readable column rather than the full card width.
    measure = pg.evaluate(
        """() => {
             const b = document.querySelector('.card.open .sec .body:not([hidden])');
             const card = document.querySelector('.card.open');
             return b ? {text: b.clientWidth, card: card.clientWidth} : null;
           }""")
    check("prose is held to a column",
          measure and measure["text"] < 720 and measure["text"] < measure["card"], measure)

    # Read the identifier off the card rather than assuming it is an arXiv one --
    # non-arXiv sources (TISMIR and friends) are labelled "DOI:", and a hardcoded
    # "arXiv:" split would raise here and take the whole run down with it.
    idline = pg.locator(".card").first.locator(".meta.mono").inner_text()
    aid = idline.split("·")[0].split(":", 1)[1].strip()
    pg.fill("#q", aid); pg.wait_for_timeout(200)
    vis = sum(1 for i in range(n) if pg.locator(".card").nth(i).is_visible())
    # An identifier belongs to exactly one paper, so it doubles as the
    # "search narrows correctly" case. Deriving the term instead of hardcoding a
    # phrase keeps this working as the index rolls over to a new day.
    check("search by ID narrows to exactly that paper",
          pg.locator(".card").first.is_visible() and vis == 1, "%s -> %d" % (aid, vis))
    # searching a read date must surface that day's papers, now that browsing
    # by date is gone and search is the only way back to a specific day
    day = pg.locator(".card").first.locator(".date-tag").inner_text().strip()
    pg.fill("#q", day); pg.wait_for_timeout(200)
    check("search by date surfaces that day",
          sum(1 for i in range(n) if pg.locator(".card").nth(i).is_visible()) == n, day)
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

    # nav to a topic page and back
    topic_link = pg.locator("nav.site a").first
    href = topic_link.get_attribute("href")
    check("nav points at a topic page", href and href.startswith("topics/"), href)
    topic_link.click()
    pg.wait_for_load_state()
    pg.wait_for_timeout(300)
    tn = pg.locator(".card").count()
    check("topic page has cards", tn > 0, tn)
    # The point of splitting by topic is that a topic page holds one topic.
    subfields = pg.eval_on_selector_all(
        ".card", "els => [...new Set(els.map(e => e.dataset.subfield))]")
    check("topic page holds exactly one subfield", len(subfields) == 1, subfields)
    check("topic page matches its filename",
          href == "topics/%s.html" % subfields[0], "%s vs %s" % (href, subfields))
    # Expanding a whole topic on load would defeat the purpose, so only the
    # index opts in to auto-expansion.
    check("topic page does not auto-expand", pg.locator(".card.open").count() == 0,
          pg.locator(".card.open").count())
    back = pg.locator('nav.site a[href="../index.html"]')
    check("topic page links back", back.count() == 1)
    back.first.click()
    pg.wait_for_load_state()
    pg.wait_for_timeout(300)
    check("back on index", pg.locator(".card").count() == n)

    # topics index
    pg.goto(BASE + "topics/index.html")
    pg.wait_for_timeout(200)
    check("topics index lists topics", pg.locator("li a").count() > 0)

    # A topic goes quiet whenever nothing in it happens to be read, which is not
    # a broken daily run -- so the freshness banner belongs to the index alone.
    pg.goto(BASE + href)
    pg.wait_for_timeout(200)
    check("no stale banner on topic pages", pg.locator("#stale").count() == 0)

    # The freshness banner is the only thing that reports a broken daily run,
    # so drive it at both a fresh and a stale date rather than trusting whatever
    # the current data happens to produce.
    pg.goto(INDEX)
    pg.wait_for_timeout(200)

    def stale_at(days_ago):
        return pg.evaluate(
            """(n) => {
                 const el = document.getElementById('stale');
                 const d = new Date(Date.now() - n * 86400000);
                 el.dataset.latest = d.toISOString().slice(0, 10);
                 updateStale();
                 return {hidden: el.hidden, text: el.innerText};
               }""", days_ago)

    check("fresh data shows no stale banner", stale_at(0)["hidden"])
    check("yesterday still counts as fresh", stale_at(1)["hidden"])
    two = stale_at(2)
    check("two days behind warns", not two["hidden"] and "2" in two["text"], two["text"][:60])
    ten = stale_at(10)
    check("banner counts the days", "10" in ten["text"], ten["text"][:60])

    src = fetch("index.html")
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
