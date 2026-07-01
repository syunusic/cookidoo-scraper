from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routes.recipes import router as recipes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Pre-warm vision model in a thread (download weights on startup, not on first request)
    import asyncio
    from app.vision import _get_model
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _get_model)
    yield


app = FastAPI(title="Cookidoo Recipe Finder", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
