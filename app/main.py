import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import Base, engine
from app.rate_limit import limiter
from app.routers.jobs import router as jobs_router


def _openapi_servers() -> list[dict[str, str]]:
    servers: list[dict[str, str]] = []
    pub = (settings.public_base_url or "").strip()
    if pub:
        servers.append(
            {
                "url": pub.rstrip("/"),
                "description": "Configured public API host (API_PUBLIC_BASE_URL)",
            }
        )
    servers.append({"url": "/", "description": "Current origin (e.g. http://localhost:8000)"})
    return servers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Async Document Processing API",
    description="Submit documents for asynchronous processing; poll job status or receive webhooks.",
    version="1.0.0",
    lifespan=lifespan,
    servers=_openapi_servers(),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
