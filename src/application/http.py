"""FastAPI adapter over the application read/write modules (spec §6).

Thin by construction: this module only translates ``KeyError`` into 404,
``ValueError`` into 400, and serializes payloads. All validation and
status/failure semantics live in ``problem_index`` / ``workspace_read_model``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .problem_index import ProblemIndex
from .workspace_read_model import build_problem_list, build_read_model


class CreateProblemRequest(BaseModel):
    statement: str


def create_app(workspaces_root: Path) -> FastAPI:
    root = Path(workspaces_root)
    app = FastAPI(title="noespire", docs_url=None, redoc_url=None)

    @app.get("/api/problems")
    def list_problems() -> dict:
        return {"problems": build_problem_list(root)}

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
            return build_read_model(root, problem_id)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"error": f"unknown problem: {problem_id}"},
            )

    return app
