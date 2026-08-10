#!/usr/bin/env python3
"""CLI entrypoint: exports a Stepik course to a self-contained offline copy.

Usage:
    python tools/export_course.py --course-id 12345 [--output-dir exports/]
        [--video-quality best|360|720|1080] [--skip-videos] [--skip-attachments]
        [--log-level INFO]
"""
import argparse
import logging
import sys
from pathlib import Path

from course_tree import build_course_tree
from stepik_client import StepikAuthError, StepikClient
from step_renderer import render_step
from toc_builder import build_toc

logger = logging.getLogger("stepik_export")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Export a Stepik course for offline use.")
    parser.add_argument("--course-id", type=int, required=True)
    parser.add_argument("--output-dir", default="exports")
    parser.add_argument("--video-quality", default="best", choices=["best", "360", "720", "1080"])
    parser.add_argument("--skip-videos", action="store_true")
    parser.add_argument("--skip-attachments", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    try:
        client = StepikClient()
    except StepikAuthError as exc:
        logger.error(str(exc))
        return 1

    print(f"Fetching course {args.course_id} structure...")
    try:
        tree = build_course_tree(client, args.course_id)
    except Exception as exc:
        logger.error(
            "Failed to fetch course %s. If this course is paid/private/enrolled-only, "
            "it isn't accessible with the client_credentials auth used by this tool. (%s)",
            args.course_id, exc,
        )
        return 1

    course_dir = Path(args.output_dir) / tree["dir_name"]
    print(f"Exporting '{tree['title']}' to {course_dir}/")

    access_token = client.access_token
    total_steps = sum(len(l["steps"]) for m in tree["modules"] for l in m["lessons"])
    done = 0

    for module in tree["modules"]:
        module_dir = course_dir / module["dir_name"]
        for lesson in module["lessons"]:
            lesson_dir = module_dir / lesson["dir_name"]
            for step in lesson["steps"]:
                done += 1
                step_dir = lesson_dir / step["dir_name"]
                print(f"[{done}/{total_steps}] {module['title']} > {lesson['title']} > step {step['id']}")
                step_title = render_step(
                    step, step_dir,
                    course_title=tree["title"],
                    module_title=module["title"],
                    lesson_title=lesson["title"],
                    access_token=access_token,
                    video_quality=args.video_quality,
                    course_id=tree["id"],
                    lesson_id=lesson["id"],
                    skip_videos=args.skip_videos,
                    skip_attachments=args.skip_attachments,
                )
                step["title"] = step_title

    build_toc(tree, course_dir)
    print(f"Done. Open {course_dir / 'index.html'} in a browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
