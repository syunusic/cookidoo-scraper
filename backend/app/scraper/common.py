"""Shared parsing/persistence logic for the two Cookidoo scrapers
(app/scraper/cookidoo.py — public/unauthenticated, and
app/scraper/playwright_auth.py — authenticated). Both fetch the same
recipe page HTML (just via a different HTTP client/session) and need to
save it to the DB the same way, so that logic lives here once.
"""
from typing import Optional

import json

from bs4 import BeautifulSoup

from app.database import async_session
from app.matching import tokenize
from app.models import Recipe, RecipeIngredient

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def parse_recipe_html(html_text: str, url: str, recipe_id: str, lang: str, country: str) -> Optional[dict]:
    """Parse a Cookidoo recipe page's HTML into a plain dict ready for `save_recipe`."""
    from app.scraper.cookidoo import parse_iso_duration

    soup = BeautifulSoup(html_text, "html.parser")
    all_scripts = soup.find_all("script", type="application/ld+json")
    if not all_scripts:
        return None

    data = None
    for script in all_scripts:
        try:
            parsed = json.loads(script.string)
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("name"):
            data = parsed
            break

    if not data:
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
        "country": country,
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

    for script in all_scripts:
        try:
            agg_data = json.loads(script.string)
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
        if isinstance(agg_data, dict) and agg_data.get("@type") == "AggregateRating":
            result["rating"] = agg_data.get("ratingValue")
            result["review_count"] = agg_data.get("reviewCount")
            break

    return result


async def save_recipe(recipe_data: dict):
    from app.scraper.cookidoo import parse_ingredient_text
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
            ingredient_name = name or raw_ing
            ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                raw_text=raw_ing,
                ingredient_name=ingredient_name,
                quantity=qty,
                unit=unit,
                note=note,
                search_tokens=sorted(tokenize(ingredient_name)),
            )
            session.add(ingredient)

        await session.commit()
        return recipe
