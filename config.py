# config.py - Central configuration settings for the data extraction tool.
# This file stores all customizable constants such as timeouts, user agent,
# and file paths so they can be managed from a single place.

import os
from pathlib import Path
from dotenv import load_dotenv

# Optional local environment loading (no .env file is required)
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"

# Ensure outputs directory exists
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Network and Scraping Settings
REQUEST_TIMEOUT_SECONDS = 35  # Maximum time to wait for HTTP request and browser navigation
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Scraping and Scrolling Settings
MAX_SCROLLS = 10  # Maximum scroll operations to load lazy-rendered items
