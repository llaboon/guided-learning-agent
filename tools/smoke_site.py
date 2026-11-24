"""Browser smoke test for the built site (Playwright, Chromium).

    python tools/smoke_site.py http://127.0.0.1:8765/ [--shots DIR]

Runs an offline (mock-model) live session through Pyodide, opens the results
and trace views, and fails on console errors or empty views. With
``--endpoint URL`` it also runs a short live session against that
OpenAI-compatible endpoint with a dummy key and checks that the key never
appears in the page.
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--shots", default=None)
    ap.add_argument("--live-timeout", type=int, default=180)
    ap.add_argument("--endpoint", default=None)
    args = ap.parse_args()
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, vp in (("desktop", {"width": 1400, "height": 900}),
                         ("mobile", {"width": 390, "height": 844})):
            page = browser.new_page(viewport=vp)
            page.on("console", lambda m: m.type == "error" and errors.append(f"{name} console: {m.text}"))
            page.on("pageerror", lambda e: errors.append(f"{name} pageerror: {e}"))
            page.goto(args.url + "#live")
            page.wait_for_timeout(800)
            if name == "desktop":
                page.click("#mock-btn")
                page.wait_for_function(
                    "() => /Finished|Error|error/.test(document.getElementById('live-status').innerText)"
                    " || document.querySelector('#live-status .notice.bad')",
                    timeout=args.live_timeout * 1000)
                status = page.inner_text("#live-status")
                n_cards = page.locator(".session-card").count()
                n_turns = page.locator(".session-card .turn").count()
                print(f"[live] status={status!r} cards={n_cards} turns={n_turns}")
                if "Finished" not in status or n_cards < 1 or n_turns < 1:
                    errors.append(f"live session failed: {status}")
            if shots:
                page.screenshot(path=str(shots / f"{name}_live.png"), full_page=False)
            page.click("nav.tabs button[data-view=results]")
            page.wait_for_selector("#summary-table tbody tr")
            rows = page.locator("#summary-table tbody tr").count()
            print(f"[results] {name}: {rows} condition rows")
            if shots:
                page.screenshot(path=str(shots / f"{name}_results.png"), full_page=True)
            page.click("nav.tabs button[data-view=explore]")
            page.wait_for_selector("#ex-list tbody tr.click")
            page.locator("#ex-list tbody tr.click").first.click()
            page.wait_for_selector("#ex-detail .transcript .turn")
            turns = page.locator("#ex-detail .transcript .turn").count()
            print(f"[explore] {name}: {turns} transcript rows")
            if shots:
                page.screenshot(path=str(shots / f"{name}_explore.png"), full_page=False)
            # Horizontal overflow check.
            over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            if over > 2:
                errors.append(f"{name}: page overflows horizontally by {over}px")
            page.close()
        if args.endpoint:
            page = browser.new_page()
            page.on("pageerror", lambda e: errors.append(f"endpoint pageerror: {e}"))
            page.goto(args.url + "#live")
            page.wait_for_timeout(500)
            page.select_option("#preset", "custom")
            page.fill("#base-url", args.endpoint)
            page.fill("#model", "stub-model")
            page.fill("#api-key", "sk-smoke-NOTAREALKEY")
            page.fill("#turns", "4")
            page.click("#run-btn")
            page.wait_for_function(
                "() => /Finished/.test(document.getElementById('live-status').innerText)"
                " || document.querySelector('#live-status .notice.bad')",
                timeout=args.live_timeout * 1000)
            status = page.inner_text("#live-status")
            turns = page.locator(".session-card .turn").count()
            print(f"[endpoint] status={status!r} turns={turns}")
            if "Finished" not in status or turns < 1:
                errors.append(f"endpoint session failed: {status}")
            if "NOTAREALKEY" in page.content():
                errors.append("API key visible in page DOM")
            page.close()
        browser.close()
    for e in errors:
        print("[error]", e)
    print("SITE_SMOKE_" + ("FAILED" if errors else "PASSED"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
