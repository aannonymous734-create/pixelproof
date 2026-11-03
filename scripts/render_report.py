"""Render docs/REPORT.md -> docs/REPORT.pdf (pandoc -> HTML -> headless Chromium, no LaTeX needed).
Needs pandoc and Playwright:  pip install -r requirements-report.txt
(pandoc is taken from PATH, else from the bundled pypandoc_binary; the browser is Playwright's Chromium
if installed with `playwright install chromium`, else the system Edge or Chrome).

The report source uses result-file tokens ({{source:path|format}}); this script first resolves them
with scripts/check_numbers.py (which fails if any number does not come from results/), so the PDF can
only ever contain reproduced numbers.

  python scripts/render_report.py
"""
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FOOTER = ('<div style="font-size:7pt;width:100%;text-align:center;color:#777;font-family:sans-serif">'
          'TSYP14 Track 3 · anonymous Phase 1 report · <span class="pageNumber"></span> / '
          '<span class="totalPages"></span></div>')


def pandoc_exe() -> str:
    exe = shutil.which("pandoc")
    if exe:
        return exe
    try:
        import pypandoc
        return pypandoc.get_pandoc_path()
    except Exception:
        sys.exit("pandoc not found: install it, or run  pip install -r requirements-report.txt")


async def launch(p):
    try:
        return await p.chromium.launch()
    except Exception as first:  # Playwright's own Chromium is not installed: use the system browser
        for channel in ("msedge", "chrome"):
            try:
                return await p.chromium.launch(channel=channel)
            except Exception:
                continue
        raise first


async def to_pdf(html: Path, pdf: Path):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await launch(p)
        pg = await b.new_page()
        await pg.goto(html.resolve().as_uri())
        await pg.wait_for_timeout(500)
        await pg.pdf(path=str(pdf), format="A4", print_background=True, display_header_footer=True,
                     header_template="<span></span>", footer_template=FOOTER,
                     margin={"top": "16mm", "bottom": "18mm", "left": "15mm", "right": "15mm"})
        await b.close()


def main():
    # 1. resolve every result-file token (fails on any mismatch)
    resolved = DOCS / "REPORT.resolved.md"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_numbers.py"),
                        str(DOCS / "REPORT.md"), "--render", str(resolved)])
    if r.returncode != 0:
        sys.exit("check_numbers.py found unresolved numbers; not rendering")
    # 2. pandoc -> HTML  (run in DOCS so relative image/css paths resolve; output path relative to DOCS)
    html = DOCS / "build" / "REPORT.html"
    html.parent.mkdir(exist_ok=True)
    subprocess.run([pandoc_exe(), "REPORT.resolved.md", "-s", "--mathml", "--embed-resources",
                    "--resource-path=.:..", "--css", "build/report.css",
                    "--metadata", "pagetitle=PixelProof Phase 1 report",
                    "-o", "build/REPORT.html"], cwd=DOCS, check=True)
    # 3. HTML -> PDF
    asyncio.run(to_pdf(html, DOCS / "REPORT.pdf"))
    resolved.unlink(missing_ok=True)
    shutil.copyfile(DOCS / "REPORT.pdf", ROOT / "PixelProof_Phase1_Report.pdf")  # the file to submit
    print("wrote", DOCS / "REPORT.pdf", "and", ROOT / "PixelProof_Phase1_Report.pdf")


if __name__ == "__main__":
    main()
