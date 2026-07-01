import json
import logging
import os
import re
import time
import random
from typing import Optional

from playwright.sync_api import sync_playwright

from app.scraper.cookidoo import fetch_discoverable_ids, get_country_from_lang
from app.scraper.common import HEADERS, parse_recipe_html, save_recipe

logger = logging.getLogger(__name__)

BASE_URL = "https://cookidoo.es"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".cookidoo_cookies.json")
RECIPE_ID_PATTERN = re.compile(r"/recipes/recipe/([^/]+)/r(\d+)")


def login(email: str, password: str) -> list[dict]:
    """Log in to Cookidoo using Playwright and return cookies."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="es-ES",
        )
        page = context.new_page()

        logger.info("Navigating to login page...")
        page.goto(f"{BASE_URL}/profile/es-ES/login?redirectAfterLogin=%2Ffoundation%2Fes-ES%2Fexplore", wait_until="networkidle")

        # Wait for the login form to be ready
        page.wait_for_selector('input[type="email"]', timeout=15000)

        # Fill login form
        page.fill('input[type="email"]', email)
        page.fill('input[type="password"]', password)

        # Click login button
        page.click('button:has-text("Iniciar sesión")')

        # Wait for navigation after login (redirect to explore page)
        try:
            page.wait_for_url("**/foundation/es-ES/**", timeout=20000)
            logger.info("Login successful!")
        except:
            # Check for error messages
            error_text = page.text_content("text=error", timeout=3000)
            if error_text:
                logger.error("Login error: %s", error_text)
            else:
                logger.warning("Current URL after login: %s", page.url)
            return []

        # Save cookies
        cookies = context.cookies()
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f)
        logger.info("Saved %d cookies to %s", len(cookies), COOKIE_FILE)

        # Also save the localStorage/sessionStorage for API tokens
        storage_state = context.storage_state()
        storage_file = COOKIE_FILE.replace(".json", "_storage.json")
        with open(storage_file, "w") as f:
            json.dump(storage_state, f)

        browser.close()
        return cookies


def get_authenticated_session():
    """Get a requests session with saved cookies."""
    import requests
    session = requests.Session()
    session.headers.update(HEADERS)

    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE) as f:
            cookies = json.load(f)
        for cookie in cookies:
            if cookie.get("domain") and "cookidoo" in cookie.get("domain", ""):
                session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"])
    return session


SORTBY_GROUPS = ["publishedAt", "rating", "name", "totalTime"]


def _discover_from_search(page, sortby: str, max_scrolls: int = 20) -> set[str]:
    """Scroll the search page with a given sort and collect recipe IDs."""
    ids = set()
    search_url = (
        f"{BASE_URL}/search/es-ES?"
        f"countries=es&languages=es&context=recipes&sortby={sortby}"
    )
    logger.info("  Searching sortby=%s...", sortby)
    page.goto(search_url, wait_until="networkidle")
    page.wait_for_timeout(3000)

    for btn_text in ["Aceptar", "Aceptar todas", "Cerrar", "Rechazar"]:
        try:
            btn = page.locator(f"button:has-text('{btn_text}')")
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

    prev_count = 0
    for scroll in range(max_scrolls):
        links = page.locator("a[href*='/recipes/recipe/']").all()
        new_ids = set()
        for link in links:
            href = link.get_attribute("href")
            if href:
                m = RECIPE_ID_PATTERN.search(href)
                if m:
                    new_ids.add(m.group(2))
        ids.update(new_ids)

        added = len(ids) - prev_count
        if added > 0:
            logger.info("    Scroll %d: %d recipes found (+%d)", scroll + 1, len(ids), added)
        prev_count = len(ids)

        if added == 0 and scroll > 2:
            break

        try:
            btn = page.locator("button:has-text('Ver más'), button:has-text('Mostrar más'), button:has-text('Cargar más')")
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_timeout(2000)
                continue
        except Exception:
            pass

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

    return ids


def discover_recipe_ids(max_scrolls: int = 20) -> set[str]:
    """Discover recipe IDs by browsing Cookidoo search with Playwright (real browser).
    Iterates over multiple sort orders to maximize coverage.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        storage_file = COOKIE_FILE.replace(".json", "_storage.json")
        if os.path.exists(storage_file):
            with open(storage_file) as f:
                storage = json.load(f)
            context = browser.new_context(
                storage_state=storage,
                user_agent=HEADERS["User-Agent"],
                locale="es-ES",
            )
        elif os.path.exists(COOKIE_FILE):
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="es-ES",
            )
            with open(COOKIE_FILE) as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
        else:
            browser.close()
            return set()

        page = context.new_page()
        ids = set()

        for sortby in SORTBY_GROUPS:
            sort_ids = _discover_from_search(page, sortby, max_scrolls)
            before = len(ids)
            ids |= sort_ids
            logger.info("    -> +%d new recipes", len(ids) - before)

        # Also browse collections for more IDs
        col_url = f"{BASE_URL}/search/es-ES?countries=es&context=collections&sortby=publishedAt"
        logger.info("  Browsing collections...")
        page.goto(col_url, wait_until="networkidle")
        page.wait_for_timeout(3000)

        col_links = page.locator("a[href*='/collection/es-ES/']").all()
        seen_cols = set()
        for link in col_links:
            href = link.get_attribute("href")
            if href and "/collection/es-ES/p/" in href:
                col_id = href.split("/collection/es-ES/p/")[-1].split("?")[0]
                if col_id and col_id not in seen_cols:
                    seen_cols.add(col_id)

        logger.info("  Found %d collections", len(seen_cols))
        for col_id in list(seen_cols)[:50]:
            try:
                page.goto(f"{BASE_URL}/collection/es-ES/p/{col_id}", wait_until="networkidle")
                page.wait_for_timeout(2000)
                links = page.locator("a[href*='/recipes/recipe/']").all()
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        m = RECIPE_ID_PATTERN.search(href)
                        if m:
                            ids.add(m.group(2))
                logger.info("    Collection %s: %d total recipes", col_id, len(ids))
            except Exception:
                continue

        browser.close()

    logger.info("Total unique recipe IDs discovered: %d", len(ids))
    return ids


