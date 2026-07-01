import io
import json
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import pytesseract
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from sqlalchemy import select, func
from sqlalchemy.orm import load_only, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from thefuzz import fuzz

from app.database import get_db
from app.matching import STOP_WORDS, normalize, phrase_matches, tokenize
from app.models import Recipe, RecipeIngredient
from app.schemas import RecipeOut, IngredientOut

router = APIRouter(prefix="/api/recipes", tags=["recipes"])

_synonyms: dict[str, list[str]] = {}
_syn_path = Path(__file__).resolve().parent.parent / "synonyms.json"
if _syn_path.is_file():
    with open(_syn_path) as _f:
        _synonyms = json.load(_f)

# Packaging/non-ingredient words commonly read by OCR that should be excluded
NON_INGREDIENT_WORDS = {
    "reciclable", "calorias", "calorías", "grasas", "saturadas", "sodio",
    "neto", "cont", "neto", "envase", "envases", "producto", "ingredientes",
    "informacion", "información", "nutricional", "porcion", "porción",
    "conservacion", "conservación", "caducidad", "lote", "fecha",
    "consumir", "preferentemente", "peso", "neto", "escurrido",
    "fabricado", "distribuido", "importado", "exportado", "content",
    "net", "ingredients", "nutrition", "serving", "contains", "may",
    "soprole", "untable", "belatina", "southwes", "alberto",
    "rullons", "canta", "enca", "portalo", "comerc", "banpogo",
    "u415662", "cinta", "enmasca",
}


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

# The distinct-ingredient-names-by-frequency list only changes when new
# recipes are scraped (a separate offline CLI process, see app/scraper/cli.py)
# — not on every request — so cache it instead of re-running the GROUP BY
# over the whole recipe_ingredients table on every keystroke. Also used by
# search_by_ingredients() (Phase A) to resolve query matches, so: after a
# scrape that introduces a genuinely new ingredient name, searching for that
# exact new name won't find it until this cache expires (or the process
# restarts — which the normal deploy flow in bump-version.sh already does).
_ingredient_counts_cache: dict = {"data": None, "ts": 0.0}
INGREDIENT_COUNTS_TTL = 600  # seconds


async def _get_ingredient_counts(db: AsyncSession):
    now = time.monotonic()
    if _ingredient_counts_cache["data"] is not None and now - _ingredient_counts_cache["ts"] < INGREDIENT_COUNTS_TTL:
        return _ingredient_counts_cache["data"]

    query = (
        select(RecipeIngredient.ingredient_name, func.count(RecipeIngredient.id).label("cnt"))
        .where(RecipeIngredient.ingredient_name != "")
        .group_by(RecipeIngredient.ingredient_name)
        .order_by(func.count(RecipeIngredient.id).desc())
    )
    result = await db.execute(query)
    all_ingredients = result.all()
    _ingredient_counts_cache["data"] = all_ingredients
    _ingredient_counts_cache["ts"] = now
    return all_ingredients


