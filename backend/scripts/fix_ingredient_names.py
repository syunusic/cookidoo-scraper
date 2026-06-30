import re
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB = Path(__file__).resolve().parent.parent / "cookidoo.db"

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
    r"\s+(rallada|rallado|ralladas|rallados|tostado|tostada|tostados|tostadas|fresco|fresca|frescos|frescas|molida|molidos|molidas|triturado|triturada|triturados|trituradas|picado|picada|picados|picadas|congelado|congelada|congelados|congeladas|desalado|desalada|desalados|desaladas|ahumado|ahumada|ahumados|ahumadas|remojado|remojada|remojados|remojadas|deshuesado|deshuesada|en\s+salazón)$",
    re.IGNORECASE,
)


def clean(name: str) -> str:
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


def reparse(raw_text: str) -> str:
    from app.scraper.cookidoo import parse_ingredient_text
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
