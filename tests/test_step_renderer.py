import json

import pytest

import resource_downloader
from step_renderer import (
    _TYPE_TO_QUIZ_NOTE,
    _pick_video_url,
    _render_generic,
    _render_quiz,
    _render_text,
    _render_video,
    render_step,
)

# -- _pick_video_url ---------------------------------------------------------


def test_pick_video_url_returns_none_for_empty_list():
    assert _pick_video_url([], "best", "test-context") is None


def test_pick_video_url_best_picks_highest_quality():
    urls = [{"quality": "360", "url": "a"}, {"quality": "1080", "url": "b"}, {"quality": "720", "url": "c"}]
    assert _pick_video_url(urls, "best", "test-context") == {"quality": "1080", "url": "b"}


def test_pick_video_url_exact_string_match():
    urls = [{"quality": "360", "url": "a"}, {"quality": "720", "url": "b"}, {"quality": "1080", "url": "c"}]
    assert _pick_video_url(urls, "720", "test-context") == {"quality": "720", "url": "b"}


def test_pick_video_url_falls_back_to_nearest_when_exact_missing(caplog):
    # 720 falls between 480 and 1080, nearer to 480 (240 away) than 1080 (360 away).
    urls = [{"quality": "360", "url": "a"}, {"quality": "480", "url": "b"}, {"quality": "1080", "url": "c"}]
    result = _pick_video_url(urls, "720", "test-context")
    assert result == {"quality": "480", "url": "b"}
    assert "not available" in caplog.text


def test_pick_video_url_single_item_list_returns_it_regardless():
    urls = [{"quality": "240", "url": "only"}]
    assert _pick_video_url(urls, "best", "test-context") == urls[0]


def test_pick_video_url_falls_back_to_lowest_when_requested_is_not_numeric(caplog):
    urls = [{"quality": "360", "url": "a"}, {"quality": "1080", "url": "b"}, {"quality": "720", "url": "c"}]
    result = _pick_video_url(urls, "hd", "test-context")
    assert result == {"quality": "360", "url": "a"}
    assert "not available" in caplog.text


# -- pure block renderers -----------------------------------------------------


def test_render_quiz_basic_case():
    # Real API shape: block["options"] is a settings dict, not a list of answers.
    block = {"name": "choice", "text": "Mark every true statement.", "options": {"is_multiple_choice": True}}
    html = _render_quiz(block)
    assert "Mark every true statement." in html
    assert "not available offline" in html
    assert "is_multiple_choice" not in html
    assert "<li>" not in html


@pytest.mark.parametrize("block_type", sorted(_TYPE_TO_QUIZ_NOTE))
def test_render_quiz_keeps_the_question_for_every_quiz_type(block_type):
    block = {"name": block_type, "text": "The question", "options": {}}
    html = _render_quiz(block)
    assert "The question" in html
    assert 'class="warning"' in html


def test_render_quiz_notes_when_more_than_one_answer_may_be_correct():
    block = {"name": "choice", "text": "Pick all that apply", "options": {"is_multiple_choice": True}}
    html = _render_quiz(block)
    assert "More than one answer may be correct" in html


def test_render_quiz_omits_multiple_answer_note_for_single_choice():
    block = {"name": "choice", "text": "Pick one", "options": {"is_multiple_choice": False}}
    html = _render_quiz(block)
    assert "More than one answer" not in html


def test_render_generic_dumps_raw_block_as_json(caplog):
    block = {"name": "unknown-type", "custom_field": "custom_value"}
    html = _render_generic(block, "test-context")
    assert "<pre><code>" in html
    assert "&quot;custom_field&quot;" in html
    assert "no dedicated renderer" in caplog.text


# -- _render_text --------------------------------------------------------------


def test_render_text_rewrites_img_src_via_resolve():
    block = {"text": '<img src="http://x.com/a.png">'}
    calls = []

    def mock_resolve(url, filename_hint, index):
        calls.append(url)
        return "local.png"

    html = _render_text(block=block, resolve=mock_resolve, context="test-context", skip_attachments=False)
    assert 'src="local.png"' in html
    assert calls == ["http://x.com/a.png"]


def test_render_text_skips_non_http_src():
    # A data: URI src never matches the "http"-prefix check, so resolve is never called.
    block = {"text": '<img src="data:image/png;base64,abc">'}
    html = _render_text(block=block, resolve=None, context="test-context", skip_attachments=False)
    assert "data:image/png;base64,abc" in html


