#!/usr/bin/env python3
"""
CLI entrypoint: exports a Stepik course to a self-contained offline copy.

Usage:
    python tools/export_course.py --course-id 12345 [--output-dir exports/]
        [--video-quality best|360|720|1080] [--skip-videos] [--skip-attachments]
        [--log-level INFO]
"""

import argparse
import logging
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from course_tree import build_course_tree
from step_renderer import StepContext, render_step
from stepik_client import StepikAuthError, StepikClient
from toc_builder import build_toc


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
    parser.add_argument("--skip-videos", action="store_true", help="render video steps without downloading the video")
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
    except (StepikAuthError, requests.RequestException, ValueError) as exc:
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

    total_steps = sum(len(lesson["steps"]) for module in tree["modules"] for lesson in module["lessons"])
    if not total_steps:
        logger.warning("Course %s has no steps to export.", args.course_id)
    done = 0

    for module in tree["modules"]:
        module_dir = course_dir / module["dir_name"]
        for lesson in module["lessons"]:
            lesson_dir = module_dir / lesson["dir_name"]
            for step in lesson["steps"]:
                done += 1
                step_dir = lesson_dir / step["dir_name"]
                logger.info(
                    "[%d/%d] %s > %s > step %s",
                    done,
                    total_steps,
                    module["title"],
                    lesson["title"],
                    step["id"],
                )
                context = StepContext(
                    course_id=tree["id"],
                    course_title=tree["title"],
                    course_dir=course_dir,
                    module_title=module["title"],
                    lesson_id=lesson["id"],
                    lesson_title=lesson["title"],
                    video_quality=args.video_quality,
                    # per-step property call, so token refresh could happen if it expires mid-export
                    access_token=client.access_token,
                    skip_videos=args.skip_videos,
                    skip_attachments=args.skip_attachments,
                )
                render_step(step, step_dir, context)

    build_toc(tree, course_dir)
    logger.info("Steps exported: %d. Warnings: %d.", total_steps, warning_counter.count)
    logger.info("Done. Open %s in a browser.", course_dir / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
