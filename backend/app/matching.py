"""Spanish-language ingredient tokenization and fuzzy matching.

Shared between the search endpoint (app/routes/recipes.py) and the scraper
(app/scraper/*).
"""
import re

from thefuzz import fuzz

STOP_WORDS = {"de", "del", "la", "el", "los", "las", "un", "una", "y", "e", "con", "al", "en", "sin", "para", "por"}


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[´'`]", "", text)
    text = re.sub(r"[^a-z0-9áéíóúüñç ]", " ", text)
    words = [w for w in text.split() if w not in STOP_WORDS]
    return " ".join(words)


def stem(word: str) -> str:
    word = word.lower().strip()
    if word.endswith("ces"):
        return word[:-3] + "z"
    if word.endswith("es") and len(word) > 3:
        return word[:-2]
    if word.endswith("s") and len(word) > 2:
        return word[:-1]
    return word


def phrase_words(text: str) -> list[str]:
    """Significant words of a phrase, in order, stop words removed."""
    return [w for w in normalize(text).split() if len(w) > 1]


def tokenize(text: str) -> set[str]:
    words = phrase_words(text)
    stems = {stem(w) for w in words}
    stems.update(words)
    return stems


def _word_matches(word: str, name_tokens: set[str]) -> bool:
    """Does this single word appear in name_tokens — exactly, by stem, as a
    substring (for words long enough that a substring match is meaningful),
    or as a typo (fuzzy ratio) of one of them?"""
    w_stem = stem(word)
    for nt in name_tokens:
        nt_stem = stem(nt)
        if w_stem == nt_stem:
            return True
        if min(len(word), len(nt)) > 3 and (word in nt or nt in word):
            return True
    if len(word) >= 4:
        for nt in name_tokens:
            if len(nt) >= 4 and fuzz.ratio(word, nt) > 80:
                return True
    return False


def phrase_matches(phrase: str, name_tokens: set[str], name_phrase: str) -> bool:
    """Does the ingredient name match this single query phrase (one typed
    ingredient, or one synonym variant of it)?

    Requires ALL of the phrase's significant words to be present in the
    name — not just any single one — otherwise a two-word query like "carne
    molida" (ground beef) would match "carne de res" (cubed beef) just
    because they share the word "carne", even though "molida" (the word that
    actually distinguishes ground meat) matches nothing.

    This is intentionally strict with no partial-word tolerance, even for
    longer phrases: a synonym like "carne molida de res" (3 significant
    words: carne, molida, res) must NOT match plain "carne de res" on 2 of 3
    words (missing exactly "molida", the one that matters) — that was a real
    bug caught while testing this. It doesn't lose legitimate matches in the
    other direction: if a recipe's ingredient is the longer "carne molida de
    res" and the user searches the shorter "carne molida", that already
    matches fine since all of the (shorter) query's words are present in the
    (longer) name — extra words in the NAME are never a problem, only extra
    required words in the QUERY phrase would be.

    Deliberately does NOT fall back to a whole-phrase fuzzy ratio (like
    fuzz.token_set_ratio(phrase, name_phrase)) for multi-word phrases: a
    single shared word (e.g. "carne") skews that score high even when the
    rest of the phrase clearly doesn't match, reintroducing the same
    false-positive this function exists to avoid. For a single-word phrase
    there's no coverage to protect, and token_set_ratio is more tolerant of
    accent/typo differences than the per-word fuzz.ratio in _word_matches
    (e.g. "camarón" vs "camarones"), so it's still used in that case.
    """
    words = phrase_words(phrase)
    if not words:
        return False

    if all(_word_matches(w, name_tokens) for w in words):
        return True

    if len(words) == 1 and fuzz.token_set_ratio(words[0], name_phrase) > 75:
        return True

    return False


def ingredient_matches(ingredient_name: str, query: str) -> bool:
    """Does ingredient_name match a single query phrase (e.g. what the user
    typed for one ingredient, or one synonym variant of it)?"""
    return phrase_matches(query, tokenize(ingredient_name), normalize(ingredient_name))
