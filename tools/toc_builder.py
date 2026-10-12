"""
Builds the single root index.html table of contents for an exported course,
and copies the project's one style.css template into the export so the whole
course folder is self-contained (no path back into the project).
"""

import shutil
from datetime import datetime
from pathlib import Path

from template_env import TEMPLATES_DIR, get_template


def build_toc(course_tree, course_dir, skipped_step_ids):
    course_dir = Path(course_dir)
    assets_dir = course_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATES_DIR / "style.css", assets_dir / "style.css")

    html = get_template("toc.html.j2").render(
        course_title=course_tree["title"],
        course_id=course_tree["id"],
        export_date=datetime.now().strftime("%Y-%m-%d"),
        modules=course_tree["modules"],
        skipped_step_ids=skipped_step_ids,
        css_path="assets/style.css",
    )
    (course_dir / "index.html").write_text(html, encoding="utf-8")
