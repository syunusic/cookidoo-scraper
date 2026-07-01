# Cookidoo Recipe Finder

Scraper y buscador de recetas de [Cookidoo](https://cookidoo.es) (la plataforma oficial de recetas Thermomix®). Extrae recetas por idioma/país, las almacena en una base de datos SQLite, y permite buscar qué recetas puedes cocinar con los ingredientes que tienes.

## Funcionalidades

- **Scraper de recetas**: Descubre recetas usando múltiples combinaciones de ordenamiento/locale vía API REST, y extrae nombre, ingredientes, tiempos, dificultad, valoración, información nutricional y más con Playwright.
- **Búsqueda por ingredientes**: Ingresa los ingredientes que tienes y encuentra recetas ordenadas por las que más usan tus ingredientes.
- **Matching inteligente**: Stemmer en español + fuzzy matching con thefuzz para tolerar errores tipográficos y variaciones (huevo ≈ huevos, tomate ≈ tomates, aroz ≈ arroz).
- **Sinónimos panhispánicos**: palta ≈ aguacate, patatas ≈ papas, maíz ≈ choclo ≈ elote, etc.
- **Autocompletado**: Mientras escribes, sugiere ingredientes existentes en la base de datos.
- **Filtro por categoría**: Una vez obtenidos los resultados, filtra por tipo de plato.
- **Login autenticado**: Scrapea con tus credenciales de Cookidoo para acceder al explorador completo de recetas.
- **CLI y WebApp**: Usa el scraper desde terminal y la interfaz web para buscar recetas.

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Backend API | Python + FastAPI |
| Base de datos | SQLite + SQLAlchemy (async) |
| Scraper público | requests + BeautifulSoup4 |
| Scraper autenticado | Playwright (headless Chromium) |
| CLI | Click |
| Frontend | React + Vite + Tailwind CSS |
| Fuzzy matching | thefuzz + python-Levenshtein |

## Estructura del proyecto

```
cookidoo-scraper/
├── backend/
│   ├── app/
│   │   ├── __init__.py            # Versión de la app (single source of truth)
│   │   ├── main.py                # Servidor FastAPI (puerto 8000)
│   │   ├── database.py            # Conexión SQLite asíncrona
│   │   ├── models.py              # Modelos SQLAlchemy (Recipe, RecipeIngredient)
│   │   ├── schemas.py             # Esquemas Pydantic para la API
│   │   ├── synonyms.json          # Mapa de sinónimos panhispánicos
│   │   ├── routes/
│   │   │   └── recipes.py         # Endpoints REST (/api/recipes/*)
│   │   └── scraper/
│   │       ├── cli.py             # Interfaz de línea de comandos
│   │       ├── cookidoo.py        # Scraper público (sin login)
│   │       └── playwright_auth.py # Scraper con login (Playwright)
│   ├── scripts/
│   │   └── fix_ingredient_names.py  # Migración: normaliza nombres viejos
│   ├── cookidoo.db                # Base de datos SQLite
│   ├── dist/                      # Frontend build (generado)
│   ├── requirements.txt
│   └── deploy/
│       └── cookidoo-api.service   # Systemd service
├── frontend/
│   ├── public/
│   │   ├── og-image.jpg           # Preview para redes sociales
│   │   └── favicon.png
│   ├── src/
│   │   ├── App.jsx                # Componente principal
│   │   ├── api.js                 # Cliente HTTP para la API
│   │   ├── index.css              # Estilos Tailwind
│   │   ├── main.jsx               # Punto de entrada React
│   │   └── components/
│   │       ├── IngredientSearch.jsx  # Formulario con autocompletado
│   │       ├── RecipeList.jsx        # Resultados con filtro por categoría
│   │       └── RecipeDetail.jsx      # Detalle de receta
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   └── postcss.config.js
├── bump-version.sh                 # Script: bump versión + rebuild frontend + restart service
└── README.md
```

## Instalación

### Prerrequisitos

- Python 3.9+
- Node.js 22+ (para el frontend)

### Backend

```bash
git clone <repo>
cd cookidoo-scraper

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r backend/requirements.txt

# Opcional: Playwright para scraper autenticado
pip install playwright
python -m playwright install chromium
```

### Frontend

```bash
cd frontend
npm install
```

## Cómo usar

### Desarrollo (con Vite dev server)

**Terminal 1 — Backend:**
```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Abre http://localhost:5173

### Producción (backend sirve frontend)

```bash
cd frontend
npm run build
cp -r dist/* ../backend/dist/
# o service systemd:
sudo systemctl restart cookidoo-api
```

### Scrapear recetas

#### Sin login (público)
```bash
source .venv/bin/activate
cd backend
python -m app.scraper.cli scrape --languages es-ES --limit 50
```

#### Con login de Cookidoo (recomendado)
```bash
source .venv/bin/activate
cd backend
python -m app.scraper.cli login            # guarda cookies
python -m app.scraper.cli login-and-scrape --limit 200
```

## API endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health` | Health check + versión + conteo de recetas |
| GET | `/api/recipes/search?q=...` | Buscar recetas por ingredientes |
| GET | `/api/recipes/` | Listar todas las recetas |
| GET | `/api/recipes/{id}` | Detalle de receta con ingredientes |
| GET | `/api/recipes/ingredients/suggest?q=...` | Autocompletado de ingredientes |

### Parámetros de búsqueda

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `q` | string | (requerido) | Ingredientes separados por coma |
| `language` | string | — | Filtrar por idioma (ej. `es-ES`) |
| `country` | string | — | Filtrar por país (ej. `es`) |
| `limit` | int | 20 | Máximo resultados |
| `max_missing` | int | — | Máx. ingredientes faltantes permitidos |
| `max_total` | int | — | Máx. ingredientes totales en la receta |

## Algoritmo de matching

1. **Tokeniza** ingredientes del usuario y de la receta, eliminando stop words
2. **Aplica stemming** en español: plurales, terminaciones
3. **Compara tokens** por stem exacto y substring
4. **Fuzzy fallback** con thefuzz para errores tipográficos
5. **Expansión de sinónimos** desde `synonyms.json`
6. **Ordena** por: más ingredientes del usuario aprovechados → mayor cobertura → receta más simple

## Normalización de ingredientes

El scraper limpia los nombres de ingredientes automáticamente:

- Elimina preposiciones iniciales: `de ajo` → `ajo`
- Elimina palabras de preparación: `copos de avena` → `avena`, `cubitos de hielo` → `hielo`
- Elimina unidades capturadas como nombre: `colmada de harina` → `harina`
- Elimina modificadores finales: `perejil fresco` → `perejil`, `pimienta molida` → `pimienta`
- Multi-pasada para casos complejos: `bacalao en salazón remojado y desalado` → `bacalao`

## Sinónimos

Los sinónimos panhispánicos se definen en `backend/app/synonyms.json`. Al buscar un ingrediente, se expande automáticamente con sus equivalentes regionales.

Ejemplos incluidos: palta/aguacate, patatas/papas, maíz/choclo/elote, judías/porotos/frijoles, etc.

## Licencia

Uso personal y educativo. Cookidoo® y Thermomix® son marcas registradas de Vorwerk. Este proyecto no está afiliado ni respaldado por Vorwerk.
