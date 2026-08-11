"""
Builds the single root index.html table of contents for an exported course,
and copies the project's one style.css template into the export so the whole
course folder is self-contained (no path back into the project).
"""
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)


def build_toc(course_tree, course_dir):
    course_dir = Path(course_dir)
    assets_dir = course_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATES_DIR / "style.css", assets_dir / "style.css")

    modules = []
    for module in course_tree["modules"]:
        lessons = []
        for lesson in module["lessons"]:
            steps = [
                {
                    "title": step.get("title") or step["dir_name"],
                    "href": f"{module['dir_name']}/{lesson['dir_name']}/{step['dir_name']}/index.html",
                }
                for step in lesson["steps"]
            ]
            lessons.append({"title": lesson["title"], "steps": steps})
        modules.append({"title": module["title"], "lessons": lessons})

    html = _env.get_template("toc.html.j2").render(
        course_title=course_tree["title"],
        course_id=course_tree["id"],
        export_date=datetime.now().strftime("%Y-%m-%d"),
        modules=modules,
        css_path="assets/style.css",
    )
    (course_dir / "index.html").write_text(html, encoding="utf-8")
