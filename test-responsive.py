"""Run rendered layout, preference, and contrast checks using Google Chrome."""
import html
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGE = (ROOT / "index.html").read_text().replace(' loading="lazy"', '')
CSS = (ROOT / "css/style.css").read_text()
assert CSS.count("@media") == 4
assert "max-width" not in CSS
CASES = [(w, False, False) for w in (375, 771, 772, 991, 992, 1440)]
CASES += [(772, True, False), (992, False, True), (375, True, True)]

CHECKS = """
const cards = [...document.querySelectorAll('figure')];
const images = [...document.images];
const grid = getComputedStyle(document.querySelector('.grid'));
const style = getComputedStyle(cards[0]);
const check = (condition, name) => { if (!condition) throw Error(name); };
check(innerWidth === expected.width, 'viewport');
check(cards.length === 9 && images.length === 9, 'nine figures and images');
check(images.every(i => i.complete && i.naturalWidth > 0 && i.alt.trim()), 'loaded images with alt');
check(grid.display === 'grid' && grid.gap === '10px', 'grid and gap');
check(grid.gridTemplateColumns.split(' ').length === (innerWidth < 772 ? 1 : 2), 'columns');
check(document.documentElement.scrollWidth <= innerWidth, 'no horizontal overflow');
cards.forEach((card, index) => {
  const s = getComputedStyle(card), rect = card.getBoundingClientRect();
  const full = innerWidth >= 772 && (innerWidth < 992 ? index === 8 : (index + 1) % 3 === 0);
  check((s.gridColumnStart === '1' && s.gridColumnEnd === '-1') === full, 'spanning figure ' + index);
  if (innerWidth >= 772 && innerWidth < 992) {
    check(s.borderRadius === '50%' && Math.abs(rect.width - rect.height) < 1, 'circular figure');
  }
  if (innerWidth >= 992) check(s.borderRadius === '0px', 'square corners');
});
check(matchMedia('(prefers-color-scheme: dark)').matches === expected.dark, 'dark preference');
check(matchMedia('(prefers-reduced-motion: reduce)').matches === expected.reduce, 'motion preference');
check(getComputedStyle(document.documentElement).scrollBehavior === (expected.reduce ? 'auto' : 'smooth'), 'scroll preference');
if (expected.dark) {
  check(style.backgroundColor === 'rgb(32, 40, 32)', 'dark figure');
  check(style.color === 'rgb(247, 233, 166)', 'light figure text');
  check(style.borderTopColor === 'rgb(0, 0, 0)', 'black border');
}
const luminance = color => {
  const values = color.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => {
    v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
  });
  return values[0] * .2126 + values[1] * .7152 + values[2] * .0722;
};
let minimum = 100;
for (const element of document.querySelectorAll('p, a, h1, h2, figcaption')) {
  let ancestor = element, background;
  do { background = getComputedStyle(ancestor).backgroundColor; ancestor = ancestor.parentElement; }
  while (background === 'rgba(0, 0, 0, 0)' && ancestor);
  const foreground = luminance(getComputedStyle(element).color), back = luminance(background);
  const ratio = (Math.max(foreground, back) + .05) / (Math.min(foreground, back) + .05);
  minimum = Math.min(minimum, ratio);
  check(ratio >= 4.5, 'contrast: ' + element.textContent);
}
return {pass: true, minimumContrast: minimum.toFixed(2)};
"""

with tempfile.TemporaryDirectory() as temporary:
    for width, dark, reduce in CASES:
        expected = json.dumps(dict(width=width, dark=dark, reduce=reduce))
        script = "<script>addEventListener('load', () => { let result; try { result = (() => { const expected = " + expected + ";" + CHECKS + "})(); } catch (error) { result = {error: error.message}; } parent.document.body.insertAdjacentHTML('beforeend', '<pre id=report>' + JSON.stringify(result) + '</pre>'); });</script>"
        content = PAGE.replace("<head>", f'<head><base href="{ROOT.as_uri()}/">') + script
        page = Path(temporary) / "check.html"
        page.write_text(f'<iframe style="border:0;width:{width}px;height:900px" srcdoc="{html.escape(content, quote=True)}"></iframe>')
        command = [CHROME, "--headless", "--disable-gpu", "--no-first-run",
                   f"--user-data-dir={temporary}/chrome", "--window-size=1600,1000",
                   "--virtual-time-budget=3000", "--dump-dom", page.as_uri()]
        if dark:
            command.insert(1, "--force-dark-mode")
        if reduce:
            command.insert(1, "--force-prefers-reduced-motion")
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        report = result.stdout.split('<pre id="report">')[-1].split('</pre>')[0]
        assert json.loads(report).get("pass"), report
        print(f"PASS {width}px dark={dark} reduced-motion={reduce}: {report}")
