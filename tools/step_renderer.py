"""
Renders a single step's `block` JSON into a self-contained index.html,
downloading any resources it references (video / images / audio / attachments)
into the step's own directory via resource_downloader.

Dedicated renderers exist for text, video, code and pycharm blocks, and quiz
blocks keep their question text plus a note about what can't be shown offline.
Every other block type falls back to a generic "raw content" dump, with a
warning logged. A hyperlink is only downloaded when it points at a file --
links to web pages keep the URL the course author wrote.
"""

import json
import logging
import math
import os
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import markdown
from bs4 import BeautifulSoup

import resource_downloader
from template_env import get_template

logger = logging.getLogger("stepik_export")

# Tags/attributes that may reference a downloadable resource inside step HTML
_RESOURCE_ATTRS = [("img", "src"), ("audio", "src"), ("source", "src"), ("a", "href")]

STEPIK_BASE_URL = "https://stepik.org"


@dataclass(frozen=True)
class StepContext:
    course_id: int
    course_title: str
    course_dir: Path
    module_title: str
    lesson_id: int
    lesson_title: str
    video_quality: str
    access_token: str
    skip_videos: bool = False
    skip_attachments: bool = False

    def log_label(self, step_id):
        return f"course={self.course_id} lesson={self.lesson_id} step={step_id}"

    def link_from(self, step_dir, *course_relative_parts):
        target = self.course_dir.joinpath(*course_relative_parts)
        return Path(os.path.relpath(target, step_dir)).as_posix()


def _is_downloadable_file(url):
    # Only <a> hrefs are asked this: an anchor points either at a file to save or at a
    # web page to keep as a link, and the media type of its path tells the two apart.
    # img/audio/source always point at media and never reach this check, so an image
    # still downloads when Stepik serves it from an extensionless URL.
    guessed_type, _ = resource_downloader.BUILTIN_MIME_TYPES.guess_type(urlparse(url).path)
    return bool(guessed_type and guessed_type != "text/html")


def _normalize_url_to_absolute(url):
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return STEPIK_BASE_URL + url
    return url


def _render_text(block, resolve, skip_attachments):
    html = block.get("text", "")
    soup = BeautifulSoup(html, "html.parser")
    resource_index = 0
    for tag_name, attr in _RESOURCE_ATTRS:
        for tag in soup.find_all(tag_name):
            url = _normalize_url_to_absolute(tag.get(attr))
            if not url.startswith("http"):
                continue
            if tag_name == "a" and (skip_attachments or not _is_downloadable_file(url)):
                tag[attr] = url
                continue
            resource_index += 1
            filename_hint = f"resource_{resource_index}_{resource_downloader.safe_filename(url)}"
            tag[attr] = resolve(url, filename_hint) or url
    return str(soup)


def _pick_video_url(urls, requested, log_label):
    if not urls:
        return None

    def quality_to_int(url_entry):
        try:
            return int(url_entry.get("quality"))
        except (TypeError, ValueError):
            return -1

    if requested == "best":
        return max(urls, key=quality_to_int)

    target = int(requested)

    def distance_from_target(url_entry):
        quality = quality_to_int(url_entry)
        return abs(quality - target) if quality >= 0 else math.inf

    closest = min(urls, key=distance_from_target)
    if quality_to_int(closest) != target:
        logger.warning(
            "[%s] requested video quality %s not available, using %s instead",
            log_label,
            requested,
            closest.get("quality"),
        )
    return closest


def _render_video(block, resolve, log_label, quality, skip_videos):
    video = block.get("video", {})
    urls = video.get("urls", [])
    selected = _pick_video_url(urls, quality, log_label)
    if not selected or not selected.get("url"):
        logger.warning("[%s] video step has no downloadable urls", log_label)
        return '<p class="warning">Video unavailable: no downloadable URL was returned by the API.</p>'

    if skip_videos:
        return (
            f'<video controls src="{escape(selected["url"])}"></video>'
            '<p class="warning">Video download skipped (--skip-videos), so it plays only when you are online.</p>'
        )

    local = resolve(selected["url"], "video.mp4")
    if not local:
        return '<p class="warning">Video download failed. See the export log for details.</p>'
    return f'<video controls src="{escape(local)}"></video>'


# Quiz steps keep their question text. Some also lose the items you would work with,
# others only lose grading, so there are two notes rather than one per type.
_MISSING_ITEMS_NOTE = (
    "This step asks you to {task}; the items are not returned by the API, so they are not available offline."
)
_TYPED_ANSWER_NOTE = "This step expects a typed answer; grading is not available offline."

_TYPE_TO_QUIZ_NOTE = {
    "choice": _MISSING_ITEMS_NOTE.format(task="choose an answer"),
    "sorting": _MISSING_ITEMS_NOTE.format(task="sort a list"),
    "matching": _MISSING_ITEMS_NOTE.format(task="match pairs"),
    "string": _TYPED_ANSWER_NOTE,
    "number": _TYPED_ANSWER_NOTE,
    "free-answer": _TYPED_ANSWER_NOTE,
}


def _render_quiz(block, resolve, skip_attachments):
    parts = [_render_text(block, resolve, skip_attachments)]
    # block["options"] holds quiz settings, not the answers -- those come from a quiz
    # dataset that needs user-level auth, which this read-only exporter always avoids.
    note = _TYPE_TO_QUIZ_NOTE[block["name"]]
    if block.get("options", {}).get("is_multiple_choice"):
        note += " More than one answer may be correct."
    parts.append(f'<p class="warning">{note}</p>')
    return "".join(parts)


