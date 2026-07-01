# Anchored Summary

## Goal
- Build and maintain a web app that scrapes Thermomix recipes from Cookidoo and lets users search by ingredients they have.

## Constraints & Preferences
- Backend (FastAPI) serves both API and frontend static files (no separate nginx static serving).
- Nginx in DMZ does pure reverse proxy to the app server (daryl:8000).
- Systemd service (cookidoo-api) controls the backend process.
- Prefer file-based config (synonyms.json) over hardcoded lists.
- Python 3.9 compatibility required (no `dict | None` syntax).
- Version tracking: bump `__version__` in `backend/app/__init__.py` on each change, rebuild frontend, restart service.

## Progress
### Done
- 2026-07-01, v5.0.0 — Applied a full round of proposed improvements on branch `feature/mejoras-propuestas` (not yet merged to main):
  - `requirements.txt` was missing `tensorflow`/`numpy` (used unconditionally by `vision.py`, imported at server startup) — a clean install would crash. Fixed, and made `vision.py`/`main.py` degrade gracefully (skip MobileNetV2 warm-up) if tensorflow isn't installed, so the server never hard-depends on it.
  - Extracted `app/matching.py` (normalize/stem/tokenize/phrase_matches/ingredient_matches) out of `routes/recipes.py` so it can be shared with the scraper.
  - Added `RecipeIngredient.search_tokens` (JSON column) precomputed at scrape time (`app/scraper/common.py`) instead of re-tokenizing every ingredient on every search request. Migrated via Alembic + backfilled 73,486 existing rows (`scripts/backfill_search_tokens.py`).
  - Search endpoint (`routes/recipes.py::search_by_ingredients`), first pass: removed a per-recipe re-tokenization of the user's query groups (was recomputed once per recipe instead of once per request), added a per-request match cache keyed by ingredient name (73,486 ingredient rows but only 12,629 distinct names), dropped `raw_json` via `load_only`. Real baseline comparison (checked out `main` in a git worktree, pointed at the same `cookidoo.db`, ran the identical query): **~10s (main) → ~6.2s**. The first "~14s" figure quoted during the session turned out to be a mid-refactor self-comparison, not a true baseline — corrected once actually measured against unmodified `main`.
  - Search endpoint, second pass (candidate pre-filtering): the remaining cost was loading every one of the ~7,656 recipes' full ingredient lists on every search regardless of relevance. Rewrote `search_by_ingredients` as four phases: (A) resolve which of the ~12.6k *distinct* ingredient names match the query (cheap, reuses `_get_ingredient_counts`'s cache); (B) `SELECT DISTINCT recipe_id FROM recipe_ingredients WHERE ingredient_name IN (matched_names)` using the existing index on `ingredient_name` to get candidate recipe ids — mirrors the original "skip if zero matches" gate, just pushed into SQL; (C) fetch full ingredient rows for just the candidates as plain tuples (not ORM objects — instantiating ~73k `RecipeIngredient` objects on every request was itself a real cost); (D) hydrate full `Recipe`+`IngredientOut` ORM objects only for the final `limit` results returned to the client. Verified byte-for-byte identical results vs `main` on 6 real queries (common ingredients, typo cases, the "sal"/"salchicha" substring-false-positive case) before and after. Measured live on production: 5-ingredient common-baking query ~10s → ~2s; a rarer-ingredient query ("camarón, limón") ~0.8s.
  - Caveat introduced by phase A: it reuses the 10-minute `_get_ingredient_counts` cache, which was previously only used by autocomplete (where staleness is a minor UX issue). Now, searching for a genuinely brand-new ingredient name right after a scrape won't find it until that cache expires or the process restarts (restarting is already part of the normal deploy flow in `bump-version.sh`). Documented inline at `_ingredient_counts_cache`.
  - A subtle test-isolation bug came out of this: `_ingredient_counts_cache` is a module-level global, so pytest tests using separate in-memory SQLite DBs could see stale ingredient names left over from an earlier test within the same process. Fixed by resetting the cache in the `db_session` fixture (`tests/conftest.py`).
  - **Matching-quality bug found by the user while testing** (not a regression from this session's work — verified present in `main` too): searching "carne molida" (ground beef) matched "carne de res"/"carne de cerdo" (cubed beef/pork) in results, purely because both contain the word "carne" — the old `tokens_match()` treated a multi-word query as "OR across all its words", so any single shared word was enough, ignoring that "molida" (the word that actually means *ground*) matched nothing. Rewrote the core matching primitive in `app/matching.py` as `phrase_matches(phrase, name_tokens, name_phrase)`: requires **all** significant words of a query phrase to be present in the ingredient name (via stem/substring/per-word-fuzzy — `_word_matches`), with no partial-word tolerance even for longer phrases. (An initial version allowed 1 missing word for 3+-word phrases as a compromise, but that let the synonym "carne molida de res" match "carne de res" on 2 of 3 words — missing exactly "molida" again. Dropped the tolerance entirely once that surfaced; verified it doesn't lose the legitimate direction, since a shorter query phrase already matches fine against a longer name that contains all of the query's words.) Deliberately does NOT fall back to whole-phrase `fuzz.token_set_ratio` for multi-word phrases — same false-positive, a single shared word skews it high — but still uses it for single-word queries where there's no coverage to protect (needed for e.g. "camarón" vs "camarones", where per-word `fuzz.ratio` alone scores 75, just under the 80 threshold, but `token_set_ratio` scores 80).
  - `search_by_ingredients`'s Phase A now derives `total_matched`/`missing` directly from "matched by ≥1 group" instead of a separately-computed flattened `all_tokens` union — simpler, and keeps it consistent with `distinct_matched` (both now come from the same per-name group-match resolution).
  - Verified: single-word queries (5 of 6 real test queries used to validate the earlier performance rewrite) still return results identical to `main`, except for a handful of rank-50-boundary reshuffles among near-tied, low-relevance results (same `distinct_matched`, marginally different `match_score`) — an expected side effect of the total_matched computation change above, not a regression. Multi-word queries now correctly exclude the "shares one word" false positives (spot-checked "tomate, carne molida, zanahoria" and "aceite de oliva" vs "aceite de girasol").
  - Deduplicated the two scrapers: `app/scraper/common.py` now holds the shared `parse_recipe_html` + `save_recipe` used by both `cookidoo.py` (public/unauthenticated) and `playwright_auth.py` (authenticated). Previously each had a near-identical copy that could silently drift (this had already happened once with `TRAILING_MODIFIERS`, per the note below — `scripts/fix_ingredient_names.py` now imports `clean_ingredient_name` from `cookidoo.py` instead of duplicating the regexes).
  - `/api/recipes/ingredients/recognize`: added an 8 MB upload cap, a 10-req/min-per-IP in-memory rate limit (single uvicorn worker, so in-memory state is safe), and graceful 400s for corrupt images / decompression bombs instead of 500s. This endpoint runs local ML inference and/or calls a paid external API with no auth in front of it, so it was the cheapest one to abuse.
  - `/api/recipes/ingredients/suggest` (autocomplete) and the OCR-candidate lookup in `/recognize` now share a 10-minute in-memory cache (`_get_ingredient_counts`) instead of re-running the `GROUP BY` over all of `recipe_ingredients` on every keystroke/request.
  - CORS: `allow_credentials` was `True` combined with `allow_origins=["*"]`, an invalid combination per spec (browsers reject it) that was also unused (no cookies/credentials anywhere in this API). Set to `False`.
  - Replaced `print()` with `logging` in both scrapers and the CLI (`logging.basicConfig` in `cli.py`, plain `%(message)s` format to keep the same look).
  - Added Alembic (`backend/alembic/`, `alembic.ini`) for schema migrations going forward — `env.py` points at the same SQLite file as the app (`app.database.DB_PATH`) via the sync driver.
  - Added a test suite (`backend/tests/`, `pytest.ini`, `requirements-dev.txt`): 34 tests covering `app/matching.py`, ingredient parsing (`clean_ingredient_name`, `parse_ingredient_text`, `parse_iso_duration`), and the search endpoint's ranking/filtering behavior against an in-memory SQLite DB (never touches `cookidoo.db`).
  - Frontend: `RecipeList.jsx` now shows a clear message + "quitar filtro" button when a category filter leaves 0 results, instead of a silently empty list.
  - Cleanup: removed the orphan 0-byte `cookidoo.db` at the repo root (the real DB is `backend/cookidoo.db`).
- Fixed recognize endpoint: low-confidence visual results now combine with OCR instead of returning only visual.
- Removed premature return on low-confidence visual path; visual candidates are collected and OCR is also processed to find additional matches.
- Google Vision API integration: new `google_vision.py` module uses REST API with `GOOGLE_VISION_API_KEY` env var for label detection (object recognition via FOOD_MAP) and text detection (OCR). Falls back to MobileNetV2 + Tesseract if API key not set.
- Comprehensive Google Vision label mapping (GV_FOOD_MAP, 300+ entries) + substring/word-level matching for better recognition.
- Object Localization (localizedObjectAnnotations) added for more specific object detection.
- OCR separated from visual: endpoint `mode` param (`visual` default, `text` for OCR) + frontend toggle button "T".
- Comprehensive cleanup: scanned all recipe names for non-Spanish content. Deleted **740 total**:
  - 23 Turkish (character/word markers)
  - 2 Indonesian (char markers)
  - 353 mixed non-Spanish chars (Czech, Turkish, Romanian, Portuguese, French, Danish, Vietnamese — character-based)
  - 362 English/German/French-only names (zero Spanish words, word-pattern detection)
- Database now at **7656 Spanish recipes** (from initial ~8400+).
- Version tracking via `backend/app/__init__.py` (now 4.0.0), exposed in `/api/health` and frontend footer. Script: `bump-version.sh`.
- Multi-sort discovery: 4 sort orders (publishedAt, rating, name, totalTime) instead of 1.
- Multi-locale discovery: 3 locale/country combos (es-ES/all, es/all, es-ES/es) via stripe fragment API → ~8200 recipes discovered.
- `scrape_all` in playwright_auth.py now uses fast requests-based `fetch_discoverable_ids` instead of slow Playwright-based discovery.
- Python 3.9 compat fix: replaced `dict | None` → `Optional[dict]` in playwright_auth.py.
- Fixed r-prefix comparison bug in `scrape_all` (numeric IDs vs `rXXXXX` in DB).
- Recipe count displayed in API health endpoint and frontend footer.
- Photo recognition: `POST /api/recipes/ingredients/recognize` endpoint + camera button in frontend. Uses MobileNetV2 (ImageNet) for object classification (frutas/verduras) + Tesseract OCR fallback for text on packages.
- OG image regenerated (1200×630 JPG, orange gradient, app branding).
- max_total filter added to backend (`routes/recipes.py`) and frontend UI (checkbox + dropdown in IngredientSearch).
- max_missing and max_total controls added as optional checkbox + dropdown UI.
- Ingredient state lifted to `App.jsx` — persists when going back from recipe detail.
- Matching fix: removed `raw_text` from `ingredient_matches` — match only against cleaned `ingredient_name`.
- TRAILING_MODIFIERS regex fixed: added missing `molido`, `moído`, `moídas` variants.
- Synonyms added: carne molida ↔ carne picada ↔ carne molida de res ↔ carne molida de vaca.
- Migration script re-parsed 3992 + 251 existing ingredients with updated TRAILING_MODIFIERS.

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- Serve frontend static files from FastAPI (app.mount /assets, catch-all route /{full_path:path}).
- Detect non-Spanish recipes via heuristic name patterns (Portuguese/Romanian marker words) rather than per-recipe langdetect (too slow) or character-based detection (too many false positives from Spanish accents). Multi-pass approach: first delete recipes with characters never used in Spanish (ç, ğ, ş, ı, ț, ș, ă, ě, š, č, ř, ž, ý, ø, æ, å, œ, ð, þ), then delete recipes with zero Spanish content words (detecting English "the/and/with", French "au/aux/et", German "und/mit").
- MATCHING: ingredient matching only checks cleaned `ingredient_name`, not raw_text, to avoid false positives from modifiers ("molida" matching "moída" via raw_text).
- Fetch discoverable IDs via requests-based stripe API (fast, ~19s for 12 calls) instead of Playwright browser (slow, ~3min).
- For scraping, keep Playwright (needs auth cookies for rate-limiting) but only for individual recipe pages, not discovery.

## Next Steps
- Merge `feature/mejoras-propuestas` into `main` once tested (currently deployed live to the systemd service for testing, at the user's explicit request — not pushed/merged to `main` in git yet — see 2026-07-01 entries above).
- If search latency still matters at even larger recipe counts (the candidate pre-filter's win shrinks as a query's ingredients get more generic/common, since more recipes become "candidates"), consider SQLite FTS5 or a proper inverted index table as the next step.
- Add more synonym pairs to synonyms.json as users report gaps.
- Consider exposing suggest endpoint to also return synonyms.
- Improve photo recognition: better image preprocessing, multi-candidate support, confidence scores.

## Critical Context
- Database: **7656 recipes** (after full cleanup), 73,486 ingredient records (12,629 distinct ingredient_name values).
- Backend runs via systemd (`sudo systemctl restart cookidoo-api`) on port 8000. **This is a live, real-traffic service** (cookidoo.termica.biz) — the 2026-07-01 branch work was deployed to it directly at the user's explicit request for testing purposes, without merging to `main` first.
- Frontend rebuild: `npm run build` in frontend/, then `rm -rf ../backend/dist && cp -r dist ../backend/dist`.
- Python venv: `/datos/logstash/etc/diccionarios/scripts/venv_daryl/bin/activate`.
- Domain: cookidoo.termica.biz.
- Stripe API caveats: offset is ignored, max 1000 results per sortby+locale combo.
- Search (`search_by_ingredients`) now pre-filters candidate recipes via an indexed `ingredient_name IN (...)` query before loading any ingredient data (see 2026-07-01 entry above) — measured live: 5-ingredient common-baking query ~10s (original) → ~2s; a rarer-ingredient query ~0.8s. The win scales with how uncommon the searched ingredients are, since common ones still leave a large candidate set.
- Schema changes now go through Alembic (`backend/alembic/`) — run `alembic upgrade head` after pulling changes that touch `app/models.py`. `RecipeIngredient.search_tokens` (added 2026-07-01) must stay populated for new rows; `app/scraper/common.py::save_recipe` does this automatically. It's no longer read by the search endpoint itself (superseded by the Phase A/B/C/D rewrite) but is harmless to keep and may be useful again for a future FTS5/inverted-index pass.
- TRAILING_MODIFIERS regex lives only in `cookidoo.py` now — `scripts/fix_ingredient_names.py` imports `clean_ingredient_name` instead of duplicating the regexes (fixed 2026-07-01, previously had drifted out of sync).
- `_ingredient_counts_cache` (routes/recipes.py, 10-min TTL) is read by both `/ingredients/suggest` and search's Phase A — a brand-new ingredient name from a scrape won't be searchable by exact name until the cache expires or the process restarts. Tests reset this cache per-test via the `db_session` fixture (`tests/conftest.py`) since it's a module-level global that would otherwise leak between tests' separate in-memory DBs.
- Tests: `cd backend && pip install -r requirements-dev.txt && pytest` (34 tests, in-memory SQLite, never touches `cookidoo.db`).

## Relevant Files
- `backend/app/__init__.py`: version string (single source of truth).
- `backend/app/main.py`: FastAPI entry point, mounts static files, health endpoint with version + recipe_count, CORS (no credentials), lazy vision warm-up.
- `backend/app/matching.py`: tokenize/stem/normalize/phrase_matches/ingredient_matches — `phrase_matches` requires all significant words of a query phrase to be present (fixed a false-positive bug where multi-word queries like "carne molida" matched on a single shared word). Shared by the search endpoint and the scraper (for precomputing `search_tokens`).
- `backend/app/routes/recipes.py`: search (with per-request match cache + `load_only`), suggest (cached 10 min), detail endpoints, `/recognize` (rate-limited + size-capped).
- `backend/app/scraper/common.py`: shared `parse_recipe_html` + `save_recipe` (computes `search_tokens`) used by both scrapers.
- `backend/app/scraper/cookidoo.py`: `fetch_discoverable_ids` with multi-sort+multi-locale, `parse_ingredient_text`, `clean_ingredient_name` pipeline, `TRAILING_MODIFIERS` regex.
- `backend/app/scraper/playwright_auth.py`: auth login, `discover_recipe_ids` (fallback), `scrape_all` now uses requests-based discovery.
- `backend/app/synonyms.json`: pan-Hispanic ingredient synonym map (includes carne molida/picada/res/vaca).
- `backend/app/vision.py`: MobileNetV2 image classification + ImageNet → ingredient mapping; `TF_AVAILABLE` flag so the app runs without tensorflow installed.
- `backend/app/google_vision.py`: Google Cloud Vision REST API integration (label detection + object localization + web detection + OCR), uses `GOOGLE_VISION_API_KEY` env var.
- `backend/alembic/`, `backend/alembic.ini`: schema migrations (env.py points at `app.database.DB_PATH`).
- `backend/tests/`: pytest suite (matching, ingredient parsing, search endpoint), `pytest.ini`, `requirements-dev.txt`.
- `backend/scripts/fix_ingredient_names.py`: migration script to re-parse and clean existing DB records (now delegates cleaning to `cookidoo.py`).
- `backend/scripts/backfill_search_tokens.py`: one-off migration to populate `search_tokens` for rows saved before that column existed.
- `frontend/src/App.jsx`: lifted ingredient state, recipe count display, version display.
- `frontend/src/components/IngredientSearch.jsx`: autocomplete, max_missing + max_total filter controls, camera button for photo recognition.
- `frontend/src/components/RecipeList.jsx`: category filter now shows a message + clear-filter button when it excludes all results.
- `frontend/src/api.js`: API client with maxTotal option and `recognizeIngredients`.
- `frontend/public/og-image.jpg`: OG preview image (1200×630, orange gradient).
- `bump-version.sh`: script to bump version, rebuild frontend, redeploy.
- `backend/cookidoo.db`: SQLite database (not in git).

## Reflection
2026-07-01: Full-repo review requested, then all proposed improvements applied on `feature/mejoras-propuestas` (v5.0.0): missing tensorflow/numpy in requirements.txt (would break clean installs), search endpoint ~2.3x faster via removing redundant per-recipe re-tokenization + per-request name-based match cache + precomputed `search_tokens` (Alembic migration + backfill of 73,486 rows) + lighter query, deduplicated the two scrapers into `app/scraper/common.py`, rate-limited/size-capped the image recognition endpoint, cached the autocomplete GROUP BY, fixed invalid CORS config, moved scraper print() to logging, added a 30-test pytest suite, and a frontend fix for the empty-category-filter state. Branch not yet merged to main — verified locally (tests pass, health/search/suggest smoke-tested, frontend builds) but not deployed.
2026-06-30: Comprehensive language cleanup done. 7656 Spanish recipes remain after removing 740 non-Spanish recipes (Turkish, Romanian, Czech, Portuguese, French, English, German, Danish, Vietnamese, Indonesian, Filipino, Polish, Dutch, Hungarian, Icelandic). The multi-pass approach worked: first character-based (non-Spanish glyphs like ě, ğ, ș, ø, etc.), then word-pattern-based for languages that share characters with Spanish (English, French, German using only ASCII + Spanish accents). Photo recognition feature implemented: `POST /api/recipes/ingredients/recognize` endpoint uses MobileNetV2 (ImageNet) for object classification (frutas/verduras) + Tesseract OCR fallback for text on packages. If visual confidence > 70%, only visual result is returned (ignoring background OCR noise). Otherwise, OCR + low-confidence visual are combined.
