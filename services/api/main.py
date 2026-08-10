import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from services.api.routes.health import router as health_router
from src.core.logging import configure_logging, set_run_id

configure_logging()

app = FastAPI(title="Personal Career Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def run_id_middleware(request: Request, call_next):
    run_id = str(uuid.uuid4())
    set_run_id(run_id)
    request.state.run_id = run_id
    response = await call_next(request)
    response.headers["X-Run-Id"] = run_id
    return response


app.include_router(health_router, prefix="/api")
