import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.api.routes.brain import router as brain_router
from services.api.routes.content import router as content_router
from services.api.routes.health import router as health_router
from services.api.routes.memory import router as memory_router
from services.api.routes.research import router as research_router
from src.brain.service import BrainError
from src.content.service import ContentError
from src.core.logging import configure_logging, run_context
from src.llm.embeddings import MockEmbedder
from src.llm.mock import MockLLM
from src.memory.service import ContentMemoryError
from src.research.service import ResearchError

configure_logging()

app = FastAPI(title="Personal Career Engine API")
app.state.llm_client = MockLLM()
app.state.embedder = MockEmbedder()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def run_id_middleware(request: Request, call_next):
    run_id = str(uuid.uuid4())
    request.state.run_id = run_id
    # A request has a well-defined scope to wrap, so run_context (not
    # set_run_id) keeps this request's run_id from leaking into whatever
    # runs next in the same context.
    with run_context(run_id):
        response = await call_next(request)
    response.headers["X-Run-Id"] = run_id
    return response


@app.exception_handler(BrainError)
async def brain_error_handler(request: Request, exc: BrainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "run_id": request.state.run_id},
    )


@app.exception_handler(ResearchError)
async def research_error_handler(request: Request, exc: ResearchError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "run_id": request.state.run_id},
    )


@app.exception_handler(ContentError)
async def content_error_handler(request: Request, exc: ContentError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "run_id": request.state.run_id},
    )


@app.exception_handler(ContentMemoryError)
async def memory_error_handler(request: Request, exc: ContentMemoryError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "run_id": request.state.run_id},
    )


app.include_router(health_router, prefix="/api")
app.include_router(brain_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
