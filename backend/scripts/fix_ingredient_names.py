import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scraper.cookidoo import clean_ingredient_name, parse_ingredient_text  # noqa: E402

DB = Path(__file__).resolve().parent.parent / "cookidoo.db"


def clean(name: str) -> str:
    # Delegates to app.scraper.cookidoo so this script can't drift from the
    # scraper's own cleaning rules (TRAILING_MODIFIERS etc. used to be
    # duplicated here and had gone out of sync in the past).
    return clean_ingredient_name(name)


def reparse(raw_text: str) -> str:
    name, _, _, _ = parse_ingredient_text(raw_text)
    return name


def main():
    conn = sqlite3.connect(str(DB))
    cur = conn.execute("SELECT id, ingredient_name, raw_text FROM recipe_ingredients")
    rows = cur.fetchall()
    fixed = 0

    for row_id, name, raw in rows:
        # First, parse from raw_text using current logic
        parsed = reparse(raw)
        # Then apply additional cleaning (the clean function)
        cleaned = clean(parsed)
        if cleaned != name:
            conn.execute("UPDATE recipe_ingredients SET ingredient_name = ? WHERE id = ?", (cleaned, row_id))
            fixed += 1

    conn.commit()
    conn.close()
    print(f"Actualizados: {fixed} de {len(rows)} ingredientes")


if __name__ == "__main__":
    main()
