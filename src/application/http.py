"""FastAPI adapter over the application read/write modules (spec §6).

Thin by construction: this module only translates ``KeyError`` into 404,
``ValueError`` into 400, and claim-state errors into 409, and serializes
payloads. All validation, status/failure, and execution semantics live in
``problem_index`` / ``workspace_read_model`` / ``execution``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .execution import AlreadyRunningError, AlreadySolvedError, ExecutionService
from .problem_index import ProblemIndex
from .workspace_read_model import build_problem_list, build_read_model


class CreateProblemRequest(BaseModel):
    statement: str


class ForkProblemRequest(BaseModel):
    statement: str


class ArchiveProblemRequest(BaseModel):
    archived: bool


def create_app(
    workspaces_root: Path,
    execution_service: Optional[ExecutionService] = None,
) -> FastAPI:
    root = Path(workspaces_root)
    service = execution_service or ExecutionService(root)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Crash-consistency recovery, once per server start (spec §7.3).
        service.recover_stale_running()
        yield

    app = FastAPI(title="noespire", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/api/problems")
    def list_problems() -> dict:
        return {"problems": build_problem_list(root, execution_service=service)}

    @app.post("/api/problems")
    def create_problem(request: CreateProblemRequest):
        try:
            entry = ProblemIndex(root).add(request.statement)
        except ValueError as error:
            # Only validation failure maps to 400 (spec §6); anything else
            # propagates as a genuine 500.
            return JSONResponse(status_code=400, content={"error": str(error)})
        # A freshly created problem has no obligation yet: OPEN by construction.
        return JSONResponse(
            status_code=201,
            content={
                "problem_id": entry.problem_id,
                "statement": entry.statement,
                "status": "OPEN",
                "derived_from": entry.derived_from,
                "archived": entry.archived,
            },
        )

    @app.get("/api/problems/{problem_id}")
    def get_problem(problem_id: str):
        try:
            return build_read_model(root, problem_id, execution_service=service)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": f"unknown problem: {problem_id}"},
            )

    @app.post("/api/problems/{problem_id}/fork")
    def fork_problem(problem_id: str, request: ForkProblemRequest):
        try:
            entry = ProblemIndex(root).fork(problem_id, request.statement)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": f"unknown problem: {problem_id}"},
            )
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": str(error)})
        # A forked child has no obligation yet: OPEN by construction.
        return JSONResponse(
            status_code=201,
            content={
                "problem_id": entry.problem_id,
                "statement": entry.statement,
                "status": "OPEN",
                "derived_from": entry.derived_from,
                "archived": entry.archived,
            },
        )

    @app.post("/api/problems/{problem_id}/archive")
    def archive_problem(problem_id: str, request: ArchiveProblemRequest):
        try:
            entry = ProblemIndex(root).set_archived(problem_id, request.archived)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": f"unknown problem: {problem_id}"},
            )
        return {"archived": entry.archived}

    @app.post("/api/problems/{problem_id}/attempts")
    def start_attempt(problem_id: str):
        try:
            service.start_attempt(problem_id)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": f"unknown problem: {problem_id}"},
            )
        except AlreadySolvedError:
            return JSONResponse(status_code=409, content={"error": "already_solved"})
        except AlreadyRunningError:
            return JSONResponse(status_code=409, content={"error": "already_running"})
        # No attempt id in the response (freeze ruling 3): the attempt file
        # only exists once execution starts; the UI polls the read model.
        return JSONResponse(status_code=202, content={"status": "accepted"})

    return app