def _render_code_samples(samples):
    if not samples:
        return ""
    parts = ["<h2>Samples</h2>"]
    for index, (sample_input, expected_output) in enumerate(samples, start=1):
        parts.append(
            f"<h3>Sample {index}</h3>"
            f"<h4>Input</h4><pre><code>{escape(sample_input)}</code></pre>"
            f"<h4>Expected output</h4><pre><code>{escape(expected_output)}</code></pre>"
        )
    return "".join(parts)


def _render_code_default_limits(options):
    # Stepik builds both limits from one source and puts them in the options dict
    # together, so they are either both there or both missing -- never one alone.
    time_limit = options.get("execution_time_limit")
    memory_limit = options.get("execution_memory_limit")
    if time_limit is None:
        return ""
    return f"<p>Default limits: {time_limit} s, {memory_limit} MB.</p>"


def _render_code_templates(options):
    # Courses commonly offer 20-45 languages, so each template collapses into its
    # own <details> to keep the problem statement and samples at the top of the page.
    # options["limits"] is a per-language table that usually overrides the step defaults.
    language_limits = options.get("limits", {})
    parts = []
    for language, source in sorted(options.get("code_templates", {}).items()):
        if not source.strip():
            continue
        label = escape(language)
        limit = language_limits.get(language)
        if limit:
            label += f" — {limit['time']} s, {limit['memory']} MB"
        parts.append(f"<details><summary>{label}</summary><pre><code>{escape(source)}</code></pre></details>")
    if not parts:
        return ""
    return "".join(["<h2>Starter code</h2>", *parts])


def _render_code(block, resolve, skip_attachments):
    options = block.get("options", {})
    parts = [
        _render_text(block, resolve, skip_attachments),
        _render_code_samples(options.get("samples")),
        _render_code_default_limits(options),
        _render_code_templates(options),
        '<p class="warning">This step asks you to write a program; submitting a solution and '
        "grading are not available offline.</p>",
    ]
    return "".join(parts)


def _render_pycharm_files(files):
    if not files:
        return ""
    parts = ["<h2>Files</h2>"]
    for file in files:
        label = escape(file["name"])
        # A plain task file often omits is_visible, so only an explicit false means hidden.
        if file.get("is_visible") is False:
            label += ' <span class="hidden-file">hidden</span>'
        parts.append(f"<h3>{label}</h3>")
        source = file["text"]
        parts.append(f"<pre><code>{escape(source)}</code></pre>" if source.strip() else "<p>This file is empty.</p>")
    return "".join(parts)


def _render_pycharm(block, resolve, skip_attachments):
    options = block.get("options", {})
    # Most statements are already HTML, but some arrive as markdown, which the format names.
    if (options.get("description_format") or "").upper() == "MD":
        block = {**block, "text": markdown.markdown(block["text"], extensions=["tables", "fenced_code"])}
    parts = [
        _render_text(block, resolve, skip_attachments),
        _render_pycharm_files(options.get("files")),
        '<p class="warning">This step is solved in an IDE; submitting a solution and grading '
        "are not available offline.</p>",
    ]
    return "".join(parts)


def _render_generic(block, log_label):
    logger.warning(
        "[%s] no dedicated renderer for block type '%s', using generic fallback", log_label, block.get("name")
    )
    dump = json.dumps(block, ensure_ascii=False, indent=2)
    return (
        '<p class="warning">This step type does not have a dedicated offline renderer yet. '
        "Showing the raw step data below.</p>"
        f"<pre><code>{escape(dump)}</code></pre>"
    )


def render_step(step_node, step_dir, context):
    step_dir = Path(step_dir)
    step_dir.mkdir(parents=True, exist_ok=True)
    block = step_node["block"]
    block_type = block.get("name", "unknown")
    log_label = context.log_label(step_node["id"])

    resolved = {}

    def resolve(url, filename_hint):
        # The same URL can appear in several tags of one step, so download it once.
        if url not in resolved:
            resolved[url] = resource_downloader.download_resource(
                url, step_dir, log_label, access_token=context.access_token, filename_hint=filename_hint
            )
        return resolved[url]

    if block_type == "video":
        body_html = _render_video(block, resolve, log_label, context.video_quality, context.skip_videos)
    elif block_type == "text":
        body_html = _render_text(block, resolve, context.skip_attachments)
    elif block_type == "code":
        body_html = _render_code(block, resolve, context.skip_attachments)
    elif block_type == "pycharm":
        body_html = _render_pycharm(block, resolve, context.skip_attachments)
    elif block_type in _TYPE_TO_QUIZ_NOTE:
        body_html = _render_quiz(block, resolve, context.skip_attachments)
    else:
        body_html = _render_generic(block, log_label)

    html = get_template("step.html.j2").render(
        course_title=context.course_title,
        module_title=context.module_title,
        lesson_title=context.lesson_title,
        step_title=step_node["title"],
        block_type=block_type,
        body_html=body_html,
        css_path=context.link_from(step_dir, "assets", "style.css"),
        toc_path=context.link_from(step_dir, "index.html"),
    )
    (step_dir / "index.html").write_text(html, encoding="utf-8")
    (step_dir / "source.json").write_text(json.dumps(step_node["raw"], ensure_ascii=False, indent=2), encoding="utf-8")
