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
- Add more synonym pairs to synonyms.json as users report gaps.
- Consider exposing suggest endpoint to also return synonyms.
- Improve photo recognition: better image preprocessing, multi-candidate support, confidence scores.

## Critical Context
- Database: **7656 recipes** (after full cleanup), 35671+ ingredient records.
- Backend runs via systemd (`sudo systemctl restart cookidoo-api`) on port 8000.
- Frontend rebuild: `npm run build` in frontend/, then `rm -rf ../backend/dist && cp -r dist ../backend/dist`.
- Python venv: `/datos/logstash/etc/diccionarios/scripts/venv_daryl/bin/activate`.
- Domain: cookidoo.termica.biz.
- Stripe API caveats: offset is ignored, max 1000 results per sortby+locale combo.
- Known issue: search iterates all ~7656 recipes (no DB-level pre-filtering), can be slow with many ingredients.
- TRAILING_MODIFIERS regex must be kept in sync between `cookidoo.py` and `scripts/fix_ingredient_names.py`.

## Relevant Files
- `backend/app/__init__.py`: version string (single source of truth).
- `backend/app/main.py`: FastAPI entry point, mounts static files, health endpoint with version + recipe_count.
- `backend/app/routes/recipes.py`: search, suggest, detail endpoints + synonym loading + ingredient matching (no raw_text).
- `backend/app/scraper/cookidoo.py`: `fetch_discoverable_ids` with multi-sort+multi-locale, `parse_ingredient_text`, `clean_ingredient_name` pipeline, `TRAILING_MODIFIERS` regex.
- `backend/app/scraper/playwright_auth.py`: auth login, `discover_recipe_ids` (fallback), `scrape_all` now uses requests-based discovery.
- `backend/app/synonyms.json`: pan-Hispanic ingredient synonym map (includes carne molida/picada/res/vaca).
- `backend/app/vision.py`: MobileNetV2 image classification + ImageNet → ingredient mapping.
- `backend/app/google_vision.py`: Google Cloud Vision REST API integration (label detection + object localization + web detection + OCR), uses `GOOGLE_VISION_API_KEY` env var.
- `backend/scripts/fix_ingredient_names.py`: migration script to re-parse and clean existing DB records.
- `frontend/src/App.jsx`: lifted ingredient state, recipe count display, version display.
- `frontend/src/components/IngredientSearch.jsx`: autocomplete, max_missing + max_total filter controls, camera button for photo recognition.
- `frontend/src/api.js`: API client with maxTotal option and `recognizeIngredients`.
- `frontend/public/og-image.jpg`: OG preview image (1200×630, orange gradient).
- `bump-version.sh`: script to bump version, rebuild frontend, redeploy.
- `backend/cookidoo.db`: SQLite database (not in git).

## Reflection
2026-06-30: Comprehensive language cleanup done. 7656 Spanish recipes remain after removing 740 non-Spanish recipes (Turkish, Romanian, Czech, Portuguese, French, English, German, Danish, Vietnamese, Indonesian, Filipino, Polish, Dutch, Hungarian, Icelandic). The multi-pass approach worked: first character-based (non-Spanish glyphs like ě, ğ, ș, ø, etc.), then word-pattern-based for languages that share characters with Spanish (English, French, German using only ASCII + Spanish accents). Photo recognition feature implemented: `POST /api/recipes/ingredients/recognize` endpoint uses MobileNetV2 (ImageNet) for object classification (frutas/verduras) + Tesseract OCR fallback for text on packages. If visual confidence > 70%, only visual result is returned (ignoring background OCR noise). Otherwise, OCR + low-confidence visual are combined.
