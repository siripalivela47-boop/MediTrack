
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter
from pathlib import Path
from urllib.parse import urljoin, urlparse
import time

BASE_URL = "http://127.0.0.1:5000"
OUTPUT_DIR = Path("website_pdf_pages")
OUTPUT_DIR.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})

    page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2000)

    # Find internal website links
    links = page.locator("a[href]").evaluate_all("""
        links => links.map(a => a.href)
    """)

    base = urlparse(BASE_URL)
    urls = [BASE_URL]

    for link in links:
        parsed = urlparse(link)
        if parsed.netloc == base.netloc and parsed.scheme in ("http", "https"):
            clean_url = parsed._replace(fragment="").geturl()
            if clean_url not in urls:
                urls.append(clean_url)

    writer = PdfWriter()

    for index, url in enumerate(urls, start=1):
        try:
            print(f"Creating PDF page {index}: {url}")
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)

            # Print full page with colors and backgrounds
            pdf_path = OUTPUT_DIR / f"page_{index:02d}.pdf"
            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True
            )
            writer.append(str(pdf_path))

        except Exception as error:
            print(f"Skipped {url}: {error}")

    output_file = Path("MediTrack_Full_Website.pdf")
    with output_file.open("wb") as file:
        writer.write(file)

    writer.close()
    browser.close()

print(f"\nPDF saved at: {output_file.resolve()}")
