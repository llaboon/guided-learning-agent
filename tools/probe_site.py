"""Load the site once and print console errors and failed requests."""
import sys

from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.on("console", lambda m: m.type in ("error", "warning") and print("console", m.type, m.text[:200]))
    pg.on("pageerror", lambda e: print("pageerror", e))
    pg.on("requestfailed", lambda r: print("failed", r.url[:120]))
    pg.goto(url + "#live", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)
    print("svg", pg.evaluate("!!document.querySelector('#loop-wrap svg')"),
          "lucide", pg.evaluate("!!window.lucide"))
    if "--live" in sys.argv:
        pg.click("#mock-btn")
        for _ in range(24):
            pg.wait_for_timeout(5000)
            st = pg.inner_text("#live-status")
            n = pg.locator(".session-card .chat .msg.tutor").count()
            print("status:", st.replace("\n", " ")[:160], "| tutor msgs:", n, flush=True)
            if "Finished" in st or "rror" in st:
                break
    b.close()
