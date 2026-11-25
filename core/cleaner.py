# core/cleaner.py - Step 5: Cleans raw HTML and prepares text for extraction.
# This file strips script, style, and navigation tags while preserving readable text
# and hyperlinked URLs so the engine can extract links and details cleanly.

import re
from typing import List
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Comment
from utils.logger import logger

# HTML tags that add visual noise or code rather than content
UNWANTED_TAGS = [
    "script", "style", "noscript", "svg", "canvas", "video", "audio",
    "header", "footer", "nav", "iframe", "embed", "object"
]


def clean_html(raw_html: str, base_url: str = "") -> str:
    """
    Cleans HTML markup to produce readable text while preserving anchor links.
    
    Args:
        raw_html: The raw HTML string fetched from the webpage.
        base_url: The page URL used to resolve relative links into absolute URLs.
        
    Returns:
        str: Cleaned text containing links in [text](url) format.
    """
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "lxml")

    # Remove HTML comments
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # Remove unwanted scripts, styles, and navigational elements
    for tag in soup.find_all(UNWANTED_TAGS):
        tag.decompose()

    # Preserve hyperlinks: replace <a> tags with formatted [text](url) representation
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        anchor_text = a.get_text(separator=" ", strip=True)

        # Fallback to aria-label, title, or image alt text for modern responsive cards
        if not anchor_text:
            anchor_text = a.get("aria-label", "").strip() or a.get("title", "").strip()
        if not anchor_text:
            img = a.find("img", alt=True)
            if img:
                anchor_text = img["alt"].strip()
        if not anchor_text:
            anchor_text = "Link"

        # Ignore javascript: and internal page jump fragments
        if href and not href.startswith(("javascript:", "#")):
            full_url = urljoin(base_url, href) if base_url else href
            a.replace_with(f" [{anchor_text}]({full_url}) ")
        else:
            a.decompose()

    # Extract cleaned text
    text = soup.get_text(separator="\n", strip=True)

    # Collapse multiple consecutive blank lines or spaces
    cleaned_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    meaningful_lines = [line for line in cleaned_lines if line]
    cleaned_text = "\n".join(meaningful_lines)

    logger.debug(f"Cleaned HTML from {len(raw_html)} raw chars to {len(cleaned_text)} text chars.")
    return cleaned_text


def chunk_text(text: str, chunk_size: int = 8000) -> List[str]:
    """
    Splits long cleaned text into smaller chunks to fit comfortably within processing limits.
    
    Args:
        text: The cleaned text to be split.
        chunk_size: Maximum approximate character length per chunk.
        
    Returns:
        List[str]: A list of text chunks split across line boundaries.
    """
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_length = 0

    lines = text.split("\n")
    for line in lines:
        line_len = len(line) + 1  # Account for newline
        if current_length + line_len > chunk_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = line_len
        else:
            current_chunk.append(line)
            current_length += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    logger.info(f"Split text of {len(text)} characters into {len(chunks)} chunks.")
    return chunks
