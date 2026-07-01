import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routes.recipes import router as recipes_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Pre-warm vision model in a thread (download weights on startup, not on first request).
    # Optional dependency: the app must still start if tensorflow isn't installed.
    from app.vision import TF_AVAILABLE, _get_model
    if TF_AVAILABLE:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _get_model)
    else:
        logger.warning("Skipping MobileNetV2 warm-up — tensorflow not available")
    yield


app = FastAPI(title="Cookidoo Recipe Finder", lifespan=lifespan)

# This API is public and stateless (no cookies/auth), so it's served to any
# origin. allow_credentials must stay False: browsers reject the
# allow_origins=["*"] + allow_credentials=True combination outright, and
# nothing here relies on cookies/credentialed requests anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recipes_router)


@app.get("/api/health")
async def health():
    from app import __version__
    from app.database import async_session
    from sqlalchemy import select, func
    from app.models import Recipe
    async with async_session() as session:
        count = await session.scalar(select(func.count(Recipe.id)))
    return {"status": "ok", "version": __version__, "recipe_count": count}


dist = Path(__file__).resolve().parent.parent / "dist"
if dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")
    index_path = dist / "index.html"

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(index_path))
