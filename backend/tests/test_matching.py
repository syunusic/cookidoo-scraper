from app.matching import ingredient_matches, normalize, stem, tokenize


def test_normalize_strips_stop_words_and_accents_case():
    assert normalize("Huevos, Leche y Harina") == "huevos leche harina"


def test_normalize_removes_punctuation():
    assert normalize("aceite de oliva (virgen extra)") == "aceite oliva virgen extra"


def test_stem_handles_plurals():
    assert stem("huevos") == "huevo"
    # This stemmer is intentionally crude (chop trailing -s/-es/-ces): it
    # doesn't produce the linguistically "correct" singular, so "tomates"
    # and "tomate" land on different stems. Exact-stem matching alone won't
    # bridge that, but ingredient_matches() still does via its substring
    # fallback (see TestIngredientMatches below).
    assert stem("tomates") == "tomat"
    assert stem("nueces") == "nuez"  # -ces -> -z


def test_stem_leaves_short_words_alone():
    assert stem("sal") == "sal"
    assert stem("es") == "es"


def test_tokenize_includes_both_raw_and_stemmed_forms():
    tokens = tokenize("huevos frescos")
    assert "huevo" in tokens
    assert "huevos" in tokens
    assert "fresco" in tokens


class TestIngredientMatches:
    def test_exact_stem_match_singular_plural(self):
        assert ingredient_matches("huevo", "huevos")
        assert ingredient_matches("tomates", "tomate")

    def test_typo_tolerance_via_fuzzy_fallback(self):
        # "aroz" is a one-letter-missing typo for "arroz"
        assert ingredient_matches("arroz", "aroz")

    def test_unrelated_ingredient_does_not_match(self):
        assert not ingredient_matches("pollo", "chocolate")

    def test_short_word_does_not_falsely_match_as_substring(self):
        # Regression: "sal" (salt) must not match "salchicha" (sausage) just
        # because it's a text substring of it.
        assert not ingredient_matches("salchicha", "sal")

    def test_substring_match_for_longer_words(self):
        # "camarón" ingredient should match a user query of "camarones"
        assert ingredient_matches("camarón", "camarones")

    def test_multiword_query_requires_all_significant_words(self):
        # Regression: "carne molida" (ground beef) must NOT match "carne de
        # res" (cubed beef) just because they share the word "carne" — the
        # word that actually distinguishes ground meat ("molida") has to be
        # present too.
        assert not ingredient_matches("carne de res", "carne molida")
        assert not ingredient_matches("carne de cerdo", "carne molida")
        assert ingredient_matches("carne molida", "carne molida")
        assert ingredient_matches("carne molida de res", "carne molida")

    def test_multiword_query_matches_full_phrase(self):
        assert ingredient_matches("aceite de oliva virgen extra", "aceite de oliva")
        assert not ingredient_matches("aceite de girasol", "aceite de oliva")
