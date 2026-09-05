"""Uvicorn factory for the validation driver: real production app."""

import os
from pathlib import Path

from application.http import create_app


def app():
    return create_app(Path(os.environ["NOESPIRE_WS"]))
