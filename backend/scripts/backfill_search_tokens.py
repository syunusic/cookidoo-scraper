"""One-off migration: populate RecipeIngredient.search_tokens for rows saved
before that column existed (see alembic/versions/*_add_search_tokens_*.py).

New rows get search_tokens set at save time (app/scraper/common.py), so this
only needs to run once against an existing database.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.matching import tokenize  # noqa: E402

DB = Path(__file__).resolve().parent.parent / "cookidoo.db"


def main():
    conn = sqlite3.connect(str(DB))
    cur = conn.execute(
        "SELECT id, ingredient_name FROM recipe_ingredients WHERE search_tokens IS NULL"
    )
    rows = cur.fetchall()

    for row_id, name in rows:
        tokens = sorted(tokenize(name or ""))
        conn.execute(
            "UPDATE recipe_ingredients SET search_tokens = ? WHERE id = ?",
            (json.dumps(tokens), row_id),
        )

    conn.commit()
    conn.close()
    print(f"Backfilled search_tokens for {len(rows)} ingredients")


if __name__ == "__main__":
    main()
