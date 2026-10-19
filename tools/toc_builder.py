"""
Builds the single root index.html table of contents for an exported course,
and copies the project's assets folder into the export so the whole course
folder is self-contained (no path back into the project).
"""

import shutil
from datetime import datetime

from template_env import ASSETS_DIR, get_template


def build_toc(course_tree, course_dir, skipped_step_ids):
    shutil.copytree(ASSETS_DIR, course_dir / "assets", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".*"))

    html = get_template("toc.html.j2").render(
        course_title=course_tree["title"],
        course_id=course_tree["id"],
        export_date=datetime.now().strftime("%Y-%m-%d"),
        modules=course_tree["modules"],
        skipped_step_ids=skipped_step_ids,
        css_path="assets/style.css",
    )
    (course_dir / "index.html").write_text(html, encoding="utf-8")
