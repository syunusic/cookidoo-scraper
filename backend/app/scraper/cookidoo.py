import logging
import re
import time
import random
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from app.scraper.common import HEADERS, parse_recipe_html, save_recipe

logger = logging.getLogger(__name__)

BASE_URL = "https://cookidoo.es"

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
LEADING_NUMBER = re.compile(r"^[\d]+(?:/[\d]+)?\s*-\s*[\d]*(?:/[\d]*)?\s*|^-\s*[\d]+\s*")
PREP_WORDS = re.compile(
    r"^(copos|cubitos|hojas|ramitas|ramas|tallos|hebras|pipas|dientes|trozos|piezas|tiras|láminas|laminas|rodajas|rebanadas|lonchas|filetes|rallado|triturado|picado|molido|troceado|cortado|laminado|entero)\s+de\s+",
    re.IGNORECASE,
)
UNIT_WORDS = re.compile(
    r"^(cucharada|cucharadas|cucharadita|cucharaditas|pellizco|pellizcos|gramo|gramos|g|litro|litros|mililitro|mililitros|copa|copas|taza|tazas|vaso|vasos|chorrito|chorritos|ramita|ramitas|sobre|sobres|colmada|colmadas)\s+de\s+",
    re.IGNORECASE,
)
TRAILING_MODIFIERS = re.compile(
    r"\s+(rallada|rallado|ralladas|rallados|tostado|tostada|tostados|tostadas|fresco|fresca|frescos|frescas|molido|molida|molidos|molidas|moído|moída|moídas|triturado|triturada|triturados|trituradas|picado|picada|picados|picadas|congelado|congelada|congelados|congeladas|desalado|desalada|desalados|desaladas|ahumado|ahumada|ahumados|ahumadas|remojado|remojada|remojados|remojadas|deshuesado|deshuesada|en\s+salazón)$",
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
    prev = None
    while prev != name:
        prev = name
        name = TRAILING_MODIFIERS.sub("", name).strip()
        name = re.sub(r"\s+y(?:\s+\w+)?$", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name


def parse_qty(qty_str: str) -> float:
    if "/" in qty_str:
        num, den = qty_str.split("/")
        return float(num) / float(den)
    return float(qty_str.replace(",", "."))


KNOWN_UNITS = {
    "g", "kg", "mg", "ml", "l",
    "gramo", "gramos", "litro", "litros", "mililitro", "mililitros",
    "cucharada", "cucharadas", "cucharadita", "cucharaditas",
    "pellizco", "pellizcos", "sobre", "sobres",
    "copa", "copas", "taza", "tazas", "vaso", "vasos", "chorrito", "chorritos",
    "unidad", "unidades", "lata", "latas", "lata pequeña",
    "colmada", "colmadas", "rasa", "rasas",
    "rodaja", "rodajas", "loncha", "lonchas", "filete", "filetes",
    "pieza", "piezas", "tira", "tiras",
}


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
        unit = range_match.group(3).lower()
        if unit in KNOWN_UNITS:
            qty = parse_qty(range_match.group(2))
            name = clean_ingredient_name(range_match.group(4))
            return name, qty, unit, note

    # simple: "1 cucharada de aceite"
    simple_match = re.match(r"(\d+(?:[./]\d+)?)\s*([a-zA-Záéíóúüñ]+)\s+(.+)$", text)
    if simple_match:
        unit = simple_match.group(2).lower()
        if unit in KNOWN_UNITS:
            qty = parse_qty(simple_match.group(1))
            name = clean_ingredient_name(simple_match.group(3))
            return name, qty, unit, note

    # count: everything after qty is the ingredient name
    count_match = re.match(r"(\d+(?:[./]\d+)?)\s+(.+)$", text)
    if count_match:
        qty = parse_qty(count_match.group(1))
        name = count_match.group(2).strip()
        return name, qty, "", note

    return text, None, "", note


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_recipe_page(recipe_id: str, lang: str = "es-ES") -> Optional[dict]:
    url = f"{BASE_URL}/recipes/recipe/{lang}/r{recipe_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    return parse_recipe_html(resp.text, url, recipe_id, lang, get_country_from_lang(lang))


SORTBY_GROUPS = ["publishedAt", "rating", "name", "totalTime"]
LOCALE_COUNTRY_COMBOS = [("es-ES", "all"), ("es", "all"), ("es-ES", "es")]


def fetch_discoverable_ids(
    sortby_values: Optional[list[str]] = None,
    locale_country_combos: Optional[list[tuple[str, str]]] = None,
) -> set[str]:
    """Discover recipe IDs using multiple sort orders and locale/country combos.
    Cookidoo's stripe API ignores offset but different sortby and locale/country
    parameters return different subsets of the catalog (~1000 per combo).
    Combined (~12 API calls) we get ~8200 unique recipes.
    """
    if sortby_values is None:
        sortby_values = SORTBY_GROUPS
    if locale_country_combos is None:
        locale_country_combos = LOCALE_COUNTRY_COMBOS

    ids = set()
    session = requests.Session()
    session.headers.update(HEADERS)

    for locale, country in locale_country_combos:
        for sortby in sortby_values:
            url = (
                f"{BASE_URL}/search/{locale}/fragments/stripe"
                f"?limit=1000&context=recipes&countries={country}&languages={locale}"
                f"&offset=0&sortby={sortby}"
            )
            try:
                resp = session.get(url, timeout=15)
                if resp.status_code == 200:
                    found = RECIPE_ID_PATTERN.findall(resp.text)
                    prev = len(ids)
                    for lang, rid in found:
                        ids.add(rid)
                    new = len(ids) - prev
                    logger.info("  %s/%s sortby=%s: %d recipes (+%d new)", locale, country, sortby, len(found), new)
            except requests.RequestException:
                logger.warning("  %s/%s sortby=%s: FAILED", locale, country, sortby)
            time.sleep(random.uniform(0.2, 0.5))

    return sorted(ids)


async def scrape_recipes(languages: Optional[list[str]] = None, limit: int = 0):
    if languages is None:
        languages = ["es-ES"]

    discovered = fetch_discoverable_ids()
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
