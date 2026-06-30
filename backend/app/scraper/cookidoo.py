import re
import json
import time
import random
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.database import async_session
from app.models import Recipe, RecipeIngredient

BASE_URL = "https://cookidoo.es"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

RECIPE_ID_PATTERN = re.compile(r"/recipes/recipe/([^/]+)/r(\d+)")


def get_country_from_lang(lang):
    mapping = {
        "es-ES": "es", "es-MX": "mx", "es-AR": "ar", "es-CL": "cl",
        "de-DE": "de", "de-AT": "at", "de-CH": "ch",
        "fr-FR": "fr", "fr-BE": "be", "fr-CH": "ch",
        "it-IT": "it", "pt-PT": "pt", "nl-NL": "nl",
        "en-GB": "gb", "en-US": "us", "en-AU": "au",
        "sv-SE": "se", "da-DK": "dk", "no-NO": "no",
        "fi-FI": "fi", "pl-PL": "pl", "hu-HU": "hu",
        "cs-CZ": "cz", "sk-SK": "sk", "el-GR": "gr",
        "zh-CN": "cn", "ja-JP": "jp",
    }
    for k, v in mapping.items():
        if lang.startswith(k[:2]):
            return v
    return lang[:2]


def parse_iso_duration(duration_str: str) -> str:
    if not duration_str or not duration_str.startswith("PT"):
        return duration_str or ""
    total_minutes = 0
    current = ""
    for char in duration_str[2:]:
        if char.isdigit():
            current += char
        elif char == "H":
            total_minutes += int(current) * 60
            current = ""
        elif char == "M":
            total_minutes += int(current)
            current = ""
    if total_minutes > 0:
        return f"{total_minutes}min"
    return duration_str


HTML_FRACTIONS = {
    "&frac12;": "1/2", "&frac14;": "1/4", "&frac34;": "3/4",
    "&frac13;": "1/3", "&frac23;": "2/3", "&frac15;": "1/5",
    "&frac25;": "2/5", "&frac35;": "3/5", "&frac45;": "4/5",
    "&frac16;": "1/6", "&frac56;": "5/6", "&frac18;": "1/8",
    "&frac38;": "3/8", "&frac58;": "5/8", "&frac78;": "7/8",
}


def clean_html_fractions(text: str) -> str:
    for entity, replacement in HTML_FRACTIONS.items():
        text = text.replace(entity, replacement)
    return text


LEADING_PREPOSITIONS = re.compile(r"^(de\s+(la\s+|las\s+|los\s+)?|del\s+|en\s+|con\s+|sin\s+|al\s+)")
LEADING_NUMBER = re.compile(r"^[\d]+\s*-\s*[\d]*\s*|^-\s*[\d]+\s*")
PREP_WORDS = re.compile(
    r"^(copos|cubitos|hojas|ramitas|ramas|tallos|hebras|pipas|dientes|trozos|piezas|tiras|láminas|laminas|rodajas|rebanadas|lonchas|filetes|rallado|triturado|picado|molido|troceado|cortado|laminado|entero)\s+de\s+",
    re.IGNORECASE,
)
UNIT_WORDS = re.compile(
    r"^(cucharada|cucharadas|cucharadita|cucharaditas|pellizco|pellizcos|gramo|gramos|g|litro|litros|mililitro|mililitros|copa|copas|taza|tazas|vaso|vasos|chorrito|chorritos|ramita|ramitas|sobre|sobres)\s+de\s+",
    re.IGNORECASE,
)
TRAILING_MODIFIERS = re.compile(
    r"\s+(rallada|rallado|ralladas|rallados|tostado|tostada|tostados|tostadas|fresco|fresca|frescos|frescas|molida|molidos|molidas|triturado|triturada|triturados|trituradas|picado|picada|picados|picadas|congelado|congelada|congelados|congeladas|natural|líquido|liquido|recién\s+(molida|molido|rallada|rallado))$",
    re.IGNORECASE,
)


def clean_ingredient_name(name: str) -> str:
    name = name.strip()
    name = LEADING_PREPOSITIONS.sub("", name).strip()
    name = LEADING_NUMBER.sub("", name).strip()
    m = PREP_WORDS.match(name)
    if m:
        name = name[m.end():].strip()
    m = UNIT_WORDS.match(name)
    if m:
        name = name[m.end():].strip()
    name = TRAILING_MODIFIERS.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name


def parse_qty(qty_str: str) -> float:
    if "/" in qty_str:
        num, den = qty_str.split("/")
        return float(num) / float(den)
    return float(qty_str.replace(",", "."))


