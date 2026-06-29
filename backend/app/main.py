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
    return {"status": "ok"}


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
