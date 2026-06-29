# Cookidoo Recipe Finder

Scraper y buscador de recetas de [Cookidoo](https://cookidoo.es) (la plataforma oficial de recetas Thermomix®). Extrae recetas por idioma/país, las almacena en una base de datos SQLite, y permite buscar qué recetas puedes cocinar con los ingredientes que tienes en tu refrigerador.

## Funcionalidades

- **Scraper de recetas**: Navega Cookidoo y extrae nombre, ingredientes, tiempos, dificultad, valoración, información nutricional y más.
- **Búsqueda por ingredientes**: Ingresa los ingredientes que tienes y encuentra recetas que puedas preparar con ellos (o comprando pocas cosas más).
- **Matching inteligente**: Stemmer en español que entiende variaciones (huevo ≈ huevos, tomate ≈ tomates, arroz ≈ arroces).
- **Sistema de scoring**: Ordena resultados por porcentaje de ingredientes cubiertos y cantidad de ingredientes faltantes.
- **Login autenticado**: Scrapea con tus credenciales de Cookidoo para descubrir cientos de recetas (el explorador de recetas requiere sesión).
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

## Estructura del proyecto

```
scrapper_cookidoo/
├── backend/
│   ├── app/
│   │   ├── main.py                # Servidor FastAPI (puerto 8000)
│   │   ├── database.py            # Conexión SQLite asíncrona
│   │   ├── models.py              # Modelos SQLAlchemy (Recipe, RecipeIngredient)
│   │   ├── schemas.py             # Esquemas Pydantic para la API
│   │   ├── routes/
│   │   │   └── recipes.py         # Endpoints REST (/api/recipes)
│   │   └── scraper/
│   │       ├── cli.py             # Interfaz de línea de comandos
│   │       ├── cookidoo.py        # Scraper público (sin login)
│   │       └── playwright_auth.py # Scraper con login (Playwright)
│   ├── cookidoo.db                # Base de datos SQLite
│   ├── requirements.txt
│   └── run.sh                     # Script para arrancar el backend
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Componente principal
│   │   ├── api.js                 # Cliente HTTP para la API
│   │   ├── index.css              # Estilos Tailwind
│   │   ├── main.jsx               # Punto de entrada React
│   │   └── components/
│   │       ├── IngredientSearch.jsx  # Formulario de búsqueda
│   │       ├── RecipeList.jsx        # Lista de resultados
│   │       └── RecipeDetail.jsx      # Detalle de receta
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   ├── tailwind.config.js
│   └── postcss.config.js
├── .venv/                          # Entorno virtual Python
└── README.md
```

## Instalación

### Prerrequisitos

- Python 3.11+
- Node.js 22+ (para el frontend)

### Backend

```bash
# Clonar y entrar al proyecto
cd scrapper_cookidoo

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r backend/requirements.txt

# Opcional: instalar Playwright para scraper autenticado
pip install playwright
python -m playwright install chromium
```

### Frontend

```bash
cd frontend
npm install
```

## Cómo usar

### 1. Arrancar el backend

```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Arrancar el frontend

En otra terminal:

```bash
cd frontend
npm run dev
```

Abre http://localhost:5173 en tu navegador.

### 3. Scrapear recetas

#### Sin login (público)

Scrapea recetas desde páginas públicas (limitado a las que aparecen en portada):

```bash
source .venv/bin/activate
cd backend

# Scrapea recetas en español
python -m app.scraper.cli scrape --languages es-ES --limit 50

# Scrapea en múltiples idiomas
python -m app.scraper.cli scrape --languages es-ES,es-MX,fr-FR --limit 100

# Scrapea una receta específica por ID
python -m app.scraper.cli recipe 370592
```

#### Con login de Cookidoo (recomendado)

Con sesión iniciada puedes acceder al explorador de recetas completo:

```bash
source .venv/bin/activate
cd backend

# Paso 1: Iniciar sesión (guarda cookies)
python -m app.scraper.cli login
# Te pedirá email y contraseña

# Paso 2: Scrapear descubriendo recetas del explorador
python -m app.scraper.cli login-and-scrape --limit 200

# O todo en uno:
python -m app.scraper.cli login-and-scrape --email tu@email.com --limit 500
```

### 4. Buscar recetas por ingredientes

Desde la web: http://localhost:5173

O directamente por API:

```bash
# Buscar recetas con huevo, lechuga y tomate (máx 3 ingredientes faltantes)
curl 'http://localhost:8000/api/recipes/search?q=huevo,lechuga,tomate&max_missing=3'

# Buscar con más tolerancia
curl 'http://localhost:8000/api/recipes/search?q=pollo,arroz,ajo,cebolla&max_missing=5'

# Filtrar por idioma y país
curl 'http://localhost:8000/api/recipes/search?q=harina,huevo,leche&language=es-ES&country=es'
```

### 5. API endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/recipes/search?q=...&max_missing=...` | Buscar recetas por ingredientes |
| GET | `/api/recipes/` | Listar todas las recetas |
| GET | `/api/recipes/{id}` | Obtener detalle de una receta |
| GET | `/api/health` | Health check |

#### Parámetros de búsqueda

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `q` | string | (requerido) | Ingredientes separados por coma |
| `max_missing` | int | 3 | Máx ingredientes faltantes permitidos (0-10) |
| `language` | string | — | Filtrar por idioma (ej. `es-ES`) |
| `country` | string | — | Filtrar por país (ej. `es`, `mx`) |
| `limit` | int | 20 | Máximo resultados (1-100) |

## Modelo de datos

### Recipe

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | Integer | ID autoincremental |
| `cookidoo_id` | String | ID único de Cookidoo (ej. `r370592`) |
| `name` | String | Nombre de la receta |
| `url` | String | URL en Cookidoo |
| `image_url` | String | URL de la imagen |
| `language` | String | Código de idioma (ej. `es-ES`) |
| `country` | String | Código de país (ej. `es`) |
| `total_time` | String | Tiempo total (ej. `30min`) |
| `prep_time` | String | Tiempo de preparación |
| `cook_time` | String | Tiempo de cocción |
| `yield_amount` | String | Porciones (ej. `8 vasos`) |
| `difficulty` | String | Dificultad (`fácil`, `media`, `difícil`) |
| `rating` | Float | Valoración media (0-5) |
| `review_count` | Integer | Número de valoraciones |
| `categories` | JSON | Array de categorías |
| `calories` | String | Calorías por porción |
| `carbs` | String | Carbohidratos |
| `fat` | String | Grasas |
| `protein` | String | Proteínas |
| `fiber` | String | Fibra |
| `raw_json` | JSON | JSON-LD original de Cookidoo |

### RecipeIngredient

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | Integer | ID autoincremental |
| `recipe_id` | Integer | FK a Recipe |
| `raw_text` | String | Texto original (ej. `150 g de harina`) |
| `ingredient_name` | String | Nombre normalizado (ej. `harina`) |
| `quantity` | Float | Cantidad numérica |
| `unit` | String | Unidad (g, ml, cucharadita, etc.) |
| `note` | String | Nota opcional entre paréntesis |

## Algoritmo de matching

El buscador implementa un sistema de matching que:

1. **Tokeniza** los ingredientes del usuario y los de la receta, eliminando stop words (de, del, la, el, con, etc.)
2. **Aplica stemming** en español: elimina plurales (`huevos` → `huevo`, `tomates` → `tomate`) y otras terminaciones (`ces` → `z`)
3. **Compara tokens** por igualdad exacta del stem y por substring cuando el token es largo (>3 caracteres)
4. **Calcula score**: `match_ratio * (1 / (1 + missing * 0.5))`, dando prioridad a recetas con alta cobertura y pocos faltantes

Esto permite que "huevo" matchee con "huevos" y "aceite de oliva" matchee con "aceite".

## Cómo contribuir / mejoras posibles

- **Más idiomas**: El scraper soporta múltiples idiomas (`es-ES`, `fr-FR`, `de-DE`, `it-IT`, etc.). Las URLs de Cookidoo varían por país.
- **Instrucciones**: Con login, se podría extraer también el paso a paso de cada receta.
- **App iOS**: El frontend React se puede empaquetar con Capacitor/Cordova para generar una app nativa.
- **Búsqueda por categoría**: Actualmente las categorías se almacenan en JSON pero no se exponen como filtro en la UI.
- **Sugerencias semanales**: Usar el planificador de Cookidoo para sugerir recetas para la semana.
- **Exportar lista de compras**: Generar lista de ingredientes faltantes para cada receta.

## Licencia

Uso personal y educativo. Cookidoo® y Thermomix® son marcas registradas de Vorwerk. Este proyecto no está afiliado ni respaldado por Vorwerk. Respeta los términos de uso de Cookidoo.
