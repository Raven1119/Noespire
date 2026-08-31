"""FastAPI adapter over the application read modules (spec §6).

Thin by construction: this module only translates ``KeyError`` into 404 and
serializes read-model dicts. All status/failure semantics live in
``workspace_read_model``. Slice 1 exposes read endpoints only — no POST, no
background execution.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .workspace_read_model import build_problem_list, build_read_model


def create_app(workspaces_root: Path) -> FastAPI:
    root = Path(workspaces_root)
    app = FastAPI(title="noespire", docs_url=None, redoc_url=None)

    @app.get("/api/problems")
    def list_problems() -> dict:
        return {"problems": build_problem_list(root)}

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
