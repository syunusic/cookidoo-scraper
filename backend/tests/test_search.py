from app.routes.recipes import search_by_ingredients
from tests.conftest import add_recipe


async def test_search_ranks_by_distinct_ingredients_then_coverage(db_session):
    await add_recipe(db_session, "tortilla", ["huevo", "patata", "cebolla", "sal", "aceite"])
    await add_recipe(db_session, "flan", ["huevo", "leche", "azucar"])
    await add_recipe(db_session, "ensalada", ["lechuga", "tomate"])

    result = await search_by_ingredients(
        q="huevo,leche", max_missing=999, max_total=None,
        language=None, country=None, limit=20, db=db_session,
    )

    names = [r["recipe"]["name"] for r in result["results"]]
    assert "flan" in names
    assert "ensalada" not in names  # no overlap at all
    assert names[0] == "flan"  # matches both distinct user ingredients


async def test_search_respects_max_missing(db_session):
    await add_recipe(db_session, "tortilla", ["huevo", "patata", "cebolla", "sal", "aceite"])

    result = await search_by_ingredients(
        q="huevo", max_missing=1, max_total=None,
        language=None, country=None, limit=20, db=db_session,
    )
    assert result["results"] == []  # 4 missing ingredients > max_missing=1

    result = await search_by_ingredients(
        q="huevo", max_missing=999, max_total=None,
        language=None, country=None, limit=20, db=db_session,
    )
    assert len(result["results"]) == 1


async def test_search_respects_max_total(db_session):
    await add_recipe(db_session, "tortilla", ["huevo", "patata", "cebolla", "sal", "aceite"])

    result = await search_by_ingredients(
        q="huevo", max_missing=999, max_total=3,
        language=None, country=None, limit=20, db=db_session,
    )
    assert result["results"] == []  # recipe has 5 ingredients > max_total=3


async def test_search_empty_query_returns_no_results(db_session):
    result = await search_by_ingredients(
        q="", max_missing=999, max_total=None,
        language=None, country=None, limit=20, db=db_session,
    )
    assert result["results"] == []


async def test_search_repeated_ingredient_names_match_consistently(db_session):
    # Regression guard for the per-request match cache keyed by ingredient
    # name: recipes sharing an identical ingredient_name string must still
    # each be evaluated correctly, not just the first one seen.
    await add_recipe(db_session, "receta1", ["sal", "huevo"])
    await add_recipe(db_session, "receta2", ["sal", "harina"])

    result = await search_by_ingredients(
        q="huevo", max_missing=999, max_total=None,
        language=None, country=None, limit=20, db=db_session,
    )
    names = [r["recipe"]["name"] for r in result["results"]]
    assert names == ["receta1"]


async def test_search_filters_by_language_and_country(db_session):
    # Regression guard for the candidate-recipe SQL query (Phase B in
    # search_by_ingredients), which joins RecipeIngredient -> Recipe only
    # when language/country filters are given.
    await add_recipe(db_session, "tortilla_es", ["huevo", "patata"], language="es-ES", country="es")
    await add_recipe(db_session, "tortilla_mx", ["huevo", "patata"], language="es-MX", country="mx")

    result = await search_by_ingredients(
        q="huevo", max_missing=999, max_total=None,
        language="es-MX", country=None, limit=20, db=db_session,
    )
    names = [r["recipe"]["name"] for r in result["results"]]
    assert names == ["tortilla_mx"]

    result = await search_by_ingredients(
        q="huevo", max_missing=999, max_total=None,
        language=None, country="es", limit=20, db=db_session,
    )
    names = [r["recipe"]["name"] for r in result["results"]]
    assert names == ["tortilla_es"]


async def test_search_candidate_filter_excludes_zero_overlap_recipes(db_session):
    # A recipe with no ingredient in common with the query must never appear,
    # regardless of how the candidate pre-filter (Phase B) is implemented.
    await add_recipe(db_session, "con_pollo", ["pollo", "arroz"])
    await add_recipe(db_session, "sin_relacion", ["chocolate", "vainilla"])

    result = await search_by_ingredients(
        q="pollo", max_missing=999, max_total=None,
        language=None, country=None, limit=20, db=db_session,
    )
    names = [r["recipe"]["name"] for r in result["results"]]
    assert names == ["con_pollo"]