def test_render_text_skips_anchor_tags_when_skip_attachments_true():
    # The only tag present is an <a>, and skip_attachments=True skips anchor
    # tags entirely, so resolve is never called.
    block = {"text": '<a href="http://x.com/f.pdf">link</a>'}
    html = _render_text(block=block, resolve=None, context="test-context", skip_attachments=True)
    assert 'href="http://x.com/f.pdf"' in html


# -- _render_video --------------------------------------------------------------


def test_render_video_returns_warning_html_when_skip_videos_true():
    html = _render_video(
        block={"video": {"urls": [{"quality": "720", "url": "x"}]}},
        resolve=None,
        context="test-context",
        quality="best",
        skip_videos=True,
    )
    assert "skipped" in html


def test_render_video_returns_warning_when_no_urls():
    # urls=[] makes _pick_video_url return None, so _render_video returns
    # its "unavailable" warning before ever calling resolve.
    html = _render_video(
        block={"video": {"urls": []}},
        resolve=None,
        context="test-context",
        quality="best",
        skip_videos=False,
    )
    assert "unavailable" in html.lower()


def test_render_video_calls_resolve_with_selected_url_and_returns_video_tag():
    block = {"video": {"urls": [{"quality": "720", "url": "http://x.com/v.mp4"}]}}

    def mock_resolve(url, filename_hint, index):
        assert url == "http://x.com/v.mp4"
        assert filename_hint == "video.mp4"
        return "video.mp4"

    html = _render_video(
        block=block,
        resolve=mock_resolve,
        context="test-context",
        quality="best",
        skip_videos=False,
    )
    assert html == '<video controls src="video.mp4"></video>'


def test_render_video_returns_warning_when_resolve_fails():
    block = {"video": {"urls": [{"quality": "720", "url": "http://x.com/v.mp4"}]}}

    def mock_resolve(url, filename_hint, index):
        return None

    html = _render_video(
        block=block,
        resolve=mock_resolve,
        context="test-context",
        quality="best",
        skip_videos=False,
    )
    assert "download failed" in html.lower()


# -- render_step (integration of the above via the real resolve() closure) -----


def _make_step_node(block, step_id=1):
    return {"id": step_id, "block": block, "raw": {"id": step_id, "block": block}}


def test_render_step_creates_step_dir_and_writes_index_and_source_json(tmp_path, monkeypatch):
    monkeypatch.setattr(resource_downloader, "download_resource", None)
    step_dir = tmp_path / "step_01_text"
    block = {"name": "text", "text": "hello", "title": "My Step"}
    step_node = _make_step_node(block)

    title = render_step(
        step_node=step_node,
        step_dir=step_dir,
        course_title="Course",
        module_title="Module",
        lesson_title="Lesson",
        access_token="test-token",
        video_quality="best",
        course_id=1,
        lesson_id=2,
    )

    assert title == "My Step"
    html = (step_dir / "index.html").read_text()
    assert "My Step" in html
    assert "hello" in html
    source = json.loads((step_dir / "source.json").read_text())
    assert source == step_node["raw"]


def test_render_step_falls_back_to_generated_title_when_block_has_no_title(tmp_path, monkeypatch):
    monkeypatch.setattr(resource_downloader, "download_resource", None)
    block = {"name": "text", "text": "hello"}
    step_node = _make_step_node(block, step_id=42)

    title = render_step(
        step_node=step_node,
        step_dir=tmp_path / "step",
        course_title="Course",
        module_title="Module",
        lesson_title="Lesson",
        access_token="test-token",
        video_quality="best",
        course_id=1,
        lesson_id=2,
    )

    assert title == "Step 42 (text)"


def test_render_step_dispatches_unknown_block_type_to_generic_renderer(tmp_path, monkeypatch):
    monkeypatch.setattr(resource_downloader, "download_resource", None)
    block = {"name": "quiz", "custom_field": "custom_value"}
    step_node = _make_step_node(block)
    step_dir = tmp_path / "step"

    render_step(
        step_node=step_node,
        step_dir=step_dir,
        course_title="Course",
        module_title="Module",
        lesson_title="Lesson",
        access_token="test-token",
        video_quality="best",
        course_id=1,
        lesson_id=2,
    )

    html = (step_dir / "index.html").read_text()
    assert "raw step data" in html
