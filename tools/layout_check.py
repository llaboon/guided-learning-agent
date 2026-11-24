"""DOM layout checks: SVG labels inside their boxes, sibling overlap, text contrast."""
import sys

from playwright.sync_api import sync_playwright

url = sys.argv[1]
JS = r"""
() => {
  const out = [];
  // loop diagram: each text inside its node rect
  document.querySelectorAll('#loop-wrap .node').forEach(g => {
    const r = g.querySelector('rect').getBBox();
    g.querySelectorAll('text').forEach(t => { const b = t.getBBox();
      if (b.x + b.width > r.x + r.width - 2) out.push('loop text overflows: ' + t.textContent); });
  });
  // overlapping siblings inside flex/grid containers
  const boxes = [...document.querySelectorAll('.stat, .metric, .btn, .chip, nav.tabs button, .seg button, .check, .panel, .msg')]
    .filter(e => e.offsetParent);
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.contains(b) || b.contains(a)) continue;
    const p = a.getBoundingClientRect(), q = b.getBoundingClientRect();
    const ox = Math.min(p.right, q.right) - Math.max(p.left, q.left);
    const oy = Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top);
    if (ox > 2 && oy > 2) out.push('overlap: ' + (a.className + '|' + a.innerText.slice(0, 20)) + ' <> ' + (b.className + '|' + b.innerText.slice(0, 20)));
  }
  // contrast of a few text roles
  const lum = c => { const m = c.match(/[\d.]+/g).map(Number); const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; };
    return .2126 * f(m[0]) + .7152 * f(m[1]) + .0722 * f(m[2]); };
  const bgOf = e => { while (e) { const c = getComputedStyle(e).backgroundColor; if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return c; e = e.parentElement; } return 'rgb(255,255,255)'; };
  const seen = new Set();
  document.querySelectorAll('h1, h2, h3, p, span, b, td, th, button, .bubble, label').forEach(e => {
    if (!e.offsetParent || !e.childNodes.length || ![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    const fg = getComputedStyle(e).color, bg = bgOf(e);
    if (/rgba\([^)]*, 0\.\d+\)/.test(bg)) return;
    const l1 = lum(fg), l2 = lum(bg), cr = (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05);
    const key = e.className + fg + bg;
    if (cr < 4 && !seen.has(key)) { seen.add(key); out.push(`low contrast ${cr.toFixed(2)}: ${e.tagName}.${e.className} "${e.innerText.slice(0, 24)}"`); }
  });
  return out;
}
"""
with sync_playwright() as p:
    b = p.chromium.launch()
    for vp in ({"width": 1440, "height": 900}, {"width": 390, "height": 844}):
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport=vp, color_scheme=theme)
            pg = ctx.new_page()
            pg.goto(url + "#live", wait_until="domcontentloaded")
            pg.wait_for_function("() => document.querySelector('#loop-wrap svg') && window.lucide")
            pg.wait_for_timeout(800)
            for v in ("live", "results", "explore", "repro"):
                pg.click(f"nav.tabs button[data-view={v}]")
                pg.wait_for_timeout(900)
                if v == "explore":
                    pg.locator("#ex-list tbody tr.click").first.click()
                    pg.wait_for_selector("#ex-detail .chat .msg")
                res = pg.evaluate(JS)
                for r in res[:12]:
                    print(vp["width"], theme, v, r)
            ctx.close()
    b.close()
print("LAYOUT_CHECK_DONE")
