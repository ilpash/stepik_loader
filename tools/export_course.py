"""
CLI entrypoint: exports a Stepik course to a self-contained offline copy.

Usage:
    python tools/export_course.py --course-id 12345 [--output-dir exports/]
        [--video-quality best|360|720|1080] [--skip-videos] [--skip-attachments]
        [--log-level INFO]
"""

import argparse
import errno
import logging
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from course_tree import CourseNotFoundError, build_course_tree
from step_renderer import StepContext, render_step
from stepik_client import StepikAuthError, StepikClient
from toc_builder import build_toc

DISK_FULL_ERROR_CODES = {errno.ENOSPC, errno.EDQUOT}


class WarningCounter(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, _record):
        self.count += 1


logger = logging.getLogger("stepik_export")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
logger.addHandler(console_handler)

warning_counter = WarningCounter()
logger.addHandler(warning_counter)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Export a Stepik course for offline use.")
    parser.add_argument("--course-id", type=int, required=True, help="id of the public Stepik course to export")
    parser.add_argument("--output-dir", default="exports", help="parent directory for the exported course folder")
    parser.add_argument(
        "--video-quality",
        default="best",
        choices=["best", "360", "720", "1080"],
        help="preferred video resolution; if a step is not available in it, the closest one is used",
    )
    parser.add_argument(
        "--skip-videos", action="store_true", help="link video steps to the online video instead of downloading it"
    )
    parser.add_argument("--skip-attachments", action="store_true", help="leave linked files as their original url")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="lowest log severity printed to the console",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    console_handler.setLevel(args.log_level)
    load_dotenv()
    warning_counter.count = 0

    try:
        client = StepikClient()
    except StepikAuthError as exc:
        logger.error(str(exc))
        return 1

    logger.info("Fetching course %s structure...", args.course_id)
    try:
        tree = build_course_tree(client, args.course_id)
    except (StepikAuthError, requests.RequestException, CourseNotFoundError) as exc:
        logger.error(
            "Failed to fetch course %s (%s). Check the credentials in .env and your network "
            "connection; paid, private and enrolled-only courses are not reachable with the "
            "client_credentials auth this tool uses.",
            args.course_id,
            exc,
        )
        return 1

    course_dir = Path(args.output_dir) / tree["dir_name"]
    logger.info("Exporting '%s' to %s/", tree["title"], course_dir)

    steps = [
        (module, lesson, step) for module in tree["modules"] for lesson in module["lessons"] for step in lesson["steps"]
    ]
    if not steps:
        logger.warning("Course %s has no steps to export.", args.course_id)
    skipped_step_ids = set()

    for done, (module, lesson, step) in enumerate(steps, start=1):
        step_dir = course_dir / module["dir_name"] / lesson["dir_name"] / step["dir_name"]
        logger.info("[%d/%d] %s > %s > step %s", done, len(steps), module["title"], lesson["title"], step["id"])
        context = StepContext(
            course_id=tree["id"],
            course_title=tree["title"],
            course_dir=course_dir,
            module_title=module["title"],
            lesson_id=lesson["id"],
            lesson_title=lesson["title"],
            video_quality=args.video_quality,
            # Read on every step, so a token that expires mid-export is refreshed
            access_token=client.access_token,
            skip_videos=args.skip_videos,
            skip_attachments=args.skip_attachments,
        )
        try:
            render_step(step, step_dir, context)
        except OSError as exc:
            if exc.errno in DISK_FULL_ERROR_CODES:
                logger.error("The disk is full, stopping the export: %s", exc)
                return 1
            logger.warning("[%s] could not write the step, skipping it: %s", context.log_label(step["id"]), exc)
            skipped_step_ids.add(step["id"])

    build_toc(tree, course_dir, skipped_step_ids)
    logger.info("Steps exported: %d. Warnings: %d.", len(steps) - len(skipped_step_ids), warning_counter.count)
    logger.info("Done. Open %s in a browser.", course_dir / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
