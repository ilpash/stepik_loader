"""
The project's single Jinja environment for rendering its HTML templates.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

_env = Environment(loader=FileSystemLoader(ASSETS_DIR), autoescape=True, undefined=StrictUndefined)


def get_template(name):
    return _env.get_template(name)
