# core/fetcher.py - Step 4: Hybrid web page downloader using httpx and Playwright Chromium.
# Uses httpx for fast static page retrieval and seamlessly escalates to Playwright
# for dynamic JavaScript rendering, client-side hydration, and lazy scrolling.

from typing import Tuple
from config import MAX_SCROLLS, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from utils.logger import logger


def _needs_playwright(url: str, html: str) -> bool:
    """Detects whether a web page requires headless browser rendering."""
    url_lower = url.lower()
    # Sites known to require JavaScript rendering or scroll virtualization
    if any(k in url_lower for k in ("lu.ma", "luma.com", "eventbrite", "meetup")):
        return True

    if not html or len(html.strip()) < 500:
        return True

    lower = html.lower()
    spa_markers = (
        "enable javascript",
        "you need to enable javascript",
        "id=\"__next\"",
        "id=\"root\"",
        "id=\"app\"",
        "data-reactroot",
        "timeline-section",
    )
    # If SPA marker exists and text content is very sparse
    if any(m in lower for m in spa_markers):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        text_len = len(soup.get_text().strip())
        if text_len < 1200:
            return True

    return False


def _fetch_httpx(url: str) -> Tuple[bool, str]:
    """Fast-path HTTP GET request using httpx."""
    try:
        import httpx

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
            return True, html
    except Exception as exc:
        logger.debug(f"httpx fast-path could not fetch {url}: {exc}")
        return False, str(exc)


def _fetch_playwright(url: str) -> Tuple[bool, str]:
    """Headless Chromium browser rendering using Playwright."""
    from playwright.sync_api import sync_playwright

    logger.info(f"Rendering page with Playwright (Chromium): {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="en-GB",
                timezone_id="Asia/Calcutta",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            # Evade basic automation detection
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Navigate and wait for initial DOM content
            timeout_ms = REQUEST_TIMEOUT_SECONDS * 1000
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as goto_err:
                logger.warning(
                    f"Navigation to {url} with wait_until='domcontentloaded' timed out or failed: {goto_err}. "
                    f"Retrying with wait_until='commit'..."
                )
                page.goto(url, wait_until="commit", timeout=timeout_ms)

            # Wait briefly for client-side JavaScript components to mount
            page.wait_for_timeout(2000)

            # Setup accumulator in page to preserve virtualized DOM items (such as Luma timeline sections).
            # Virtual DOM lists remove items from the DOM as they scroll above the viewport.
            page.evaluate("""() => {
                window.__accumulatedSections = [];
                window.__seenKeys = new Set();
                window.__snapshotTimeline = () => {
                    const sections = document.querySelectorAll('.timeline-section');
                    let newCount = 0;
                    sections.forEach(sec => {
                        const firstLink = sec.querySelector('a[href]')?.getAttribute('href') || sec.innerText.slice(0, 40);
                        if (!window.__seenKeys.has(firstLink)) {
                            window.__seenKeys.add(firstLink);
                            window.__accumulatedSections.push(sec.cloneNode(true));
                            newCount++;
                        }
                    });
                    return newCount;
                };
            }""")

            # Snapshot initial items before scrolling
            page.evaluate("window.__snapshotTimeline()")

            # Scroll until no new event cards appear, with a maximum of MAX_SCROLLS
            for scroll_idx in range(MAX_SCROLLS):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(1000)
                new_count = page.evaluate("window.__snapshotTimeline()")
                logger.debug(f"Scroll {scroll_idx + 1}/{MAX_SCROLLS}: {new_count} new timeline sections added.")
                if new_count == 0 and scroll_idx >= 2:
                    logger.info(f"No new event cards appeared after {scroll_idx + 1} scrolls. Stopping scroll.")
                    break

            # Prepend all accumulated sections to document.body so all sections are preserved in order
            page.evaluate("""() => {
                if (window.__accumulatedSections && window.__accumulatedSections.length > 0) {
                    const container = document.createElement('div');
                    container.id = 'preserved-timeline-sections';
                    window.__accumulatedSections.forEach(sec => container.appendChild(sec));
                    document.body.insertBefore(container, document.body.firstChild);
                }
            }""")

            rendered_html = page.content()
            browser.close()
            logger.info(f"Successfully rendered {len(rendered_html)} chars from {url} via Playwright")
            return True, rendered_html
    except Exception as exc:
        err_msg = f"Failed to fetch {url} with Playwright: {exc}"
        logger.error(err_msg)
        return False, err_msg


def fetch_page(url: str) -> Tuple[bool, str]:
    """
    Renders and downloads a web page using httpx fast-path, falling back to Playwright Chromium.
    
    Args:
        url: The web page URL to fetch.
        
    Returns:
        Tuple[bool, str]: (Success boolean, HTML content or error message)
    """
    url_lower = url.lower()
    # If the URL is known to require dynamic browser rendering, go directly to Playwright
    if any(k in url_lower for k in ("lu.ma", "luma.com")):
        return _fetch_playwright(url)

    # Fast path: try httpx
    ok, html_or_err = _fetch_httpx(url)
    if ok and not _needs_playwright(url, html_or_err):
        logger.info(f"Successfully fetched {len(html_or_err)} chars from {url} via httpx fast-path")
        return True, html_or_err

    # Fallback to Playwright
    return _fetch_playwright(url)
