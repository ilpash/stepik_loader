"""
The project's single Jinja environment for rendering its HTML templates.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


def get_template(name):
    return _env.get_template(name)
