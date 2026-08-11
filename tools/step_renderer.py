"""
Renders a single step's `block` JSON into a self-contained index.html,
downloading any resources it references (video / images / audio / attachments)
into the step's own directory via resource_downloader.

Dedicated renderers exist for text and video blocks, and quiz blocks keep their
question text plus a note about what can't be shown offline. Every other block
type falls back to a generic "raw content" dump, with a warning logged
"""

import json
import logging
from html import escape
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

import resource_downloader

logger = logging.getLogger("stepik_export")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

# tags/attributes that may reference a downloadable resource inside step HTML
_RESOURCE_ATTRS = [("img", "src"), ("audio", "src"), ("source", "src"), ("a", "href")]


def _render_text(block, resolve, context, skip_attachments):
    html = block.get("text") or ""
    soup = BeautifulSoup(html, "html.parser")
    resource_index = 0
    for tag_name, attr in _RESOURCE_ATTRS:
        if tag_name == "a" and skip_attachments:
            continue
        for tag in soup.find_all(tag_name):
            url = tag.get(attr)
            if not url or not url.startswith("http"):
                continue
            resource_index += 1
            local = resolve(url, filename_hint=None, index=resource_index)
            if local:
                tag[attr] = local
    return str(soup)


def _pick_video_url(urls, requested, context):
    if not urls:
        return None

    def quality_to_int(u):
        try:
            return int(u.get("quality"))
        except (TypeError, ValueError):
            return -1

    if requested == "best":
        return max(urls, key=quality_to_int)

    for u in urls:
        if str(u.get("quality")) == str(requested):
            return u

    try:
        target = int(requested)
    except ValueError:
        target = 0

    def distance_from_target(u):
        q = quality_to_int(u)
        return abs(q - target) if q >= 0 else 10**9

    closest = min(urls, key=distance_from_target)
    logger.warning(
        "[%s] requested video quality %s not available, using %s instead",
        context,
        requested,
        closest.get("quality"),
    )
    return closest


def _render_video(block, resolve, context, quality, skip_videos):
    if skip_videos:
        return '<p class="warning">Video download skipped (--skip-videos).</p>'

    video = block.get("video") or {}
    urls = video.get("urls") or []
    selected = _pick_video_url(urls, quality, context)
    if not selected or not selected.get("url"):
        logger.warning("[%s] video step has no downloadable urls", context)
        return '<p class="warning">Video unavailable: no downloadable URL was returned by the API.</p>'

    local = resolve(selected["url"], filename_hint="video.mp4", index=0)
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


def _render_quiz(block):
    prompt = block.get("text") or ""
    parts = [f'<div class="prompt">{prompt}</div>'] if prompt else []
    # block["options"] holds quiz settings, not the answers -- those come from a quiz
    # dataset that needs user-level auth, which this read-only exporter always avoids.
    note = _TYPE_TO_QUIZ_NOTE[block["name"]]
    options = block.get("options")
    if isinstance(options, dict) and options.get("is_multiple_choice"):
        note += " More than one answer may be correct."
    parts.append(f'<p class="warning">{note}</p>')
    return "".join(parts)


def _render_generic(block, context):
    logger.warning("[%s] no dedicated renderer for block type '%s', using generic fallback", context, block.get("name"))
    dump = json.dumps(block, ensure_ascii=False, indent=2)
    return (
        '<p class="warning">This step type does not have a dedicated offline renderer yet. '
        "Showing the raw step data below.</p>"
        f"<pre><code>{escape(dump)}</code></pre>"
    )


def render_step(
    step_node,
    step_dir,
    course_title,
    module_title,
    lesson_title,
    access_token,
    video_quality,
    course_id,
    lesson_id,
    skip_videos=False,
    skip_attachments=False,
):
    step_dir = Path(step_dir)
    step_dir.mkdir(parents=True, exist_ok=True)
    block = step_node.get("block") or {}
    block_type = block.get("name", "unknown")
    context = f"course={course_id} lesson={lesson_id} step={step_node['id']}"

    def resolve(url, filename_hint, index):
        hint = filename_hint
        if hint is None:
            base_name = resource_downloader.safe_filename(url)
            hint = f"resource_{index}_{base_name}" if index else base_name
        return resource_downloader.download_resource(
            url, step_dir, context, access_token=access_token, filename_hint=hint
        )

    if block_type == "video":
        body_html = _render_video(block, resolve, context, video_quality, skip_videos)
    elif block_type == "text":
        body_html = _render_text(block, resolve, context, skip_attachments)
    elif block_type in _TYPE_TO_QUIZ_NOTE:
        body_html = _render_quiz(block)
    else:
        body_html = _render_generic(block, context)

    step_title = block.get("title") or f"Step {step_node['id']} ({block_type})"

    html = _env.get_template("step.html.j2").render(
        course_title=course_title,
        module_title=module_title,
        lesson_title=lesson_title,
        step_title=step_title,
        block_type=block_type,
        body_html=body_html,
        css_path="../../../assets/style.css",
        toc_path="../../../index.html",
    )
    (step_dir / "index.html").write_text(html, encoding="utf-8")
    (step_dir / "source.json").write_text(json.dumps(step_node["raw"], ensure_ascii=False, indent=2), encoding="utf-8")
    return step_title
