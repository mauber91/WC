from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from world_cup_api.api.routes import router
from world_cup_api.config import get_settings
from world_cup_api.db import Base, SessionLocal, engine
from world_cup_api.jobs.tournament_jobs import start_tournament_jobs, stop_tournament_jobs
from world_cup_api.services.seed import seed_database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)
    start_tournament_jobs(run_immediately=True)
    yield
    stop_tournament_jobs()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
