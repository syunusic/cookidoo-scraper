import json
import os
import re
import time
import random
from typing import Optional

from playwright.sync_api import sync_playwright

from app.database import async_session
from app.models import Recipe, RecipeIngredient
from app.scraper.cookidoo import parse_ingredient_text, parse_iso_duration

BASE_URL = "https://cookidoo.es"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".cookidoo_cookies.json")
RECIPE_ID_PATTERN = re.compile(r"/recipes/recipe/([^/]+)/r(\d+)")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}


def login(email: str, password: str) -> list[dict]:
    """Log in to Cookidoo using Playwright and return cookies."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="es-ES",
        )
        page = context.new_page()

        print("Navigating to login page...")
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
            print("Login successful!")
        except:
            # Check for error messages
            error_text = page.text_content("text=error", timeout=3000)
            if error_text:
                print(f"Login error: {error_text}")
            else:
                print(f"Current URL after login: {page.url}")
            return []

        # Save cookies
        cookies = context.cookies()
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f)
        print(f"Saved {len(cookies)} cookies to {COOKIE_FILE}")

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
    print(f"  Searching sortby={sortby}...")
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
            print(f"    Scroll {scroll + 1}: {len(ids)} recipes found (+{added})")
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
            print(f"    -> +{len(ids) - before} new recipes")

        # Also browse collections for more IDs
        col_url = f"{BASE_URL}/search/es-ES?countries=es&context=collections&sortby=publishedAt"
        print(f"  Browsing collections...")
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

        print(f"  Found {len(seen_cols)} collections")
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
                print(f"    Collection {col_id}: {len(ids)} total recipes")
            except Exception:
                continue

        browser.close()

    print(f"Total unique recipe IDs discovered: {len(ids)}")
    return ids


def scrape_recipe_page(recipe_id: str, lang: str = "es-ES") -> Optional[dict]:
    """Scrape a single recipe page using authenticated session."""
    import requests
    from bs4 import BeautifulSoup
    import json

    session = get_authenticated_session()
    url = f"{BASE_URL}/recipes/recipe/{lang}/r{recipe_id}"

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    json_ld = soup.find("script", type="application/ld+json")
    if not json_ld:
        return None

    try:
        data = json.loads(json_ld.string)
    except (json.JSONDecodeError, AttributeError):
        return None

    if not data.get("name"):
        return None

    difficulty_el = soup.find("rdp-difficulty")
    difficulty = ""
    if difficulty_el:
        p = difficulty_el.find("p")
        if p:
            difficulty = p.get_text(strip=True)

    categories_raw = data.get("recipeCategory", [])
    if isinstance(categories_raw, str):
        categories_raw = [categories_raw]

    nutrition = data.get("nutrition", {})

    result = {
        "cookidoo_id": f"r{recipe_id}",
        "name": data.get("name"),
        "url": url,
        "image_url": data.get("image", ""),
        "language": lang,
        "country": lang.split("-")[0] if "-" in lang else lang,
        "total_time": parse_iso_duration(data.get("totalTime")),
        "prep_time": parse_iso_duration(data.get("prepTime")),
        "cook_time": parse_iso_duration(data.get("cookTime")),
        "yield_amount": data.get("recipeYield"),
        "difficulty": difficulty,
        "rating": None,
        "review_count": None,
        "categories": categories_raw,
        "calories": nutrition.get("calories"),
        "carbs": nutrition.get("carbohydrateContent"),
        "fat": nutrition.get("fatContent"),
        "protein": nutrition.get("proteinContent"),
        "fiber": nutrition.get("fiberContent"),
        "raw_json": data,
        "ingredients_raw": data.get("recipeIngredient", []),
    }

    # Extract aggregate rating from JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            agg = json.loads(script.string)
            if isinstance(agg, dict) and agg.get("@type") == "AggregateRating":
                result["rating"] = agg.get("ratingValue")
                result["review_count"] = agg.get("reviewCount")
                break
        except (json.JSONDecodeError, AttributeError):
            continue

    return result





async def save_recipe(recipe_data: dict):
    from sqlalchemy import select
    async with async_session() as session:
        q = select(Recipe).where(Recipe.cookidoo_id == recipe_data["cookidoo_id"])
        r = await session.execute(q)
        existing = r.scalar_one_or_none()
        if existing:
            return existing

        recipe = Recipe(
            cookidoo_id=recipe_data["cookidoo_id"],
            name=recipe_data["name"],
            url=recipe_data["url"],
            image_url=recipe_data.get("image_url", ""),
            language=recipe_data.get("language", "es-ES"),
            country=recipe_data.get("country", "es"),
            total_time=recipe_data.get("total_time"),
            prep_time=recipe_data.get("prep_time"),
            cook_time=recipe_data.get("cook_time"),
            yield_amount=recipe_data.get("yield_amount"),
            difficulty=recipe_data.get("difficulty"),
            rating=recipe_data.get("rating"),
            review_count=recipe_data.get("review_count"),
            categories=recipe_data.get("categories"),
            calories=recipe_data.get("calories"),
            carbs=recipe_data.get("carbs"),
            fat=recipe_data.get("fat"),
            protein=recipe_data.get("protein"),
            fiber=recipe_data.get("fiber"),
            raw_json=recipe_data.get("raw_json"),
        )
        session.add(recipe)
        await session.flush()

        for raw_ing in recipe_data.get("ingredients_raw", []):
            name, qty, unit, note = parse_ingredient_text(raw_ing)
            ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                raw_text=raw_ing,
                ingredient_name=name or raw_ing,
                quantity=qty,
                unit=unit,
                note=note,
            )
            session.add(ingredient)

        await session.commit()
        return recipe


async def scrape_all(limit: int = 0):
    import asyncio
    from sqlalchemy import select

    loop = asyncio.get_running_loop()
    ids = await loop.run_in_executor(None, discover_recipe_ids, 20)
    print(f"Discovered {len(ids)} total recipe IDs")

    # Load existing IDs from DB to skip them
    async with async_session() as session:
        r = await session.execute(select(Recipe.cookidoo_id))
        existing = {row[0] for row in r.all()}
    print(f"Already in DB: {len(existing)} recipes")

    new_ids = sorted(ids - existing)
    print(f"New recipes to scrape: {len(new_ids)}")

    if limit > 0:
        new_ids = new_ids[:limit]

    if not new_ids:
        print("Nothing new to scrape.")
        return 0

    count = 0
    for i, recipe_id in enumerate(new_ids):
        data = scrape_recipe_page(recipe_id)
        if data:
            await save_recipe(data)
            count += 1
            print(f"[{i+1}/{len(new_ids)}] {data['name']}")
        else:
            print(f"[{i+1}/{len(new_ids)}] r{recipe_id} -> FAILED")
        time.sleep(random.uniform(1, 2))

    return count
