"""Diagnostic script to render a URL with Playwright and inspect DOM/XHR responses."""

import sys
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import MAX_SCROLLS, OUTPUTS_DIR, REQUEST_TIMEOUT_SECONDS, USER_AGENT


def debug_fetch(url: str) -> None:
    parsed = urlparse(url)
    domain = (parsed.netloc or "unknown").replace(":", "_")
    output_path = OUTPUTS_DIR / f"debug_{domain}.html"

    matching_json_urls: List[str] = []
    known_calendar = "SF Hardware Meetup"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="en-GB",
            timezone_id="Asia/Calcutta",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        def handle_response(response):
            try:
                content_type = response.headers.get("content-type", "").lower()
                if "json" in content_type or response.request.resource_type in ("xhr", "fetch"):
                    body_text = response.text()
                    if known_calendar in body_text:
                        matching_json_urls.append(response.url)
            except Exception:
                pass

        page.on("response", handle_response)

        timeout_ms = REQUEST_TIMEOUT_SECONDS * 1000
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            page.goto(url, wait_until="commit", timeout=timeout_ms)

        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception as exc:
            print(f"[warn] networkidle timed out: {exc}")

        page.wait_for_timeout(1500)

        prev_height = page.evaluate("document.body.scrollHeight")
        for scroll_idx in range(MAX_SCROLLS):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)
            new_height = page.evaluate("document.body.scrollHeight")
            print(f"Scroll {scroll_idx + 1}/{MAX_SCROLLS}: height {prev_height} -> {new_height}")
            if new_height <= prev_height:
                print(f"Page height stopped growing after {scroll_idx + 1} scroll(s).")
                break
            prev_height = new_height

        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        rendered_html = page.content()
        browser.close()

    output_path.write_text(rendered_html, encoding="utf-8")
    print(f"Saved rendered HTML ({len(rendered_html)} chars) to: {output_path}")

    try:
        soup = BeautifulSoup(rendered_html, "lxml")
    except Exception:
        soup = BeautifulSoup(rendered_html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    has_popular_calendars = "Popular Calendars" in page_text or "Popular Calendars" in rendered_html
    calendar_anchors = [
        a for a in soup.find_all("a", href=True) if "?k=c" in a["href"]
    ]

    print(f'Text "Popular Calendars" present: {has_popular_calendars}')
    print(f'Anchors with href containing "?k=c": {len(calendar_anchors)}')
    for a in calendar_anchors[:10]:
        print(f"  - href={a['href']} | text={a.get_text(' | ', strip=True)[:120]}")

    print(f'JSON responses containing "{known_calendar}": {len(matching_json_urls)}')
    for resp_url in matching_json_urls:
        print(f"  - {resp_url}")


if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://luma.com/sf"
    debug_fetch(target_url)
