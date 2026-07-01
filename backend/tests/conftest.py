import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models import Recipe, RecipeIngredient
from app.matching import tokenize


@pytest.fixture
async def db_session():
    """An isolated in-memory SQLite DB per test — never touches cookidoo.db."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # routes.recipes._get_ingredient_counts caches the distinct-ingredient-name
    # list for 10 minutes across requests — long enough that, within a single
    # pytest process, a later test's fresh in-memory DB would otherwise see
    # ingredient names left over from an earlier test's DB. Reset it per test.
    import app.routes.recipes as recipes_module
    recipes_module._ingredient_counts_cache["data"] = None
    recipes_module._ingredient_counts_cache["ts"] = 0.0

    async with session_maker() as session:
        yield session

    await engine.dispose()


async def add_recipe(session, name, ingredient_names, **kwargs):
    defaults = {"language": "es-ES", "country": "es"}
    defaults.update(kwargs)
    recipe = Recipe(
        cookidoo_id=f"r{name}",
        name=name,
        url=f"https://cookidoo.es/recipes/recipe/es-ES/r{name}",
        **defaults,
    )
    session.add(recipe)
    await session.flush()

    for ing_name in ingredient_names:
        session.add(RecipeIngredient(
            recipe_id=recipe.id,
            raw_text=ing_name,
            ingredient_name=ing_name,
            search_tokens=sorted(tokenize(ing_name)),
        ))
    await session.commit()
    return recipe
