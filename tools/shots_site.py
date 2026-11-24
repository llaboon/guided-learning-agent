"""Screenshots of every tab, desktop and mobile, light and dark.

    python tools/shots_site.py http://127.0.0.1:8765/ tools/shots [--live]
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

url, out = sys.argv[1], Path(sys.argv[2])
live = "--live" in sys.argv
out.mkdir(parents=True, exist_ok=True)
problems = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for vp_name, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport=vp, color_scheme=theme)
            page = ctx.new_page()
            page.on("pageerror", lambda e: problems.append(f"pageerror {e}"))
            page.goto(url + "#live", wait_until="domcontentloaded")
            page.wait_for_function("() => window.lucide && document.querySelector('#loop-wrap svg')", timeout=60000)
            page.wait_for_timeout(800)
            tag = f"{vp_name}_{theme}"
            page.screenshot(path=str(out / f"{tag}_0top.png"))
            if live and theme == "light":
                page.click("#mock-btn")
                page.wait_for_function("() => /Finished|rror/.test(document.getElementById('live-status').innerText)", timeout=240000)
                page.locator("#live-status").scroll_into_view_if_needed()
                page.wait_for_timeout(600)
                page.screenshot(path=str(out / f"{tag}_1live.png"), full_page=False)
                page.evaluate("document.querySelector('.session-card').scrollIntoView()")
                page.wait_for_timeout(300)
                page.screenshot(path=str(out / f"{tag}_1live_card.png"))
            for v in ("results", "explore", "repro"):
                page.click(f"nav.tabs button[data-view={v}]")
                page.wait_for_timeout(900)
                if v == "explore":
                    page.locator("#ex-list tbody tr.click").first.click()
                    page.wait_for_selector("#ex-detail .chat .msg")
                    page.wait_for_timeout(400)
                page.evaluate(f"document.getElementById('view-{v}').scrollIntoView()")
                page.wait_for_timeout(300)
                page.screenshot(path=str(out / f"{tag}_{v}.png"))
                over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                if over > 2:
                    problems.append(f"{tag} {v}: horizontal overflow {over}px")
                clipped = page.evaluate("""() => [...document.querySelectorAll('button, .btn, .chip, .pill')]
                  .filter(e => e.offsetParent && e.scrollWidth > e.clientWidth + 1).map(e => e.innerText.slice(0, 30))""")
                if clipped:
                    problems.append(f"{tag} {v}: clipped {clipped[:5]}")
            ctx.close()
    b.close()
print("\n".join(problems) or "NO_PROBLEMS")