@router.get("/ingredients/suggest")
async def suggest_ingredients(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    all_ingredients = await _get_ingredient_counts(db)

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
# Photo recognition
# ---------------------------------------------------------------------------

import asyncio


def _ocr_image(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img) or img
    # upscale small images for better OCR
    w, h = img.size
    if w < 800 or h < 600:
        scale = max(800 / w, 600 / h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img = img.convert("L")
    img = img.filter(ImageFilter.SHARPEN)
    img = ImageOps.autocontrast(img, cutoff=5)
    # binarize
    img = img.point(lambda x: 0 if x < 128 else 255)
    text = pytesseract.image_to_string(img, lang="spa+eng", config="--psm 6 --oem 3")
    return text


def _extract_candidates(text: str) -> list[str]:
    candidates = set()
    for line in text.splitlines():
        line = line.strip().lower()
        if not line or len(line) < 3:
            continue
        parts = re.split(r"[,;/|()]+", line)
        for part in parts:
            part = part.strip()
            part = re.sub(r"[^a-záéíóúüñ0-9 ]", " ", part)
            part = re.sub(r"\s+", " ", part).strip()
            if len(part) > 1:
                candidates.add(part)
        # Only keep single words that are >= 4 chars AND look Spanish-like
        for word in re.findall(r"[a-záéíóúüñ]+", line):
            if len(word) > 3:
                candidates.add(word)
    return list(candidates)


def _classify_image(image_bytes: bytes):
    from app.vision import classify_image
    return classify_image(image_bytes)


# Recognition runs CPU-heavy local inference (MobileNetV2) and/or calls a paid
# external API (Google Vision) with no authentication in front of it, so it's
# the cheapest endpoint in this app to abuse. Guard it with a simple in-memory
# per-IP rate limit and an upload size cap — this process runs as a single
# uvicorn worker (see deploy/cookidoo-api.service), so in-memory state is safe.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB
RECOGNIZE_RATE_LIMIT = 10  # requests
RECOGNIZE_RATE_WINDOW = 60  # seconds
_recognize_calls: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(client_ip: str):
    now = time.monotonic()
    calls = _recognize_calls[client_ip]
    while calls and now - calls[0] > RECOGNIZE_RATE_WINDOW:
        calls.popleft()
    if len(calls) >= RECOGNIZE_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Demasiadas fotos enviadas, espera un momento e intenta de nuevo")
    calls.append(now)


@router.post("/ingredients/recognize")
async def recognize_ingredients(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query("visual", pattern="^(visual|text)$"),
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if not contents:
        return {"ingredients": []}
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Imagen demasiado grande (máx. 8 MB)")

    from app.google_vision import is_available as gv_available, detect_all as gv_detect_all
    loop = asyncio.get_event_loop()

    try:
        # Step 1: Always try MobileNetV2 first (free, local, fast)
        visual_results = await loop.run_in_executor(None, _classify_image, contents)

        # Step 2: OCR in text mode — try Google Vision OCR if available, else Tesseract
        raw_text = None
        if mode == "text":
            if gv_available():
                _, raw_text = await loop.run_in_executor(None, gv_detect_all, contents, True)
            else:
                raw_text = await loop.run_in_executor(None, _ocr_image, contents)

        # Step 3: If MobileNetV2 found nothing and Google Vision is available, use it for visual too
        if not visual_results and gv_available():
            gv_visual, _ = await loop.run_in_executor(None, gv_detect_all, contents, False)
            if gv_visual:
                visual_results = gv_visual
    except (UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="No se pudo procesar la imagen")

    matched = []
    seen_match = set()

    # 1. High-confidence visual → return immediately
    best_visual = max(visual_results, key=lambda x: x[1]) if visual_results else ("", 0)
    if best_visual[1] >= 0.7:
        return {"ingredients": [best_visual[0]]}

    # 2. Low-confidence visual → include visual candidates
    if visual_results:
        for ing, score in visual_results:
            if ing.lower() not in seen_match:
                seen_match.add(ing.lower())
                matched.append(ing)

    # 3. OCR only in text mode — strict prefix matching only (no fuzzy)
    if mode == "text" and raw_text:
        candidates = _extract_candidates(raw_text)
        # No word expansion; only use the extracted text as-is

        counts = await _get_ingredient_counts(db)
        all_ingredients = [(r[0].lower(), r[0]) for r in counts if r[0]]

        # Build a prefix lookup for fast matching
        # Map first 4 chars → list of ingredients starting with those chars
        prefix_map = {}
        for lower, orig in all_ingredients:
            key = lower[:4]
            prefix_map.setdefault(key, []).append((lower, orig))

        for cand in sorted(candidates, key=len, reverse=True):
            cand = cand.strip().lower()
            if not cand or len(cand) < 3 or cand in seen_match:
                continue
            cand_words = set(cand.split())
            if cand_words.issubset(NON_INGREDIENT_WORDS | STOP_WORDS):
                continue

            # Check candidates against DB ingredients — prefix only
            matched_ing = None
            prefix_key = cand[:4]
            for lower, orig in prefix_map.get(prefix_key, []):
                if lower.startswith(cand) or cand.startswith(lower):
                    if matched_ing is None or len(orig) < len(matched_ing):
                        matched_ing = orig

            if matched_ing and matched_ing.lower() not in seen_match:
                seen_match.add(matched_ing.lower())
                matched.append(matched_ing)

    return {"ingredients": matched[:10]}


# ---------------------------------------------------------------------------
# Recipe search
# ---------------------------------------------------------------------------

@router.get("/search")
async def search_by_ingredients(
    q: str = Query(..., description="Comma-separated list of ingredients"),
    max_missing: int = Query(999, ge=0, le=999),
    max_total: Optional[int] = Query(None, ge=1, le=100),
    language: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    user_ingredients = [i.strip().lower() for i in q.split(",") if i.strip()]

    if not user_ingredients:
        return {"results": []}

    # Expand synonyms — each group is a list of alternative phrases for one
    # user-typed ingredient (e.g. ["carne molida", "carne picada", ...]).
    expanded_groups = []
    for ui in user_ingredients:
        group = [ui]
        for syn in _synonyms.get(ui, []):
            group.append(syn)
        expanded_groups.append(group)

    # Phase A: resolve which DISTINCT ingredient names match the query. There
    # are far fewer distinct names (~12.6k) than ingredient rows (~73k, cached
    # via _get_ingredient_counts), so this fuzzy-matching pass is cheap even
    # though it's not indexable. It lets us push "does this recipe even have
    # a chance of matching" down into SQL (Phase B) via the indexed
    # ingredient_name column, instead of loading every recipe's full
    # ingredient list just to discard the ones with zero overlap.
    #
    # A name matches a group if it matches ANY phrase in that group (the
    # phrase itself or one of its synonyms) — checked via phrase_matches,
    # which requires (nearly) all of a phrase's words to be present, not
    # just one shared word. total_matched/missing derive from "matched by at
    # least one group", so they stay consistent with distinct_matched instead
    # of being computed against a separately flattened, cross-ingredient
    # token union (which is what let "carne molida" match "carne de res" —
    # both merely contain the word "carne").
    distinct_names = await _get_ingredient_counts(db)

    name_match_groups: dict[str, frozenset] = {}
    for name, _cnt in distinct_names:
        name_tokens = tokenize(name)
        name_phrase = normalize(name)
        groups = frozenset(
            gi for gi, group in enumerate(expanded_groups)
            if any(phrase_matches(phrase, name_tokens, name_phrase) for phrase in group)
        )
        if groups:
            name_match_groups[name] = groups

    name_match_all = set(name_match_groups)
    if not name_match_all:
        return {"results": []}

    # Phase B: candidate recipe ids — only those with >=1 ingredient whose
    # name is in name_match_all (mirrors the original "if total_matched == 0:
    # continue" gate, evaluated in SQL instead of after loading everything).
    candidate_query = (
        select(RecipeIngredient.recipe_id)
        .where(RecipeIngredient.ingredient_name.in_(name_match_all))
        .distinct()
    )
    if language or country:
        candidate_query = candidate_query.join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
        if language:
            candidate_query = candidate_query.where(Recipe.language == language)
        if country:
            candidate_query = candidate_query.where(Recipe.country == country)

    candidate_ids = {row[0] for row in (await db.execute(candidate_query)).all()}
    if not candidate_ids:
        return {"results": []}

    # Phase C: full ingredient lists for just the candidates, as plain rows
    # (not ORM entities) — scoring doesn't need mapped objects, and building
    # ~73k of those on every request regardless of relevance was the largest
    # remaining cost after the per-name match cache.
    ing_rows = (await db.execute(
        select(RecipeIngredient.recipe_id, RecipeIngredient.ingredient_name, RecipeIngredient.raw_text)
        .where(RecipeIngredient.recipe_id.in_(candidate_ids))
        .order_by(RecipeIngredient.id)
    )).all()

    by_recipe: dict[int, list] = defaultdict(list)
    for recipe_id, ingredient_name, raw_text in ing_rows:
        by_recipe[recipe_id].append((ingredient_name or "", raw_text))

    scored = []
    for recipe_id, rows in by_recipe.items():
        total = len(rows)
        total_matched = 0
        missing = []
        group_matched = [False] * len(expanded_groups)

        for name, raw_text in rows:
            if name in name_match_all:
                total_matched += 1
            else:
                missing.append(raw_text)
            for gi in name_match_groups.get(name, ()):
                group_matched[gi] = True

        if total_matched == 0:
            continue

        n_missing = len(missing)
        if n_missing > max_missing:
            continue
        if max_total is not None and total > max_total:
            continue

        distinct_matched = sum(group_matched)
        match_ratio = total_matched / total

        scored.append({
            "recipe_id": recipe_id,
            "match_score": round(distinct_matched + match_ratio, 3),
            "missing_ingredients": missing,
            "total_ingredients": total,
            "matched_ingredients": total_matched,
            "distinct_matched": distinct_matched,
        })

    scored.sort(key=lambda x: (-x["distinct_matched"], -x["matched_ingredients"], x["total_ingredients"]))
    top = scored[:limit]

    # Phase D: hydrate full Recipe + Ingredient objects only for the winners
    # actually returned to the client, instead of for every candidate.
    top_ids = [s["recipe_id"] for s in top]
    recipes_by_id = {}
    if top_ids:
        result = await db.execute(
            select(Recipe)
            .options(
                load_only(
                    Recipe.id, Recipe.cookidoo_id, Recipe.name, Recipe.url, Recipe.image_url,
                    Recipe.language, Recipe.country, Recipe.total_time, Recipe.prep_time,
                    Recipe.cook_time, Recipe.yield_amount, Recipe.difficulty, Recipe.rating,
                    Recipe.review_count, Recipe.categories, Recipe.calories, Recipe.carbs,
                    Recipe.fat, Recipe.protein, Recipe.fiber,
                ),
                selectinload(Recipe.ingredients),
            )
            .where(Recipe.id.in_(top_ids))
        )
        recipes_by_id = {r.id: r for r in result.scalars().all()}

    return {
        "results": [
            {
                "recipe": {
                    **recipe_to_dict(recipes_by_id[s["recipe_id"]]),
                    "ingredients": [
                        IngredientOut.model_validate(i) for i in recipes_by_id[s["recipe_id"]].ingredients
                    ],
                },
                "match_score": s["match_score"],
                "missing_ingredients": s["missing_ingredients"],
                "total_ingredients": s["total_ingredients"],
                "matched_ingredients": s["matched_ingredients"],
                "distinct_matched": s["distinct_matched"],
            }
            for s in top
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
