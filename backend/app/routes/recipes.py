import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from thefuzz import fuzz

from app.database import get_db
from app.models import Recipe, RecipeIngredient
from app.schemas import RecipeOut, IngredientOut

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

_synonyms: dict[str, list[str]] = {}
_syn_path = Path(__file__).resolve().parent.parent / "synonyms.json"
if _syn_path.is_file():
    with open(_syn_path) as _f:
        _synonyms = json.load(_f)

STOP_WORDS = {"de", "del", "la", "el", "los", "las", "un", "una", "y", "e", "con", "al", "en", "sin", "para", "por"}


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[´'`]", "", text)
    text = re.sub(r"[^a-z0-9áéíóúüñç ]", " ", text)
    words = [w for w in text.split() if w not in STOP_WORDS]
    return " ".join(words)


def stem(word: str) -> str:
    word = word.lower().strip()
    if word.endswith("ces"):
        return word[:-3] + "z"
    if word.endswith("es") and len(word) > 3:
        return word[:-2]
    if word.endswith("s") and len(word) > 2:
        return word[:-1]
    return word


def tokenize(text: str) -> set[str]:
    words = normalize(text).split()
    stems = {stem(w) for w in words if len(w) > 1}
    stems.update(w for w in words if len(w) > 1)
    return stems


def ingredient_matches(ingredient_name: str, raw_text: str, user_tokens: set[str]) -> bool:
    combined = f"{ingredient_name} {raw_text}"
    name_tokens = tokenize(combined)

    for ut in user_tokens:
        ut_stem = stem(ut)
        for nt in name_tokens:
            nt_stem = stem(nt)
            if ut_stem == nt_stem:
                return True
            if len(ut) > 3 and (ut in nt or nt in ut):
                return True

    # fuzzy fallback: check if the user token partially matches ingredient text
    user_phrase = " ".join(sorted(user_tokens))
    ing_phrase = normalize(combined)
    if fuzz.token_set_ratio(user_phrase, ing_phrase) > 75:
        return True

    # individual fuzzy checks for longer tokens
    for ut in user_tokens:
        if len(ut) < 4:
            continue
        for nt in name_tokens:
            if len(nt) < 4:
                continue
            if fuzz.ratio(ut, nt) > 80:
                return True

    return False


def recipe_to_dict(recipe: Recipe) -> dict:
    return {
        "id": recipe.id,
        "cookidoo_id": recipe.cookidoo_id,
        "name": recipe.name,
        "url": recipe.url,
        "image_url": recipe.image_url,
        "language": recipe.language,
        "country": recipe.country,
        "total_time": recipe.total_time,
        "prep_time": recipe.prep_time,
        "cook_time": recipe.cook_time,
        "yield_amount": recipe.yield_amount,
        "difficulty": recipe.difficulty,
        "rating": recipe.rating,
        "review_count": recipe.review_count,
        "categories": recipe.categories,
        "calories": recipe.calories,
        "carbs": recipe.carbs,
        "fat": recipe.fat,
        "protein": recipe.protein,
        "fiber": recipe.fiber,
    }


# ---------------------------------------------------------------------------
# Ingredients autocomplete
# ---------------------------------------------------------------------------

@router.get("/ingredients/suggest")
async def suggest_ingredients(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(RecipeIngredient.ingredient_name, func.count(RecipeIngredient.id).label("cnt"))
        .where(RecipeIngredient.ingredient_name != "")
        .group_by(RecipeIngredient.ingredient_name)
        .order_by(func.count(RecipeIngredient.id).desc())
    )
    result = await db.execute(query)
    all_ingredients = result.all()

    # exact prefix matches first
    q_lower = q.lower().strip()
    prefix_matches = [r for r in all_ingredients if r[0].lower().startswith(q_lower)]
    fuzzy_matches = []

    if len(prefix_matches) < limit:
        seen = {r[0].lower() for r in prefix_matches}
        for r in all_ingredients:
            if r[0].lower() in seen:
                continue
            if q_lower in r[0].lower():
                fuzzy_matches.append(r)
                continue
            score = fuzz.partial_ratio(q_lower, r[0].lower())
            if score > 60:
                fuzzy_matches.append(r)

        fuzzy_matches.sort(key=lambda x: -fuzz.partial_ratio(q_lower, x[0].lower()))

    combined = prefix_matches + fuzzy_matches
    return {"suggestions": [r[0] for r in combined[:limit]]}


# ---------------------------------------------------------------------------
# Recipe search
# ---------------------------------------------------------------------------

@router.get("/search")
async def search_by_ingredients(
    q: str = Query(..., description="Comma-separated list of ingredients"),
    max_missing: int = Query(999, ge=0, le=999),
    language: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_ingredients = [i.strip().lower() for i in q.split(",") if i.strip()]

    if not user_ingredients:
        return {"results": []}

    expanded = list(user_ingredients)
    for ui in user_ingredients:
        for syn in _synonyms.get(ui, []):
            expanded.append(syn)

    user_tokens = set()
    for ui in expanded:
        user_tokens.update(tokenize(ui))

    query = select(Recipe).options(selectinload(Recipe.ingredients))
    if language:
        query = query.where(Recipe.language == language)
    if country:
        query = query.where(Recipe.country == country)

    result = await db.execute(query)
    recipes = result.scalars().all()

    scored = []
    for recipe in recipes:
        db_ingredients = recipe.ingredients

        if not db_ingredients:
            continue

        matched = 0
        missing = []
        for ingredient in db_ingredients:
            name = ingredient.ingredient_name or ""
            raw = ingredient.raw_text or ""
            if ingredient_matches(name, raw, user_tokens):
                matched += 1
            else:
                missing.append(ingredient.raw_text)

        total = len(db_ingredients)
        if total == 0:
            continue

        n_missing = len(missing)
        if n_missing > max_missing:
            continue

        match_ratio = matched / total
        if matched == 0:
            continue

        scored.append({
            "recipe": recipe_to_dict(recipe),
            "recipe_ingredients": [IngredientOut.model_validate(i) for i in db_ingredients],
            "match_score": round(matched + match_ratio, 3),
            "missing_ingredients": missing,
            "total_ingredients": total,
            "matched_ingredients": matched,
        })

    scored.sort(key=lambda x: (-x["matched_ingredients"], -x["match_score"], x["total_ingredients"]))

    return {
        "results": [
            {
                "recipe": {**r["recipe"], "ingredients": r["recipe_ingredients"]},
                "match_score": r["match_score"],
                "missing_ingredients": r["missing_ingredients"],
                "total_ingredients": r["total_ingredients"],
                "matched_ingredients": r["matched_ingredients"],
            }
            for r in scored[:limit]
        ]
    }


# ---------------------------------------------------------------------------
# Single recipe
# ---------------------------------------------------------------------------

@router.get("/{recipe_id}")
async def get_recipe(recipe_id: int, db: AsyncSession = Depends(get_db)):
    query = select(Recipe).options(selectinload(Recipe.ingredients)).where(Recipe.id == recipe_id)
    result = await db.execute(query)
    recipe = result.scalar_one_or_none()
    if not recipe:
        return {"error": "Recipe not found"}, 404
    recipe_dict = recipe_to_dict(recipe)
    recipe_dict["ingredients"] = [IngredientOut.model_validate(i) for i in recipe.ingredients]
    return recipe_dict


# ---------------------------------------------------------------------------
# List all
# ---------------------------------------------------------------------------

@router.get("/")
async def list_recipes(
    language: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Recipe).options(selectinload(Recipe.ingredients))
    if language:
        query = query.where(Recipe.language == language)
    if country:
        query = query.where(Recipe.country == country)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    recipes = result.scalars().all()

    output = []
    for recipe in recipes:
        recipe_dict = recipe_to_dict(recipe)
        recipe_dict["ingredients"] = [IngredientOut.model_validate(i) for i in recipe.ingredients]
        output.append(recipe_dict)

    return output