def scrape_recipe_page(recipe_id: str, lang: str = "es-ES") -> Optional[dict]:
    """Scrape a single recipe page using authenticated session."""
    import requests

    session = get_authenticated_session()
    url = f"{BASE_URL}/recipes/recipe/{lang}/r{recipe_id}"

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    return parse_recipe_html(resp.text, url, recipe_id, lang, get_country_from_lang(lang))


async def scrape_all(limit: int = 0):
    import asyncio
    from sqlalchemy import select

    from app.database import async_session
    from app.models import Recipe

    # Fast discovery via requests-based stripe API (~12 calls, ~10s)
    # No need for slow Playwright browser — auth is only needed for the
    # actual recipe page scraping.
    loop = asyncio.get_running_loop()
    ids = await loop.run_in_executor(None, fetch_discoverable_ids)
    logger.info("Discovered %d total recipe IDs", len(ids))

    # Load existing IDs from DB to skip them
    async with async_session() as session:
        r = await session.execute(select(Recipe.cookidoo_id))
        existing = {row[0] for row in r.all()}
    logger.info("Already in DB: %d recipes", len(existing))

    existing_numeric = {rid.lstrip("r") for rid in existing}
    new_ids = sorted(set(ids) - existing_numeric)
    logger.info("New recipes to scrape: %d", len(new_ids))

    if limit > 0:
        new_ids = new_ids[:limit]

    if not new_ids:
        logger.info("Nothing new to scrape.")
        return 0

    count = 0
    for i, recipe_id in enumerate(new_ids):
        data = scrape_recipe_page(recipe_id)
        if data:
            await save_recipe(data)
            count += 1
            logger.info("[%d/%d] %s", i + 1, len(new_ids), data["name"])
        else:
            logger.warning("[%d/%d] r%s -> FAILED", i + 1, len(new_ids), recipe_id)
        time.sleep(random.uniform(1, 2))

    return count
