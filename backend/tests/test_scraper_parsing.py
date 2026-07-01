from app.scraper.cookidoo import (
    clean_ingredient_name,
    get_country_from_lang,
    parse_ingredient_text,
    parse_iso_duration,
    parse_qty,
)


class TestCleanIngredientName:
    def test_removes_leading_preposition(self):
        assert clean_ingredient_name("de ajo") == "ajo"

    def test_removes_preparation_words(self):
        assert clean_ingredient_name("copos de avena") == "avena"
        assert clean_ingredient_name("cubitos de hielo") == "hielo"

    def test_removes_unit_captured_as_name(self):
        assert clean_ingredient_name("colmada de harina") == "harina"

    def test_removes_trailing_modifiers(self):
        assert clean_ingredient_name("perejil fresco") == "perejil"
        assert clean_ingredient_name("pimienta molida") == "pimienta"

    def test_multi_pass_for_compound_modifiers(self):
        assert clean_ingredient_name("bacalao en salazón remojado y desalado") == "bacalao"


class TestParseIngredientText:
    def test_simple_quantity_and_unit(self):
        name, qty, unit, note = parse_ingredient_text("1 cucharada de aceite")
        assert name == "aceite"
        assert qty == 1.0
        assert unit == "cucharada"

    def test_range_quantity(self):
        name, qty, unit, note = parse_ingredient_text("1 - 2 cucharadas de perejil")
        assert name == "perejil"
        assert qty == 2.0
        assert unit == "cucharadas"

    def test_count_only_no_unit(self):
        name, qty, unit, note = parse_ingredient_text("2 huevos")
        assert name == "huevos"
        assert qty == 2.0
        assert unit == ""

    def test_parenthetical_note_extracted(self):
        name, qty, unit, note = parse_ingredient_text("100 g de queso (opcional)")
        assert note == "opcional"
        assert name == "queso"


def test_parse_qty_fraction():
    assert parse_qty("1/2") == 0.5


def test_parse_qty_decimal_comma():
    assert parse_qty("1,5") == 1.5


def test_parse_iso_duration_minutes():
    assert parse_iso_duration("PT30M") == "30min"


def test_parse_iso_duration_hours_and_minutes():
    assert parse_iso_duration("PT1H15M") == "75min"


def test_parse_iso_duration_empty():
    assert parse_iso_duration("") == ""


def test_get_country_from_lang():
    assert get_country_from_lang("es-ES") == "es"
    assert get_country_from_lang("de-DE") == "de"
    assert get_country_from_lang("xx-YY") == "xx"
