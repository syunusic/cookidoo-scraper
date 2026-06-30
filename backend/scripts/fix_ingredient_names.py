import re
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "cookidoo.db"
LEADING_PREPOSITIONS = re.compile(r"^(de\s+(la\s+|las\s+|los\s+)?|del\s+|en\s+|con\s+|sin\s+|al\s+)")


def clean(name: str) -> str:
    name = name.strip()
    name = LEADING_PREPOSITIONS.sub("", name).strip()
    return re.sub(r"\s+", " ", name)


def main():
    conn = sqlite3.connect(str(DB))
    cur = conn.execute("SELECT id, ingredient_name FROM recipe_ingredients")
    rows = cur.fetchall()
    fixed = 0

    for row_id, name in rows:
        cleaned = clean(name)
        if cleaned != name:
            conn.execute("UPDATE recipe_ingredients SET ingredient_name = ? WHERE id = ?", (cleaned, row_id))
            fixed += 1

    conn.commit()
    conn.close()
    print(f"Actualizados: {fixed} de {len(rows)} ingredientes")


if __name__ == "__main__":
    main()