def parse_ingredient_text(text: str) -> tuple:
    text = clean_html_fractions(text.strip())
    note = ""

    paren_match = re.search(r"\(([^)]+)\)$", text)
    if paren_match:
        note = paren_match.group(1)
        text = text[:paren_match.start()].strip()

    # range: "1 - 2 cucharadas de perejil"
    range_match = re.match(r"(\d+(?:[./]\d+)?)\s*-\s*(\d+(?:[./]\d+)?)\s+([a-zA-Záéíóúüñ]+)\s+(.+)$", text)
    if range_match:
        qty = parse_qty(range_match.group(2))
        unit = range_match.group(3)
        name = clean_ingredient_name(range_match.group(4))
        return name, qty, unit, note

    simple_match = re.match(r"(\d+(?:[./]\d+)?)\s*([a-zA-Záéíóúüñ]+)\s+(.+)$", text)
    if simple_match:
        qty = parse_qty(simple_match.group(1))
        unit = simple_match.group(2)
        name = clean_ingredient_name(simple_match.group(3))
        return name, qty, unit, note

    count_match = re.match(r"(\d+(?:[./]\d+)?)\s+(.+)$", text)
    if count_match:
        qty = parse_qty(count_match.group(1))
        name = count_match.group(2).strip()
        return name, qty, "", note

    return text, None, "", note


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_recipe_page(recipe_id: str, lang: str = "es-ES") -> dict | None:
    url = f"{BASE_URL}/recipes/recipe/{lang}/r{recipe_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
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
        "country": get_country_from_lang(lang),
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

    aggregate = soup.find("script", type="application/ld+json")
    if aggregate:
        try:
            agg_data = json.loads(aggregate.string)
            if isinstance(agg_data, dict) and agg_data.get("@type") == "AggregateRating":
                result["rating"] = agg_data.get("ratingValue")
                result["review_count"] = agg_data.get("reviewCount")
        except (json.JSONDecodeError, AttributeError):
            pass

    all_scripts = soup.find_all("script", type="application/ld+json")
    for script in all_scripts:
        try:
            agg_data = json.loads(script.string)
            if isinstance(agg_data, dict) and agg_data.get("@type") == "AggregateRating":
                result["rating"] = agg_data.get("ratingValue")
                result["review_count"] = agg_data.get("reviewCount")
                break
        except (json.JSONDecodeError, AttributeError):
            continue

    return result


def fetch_discoverable_ids(max_pages: int = 5) -> set[str]:
    ids = set()
    session = requests.Session()
    session.headers.update(HEADERS)

    explore_urls = [
        f"{BASE_URL}/foundation/es-ES/explore",
        f"{BASE_URL}/search/es-ES?countries=es&languages=es&context=recipes&sortby=publishedAt",
    ]

    for url in explore_urls:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                found = RECIPE_ID_PATTERN.findall(resp.text)
                for lang, rid in found:
                    ids.add(rid)
        except requests.RequestException:
            continue
        time.sleep(random.uniform(1, 2))

    for _ in range(max_pages):
        search_url = f"{BASE_URL}/search/es-ES/fragments/stripe?limit=24&context=recipes&countries=es&languages=es&offset={len(ids)}"
        try:
            resp = session.get(search_url, timeout=15)
            if resp.status_code == 200:
                found = RECIPE_ID_PATTERN.findall(resp.text)
                if not found:
                    break
                for lang, rid in found:
                    ids.add(rid)
            else:
                break
        except requests.RequestException:
            break
        time.sleep(random.uniform(0.5, 1.5))

    collection_url = f"{BASE_URL}/search/es-ES?countries=es&context=collections&sortby=publishedAt"
    try:
        resp = session.get(collection_url, timeout=15)
        if resp.status_code == 200:
            col_ids = re.findall(r"/collection/es-ES/p/([^\s\"']+)", resp.text)
            for col_id in col_ids[:5]:
                col_url = f"{BASE_URL}/collection/es-ES/p/{col_id}"
                try:
                    col_resp = session.get(col_url, timeout=15)
                    if col_resp.status_code == 200:
                        found = RECIPE_ID_PATTERN.findall(col_resp.text)
                        for lang, rid in found:
                            ids.add(rid)
                except requests.RequestException:
                    continue
                time.sleep(random.uniform(0.5, 1))
    except requests.RequestException:
        pass

    return ids


async def save_recipe(recipe_data: dict):
    async with async_session() as session:
        from sqlalchemy import select
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


async def scrape_recipes(languages: list[str] | None = None, limit: int = 0):
    if languages is None:
        languages = ["es-ES"]

    discovered = fetch_discoverable_ids(max_pages=3)
    if not discovered:
        return 0

    ids_to_scrape = list(discovered)
    if limit > 0:
        ids_to_scrape = ids_to_scrape[:limit]

    count = 0
    for recipe_id in ids_to_scrape:
        data = fetch_recipe_page(recipe_id)
        if data:
            await save_recipe(data)
            count += 1
        time.sleep(random.uniform(1, 3))

    return count


async def scrape_single_recipe(recipe_id: str, lang: str = "es-ES"):
    data = fetch_recipe_page(recipe_id, lang)
    if data:
        await save_recipe(data)
        return True
    return False
