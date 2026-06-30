import re
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "cookidoo.db"

LEADING_PREPOSITIONS = re.compile(r"^(de\s+(la\s+|las\s+|los\s+)?|del\s+|en\s+|con\s+|sin\s+|al\s+)")
LEADING_NUMBER = re.compile(r"^[\d]+\s*-\s*[\d]*\s*|^-\s*[\d]+\s*")
PREP_WORDS = re.compile(
    r"^(copos|cubitos|hojas|ramitas|ramas|tallos|hebras|pipas|dientes|trozos|piezas|tiras|láminas|laminas|rodajas|rebanadas|lonchas|filetes|rallado|triturado|picado|molido|troceado|cortado|laminado|entero)\s+de\s+",
    re.IGNORECASE,
)
UNIT_WORDS = re.compile(
    r"^(cucharada|cucharadas|cucharadita|cucharaditas|pellizco|pellizcos|gramo|gramos|g|litro|litros|mililitro|mililitros|copa|copas|taza|tazas|vaso|vasos|chorrito|chorritos|ramita|ramitas|sobre|sobres)\s+de\s+",
    re.IGNORECASE,
)
TRAILING_MODIFIERS = re.compile(
    r"\s+(rallada|rallado|ralladas|rallados|tostado|tostada|tostados|tostadas|fresco|fresca|frescos|frescas|molida|molidos|molidas|triturado|triturada|triturados|trituradas|picado|picada|picados|picadas|congelado|congelada|congelados|congeladas|natural|líquido|liquido|recién\s+(molida|molido|rallada|rallado))$",
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
    name = TRAILING_MODIFIERS.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name


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
