import json
from unittest.mock import MagicMock

import pytest

from step_renderer import (
    _TYPE_TO_QUIZ_NOTE,
    StepContext,
    _pick_video_url,
    _render_code,
    _render_generic,
    _render_pycharm,
    _render_quiz,
    _render_text,
    _render_video,
    render_step,
)


@pytest.fixture
def mock_resolve():
    return MagicMock(return_value="local_resource")


# -- _pick_video_url ---------------------------------------------------------


def test_pick_video_url_returns_none_for_empty_list():
    assert _pick_video_url([], "best", "test-context") is None


def _video_url(quality):
    return {"quality": quality, "url": f"https://cdn.example.com/lecture-{quality}.mp4"}


def test_pick_video_url_best_picks_highest_quality():
    urls = [_video_url("360"), _video_url("1080"), _video_url("720")]
    assert _pick_video_url(urls, "best", "test-context") == _video_url("1080")


def test_pick_video_url_exact_match(caplog):
    urls = [_video_url("360"), _video_url("720"), _video_url("1080")]
    assert _pick_video_url(urls, "720", "test-context") == _video_url("720")
    assert "not available" not in caplog.text


def test_pick_video_url_falls_back_to_nearest_when_exact_missing(caplog):
    # 720 falls between 480 and 1080, nearer to 480 (240 away) than 1080 (360 away).
    urls = [_video_url("360"), _video_url("480"), _video_url("1080")]
    result = _pick_video_url(urls, "720", "test-context")
    assert result == _video_url("480")
    assert "not available" in caplog.text


def test_pick_video_url_single_item_list_returns_it_regardless():
    urls = [_video_url("240")]
    assert _pick_video_url(urls, "best", "test-context") == urls[0]


def test_pick_video_url_skips_an_entry_with_an_unreadable_quality():
    urls = [_video_url(None), _video_url("360")]
    result = _pick_video_url(urls, "720", "test-context")
    assert result == _video_url("360")


# -- pure block renderers -----------------------------------------------------


def test_render_quiz_basic_case(mock_resolve):
    # Real API shape: block["options"] is a settings dict, not a list of answers.
    mock_resolve.return_value = "local_picture.png"
    block = {
        "name": "choice",
        "text": '<img src="https://cdn.example.com/some_picture.png"> Mark every true statement.',
        "options": {"is_multiple_choice": True},
    }
    html = _render_quiz(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Mark every true statement." in html
    assert 'src="local_picture.png"' in html
    assert "not available offline" in html
    assert "More than one answer may be correct" in html
    assert "is_multiple_choice" not in html
    assert "<li>" not in html


@pytest.mark.parametrize("block_type", sorted(_TYPE_TO_QUIZ_NOTE))
def test_render_quiz_keeps_the_question_for_every_quiz_type(block_type, mock_resolve):
    block = {"name": block_type, "text": "The question", "options": {}}
    html = _render_quiz(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "The question" in html
    assert 'class="warning"' in html


def test_render_quiz_omits_multiple_answer_note_for_single_choice(mock_resolve):
    block = {"name": "choice", "text": "Pick one", "options": {"is_multiple_choice": False}}
    html = _render_quiz(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "More than one answer" not in html


def test_render_generic_dumps_raw_block_as_json(caplog):
    block = {"name": "unknown-type", "custom_field": "custom_value"}
    html = _render_generic(block, "test-context")
    assert "<pre><code>" in html
    assert "&quot;custom_field&quot;" in html
    assert "no dedicated renderer" in caplog.text


# -- _render_text --------------------------------------------------------------


def test_render_text_rewrites_img_src_via_resolve(mock_resolve):
    mock_resolve.return_value = "local.png"
    block = {"text": '<img src="https://cdn.example.com/diagram.png">'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local.png"' in html
    mock_resolve.assert_called_once_with("https://cdn.example.com/diagram.png", "resource_1_diagram.png")


def test_render_text_skips_non_http_src(mock_resolve):
    block = {"text": '<img src="data:image/png;base64,abc">'}
    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "data:image/png;base64,abc" in html
    assert mock_resolve.call_count == 0


def test_render_text_skips_anchor_tags_when_skip_attachments_true(mock_resolve):
    block = {"text": '<a href="https://cdn.example.com/handout.pdf">link</a>'}
    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=True)
    assert 'href="https://cdn.example.com/handout.pdf"' in html
    assert mock_resolve.call_count == 0


def test_render_text_downloads_an_image_from_a_root_relative_url(mock_resolve):
    # Stepik writes its own media root-relative, which resolves against file:// offline.
    mock_resolve.return_value = "local_city.jpg"
    block = {"text": '<img src="/media/attachments/lessons/460/city.jpg">'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local_city.jpg"' in html
    mock_resolve.assert_called_once_with(
        "https://stepik.org/media/attachments/lessons/460/city.jpg", "resource_1_city.jpg"
    )


def test_render_text_keeps_the_absolute_url_when_a_download_fails(mock_resolve):
    mock_resolve.return_value = None
    block = {"text": '<img src="/media/attachments/lessons/460/city.jpg">'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="https://stepik.org/media/attachments/lessons/460/city.jpg"' in html


def test_render_text_downloads_audio_from_a_protocol_relative_url(mock_resolve):
    mock_resolve.return_value = "local_word.mp3"
    block = {"text": '<audio src="//audio.example.com/some_recording.mp3"></audio>'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local_word.mp3"' in html
    mock_resolve.assert_called_once_with(
        "https://audio.example.com/some_recording.mp3", "resource_1_some_recording.mp3"
    )


def test_render_text_adds_the_site_to_a_root_relative_page_link(mock_resolve):
    block = {"text": '<a href="/lesson/some-lesson-42/step/3">the next step</a>'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'href="https://stepik.org/lesson/some-lesson-42/step/3"' in html
    assert mock_resolve.call_count == 0


def test_render_text_adds_the_site_to_a_root_relative_link_when_skip_attachments_true(mock_resolve):
    block = {"text": '<a href="/media/attachments/lesson/42/notes.pdf">notes</a>'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=True)

    assert 'href="https://stepik.org/media/attachments/lesson/42/notes.pdf"' in html
    assert mock_resolve.call_count == 0


def test_render_text_downloads_an_anchor_that_points_at_a_file(mock_resolve):
    mock_resolve.return_value = "local_notes.pdf"
    attachment_url = "https://stepik.org/media/attachments/lesson/42/notes.pdf"
    block = {"text": f'<a href="{attachment_url}">notes</a>'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'href="local_notes.pdf"' in html
    mock_resolve.assert_called_once_with(attachment_url, "resource_1_notes.pdf")


@pytest.mark.parametrize(
    "page_url",
    [
        "https://www.youtube.com/watch?v=some_video_id",
        "https://bit.ly/some_short_link",
        "https://stepik.org/lesson/some-lesson-42/step/3?unit=100",
        "https://en.wikipedia.org/wiki/Some_article",
        "https://example.com/some_page.html",
    ],
)
def test_render_text_keeps_an_anchor_that_points_at_a_web_page(page_url, mock_resolve):
    # A web page is worthless offline and mirroring it would replace the live URL.
    block = {"text": f'<a href="{page_url}">link</a>'}
    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)
    assert f'href="{page_url}"' in html
    assert mock_resolve.call_count == 0


def test_render_text_downloads_an_image_from_an_extensionless_url(mock_resolve):
    # Stepik serves plenty of images from a URL with no extension. Only <a> hrefs are
    # filtered by media type, so an <img> downloads whatever its URL looks like.
    mock_resolve.return_value = "local_image"
    image_url = "https://ucarecdn.stepik.net/some-image-id"
    block = {"text": f'<img src="{image_url}">'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local_image"' in html
    mock_resolve.assert_called_once_with(image_url, "resource_1_some-image-id")


# -- _render_code --------------------------------------------------------------


def test_render_code_basic_case(mock_resolve):
    block = {
        "name": "code",
        "text": "<p>Print the sum of two integers.</p>",
        "options": {
            "samples": [["7 3", "10"]],
            "execution_time_limit": 5,
            "execution_memory_limit": 256,
            "limits": {"python3": {"time": 1, "memory": 128}, "c++": {"time": 2, "memory": 256}},
            "code_templates": {"python3": "print(sum())", "c++": "#include <iostream>"},
        },
    }
    html = _render_code(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Print the sum of two integers." in html
    assert "<pre><code>7 3</code></pre>" in html
    assert "<pre><code>10</code></pre>" in html
    assert "Default limits: 5 s, 256 MB." in html
    assert "<summary>python3 — 1 s, 128 MB</summary>" in html
    assert "<summary>c++ — 2 s, 256 MB</summary>" in html
    # The C++ template's <iostream> becomes the entities &lt;iostream&gt;, so a
    # browser prints it as text instead of parsing it as a tag.
    assert "&lt;iostream&gt;" in html
    assert "<iostream>" not in html
    assert "not available offline" in html


def test_render_code_omits_languages_with_empty_templates(mock_resolve):
    # Stepik lists every language it supports, leaving the template empty where the
    # author wrote none -- rendering those gives toggles that open to nothing.
    block = {
        "name": "code",
        "text": "",
        "options": {"code_templates": {"python3": "print()", "kotlin": "", "swift": "   "}},
    }
    html = _render_code(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "python3" in html
    assert "kotlin" not in html
    assert "swift" not in html


def test_render_code_renders_statement_when_options_are_missing(mock_resolve):
    block = {"name": "code", "text": "<p>Solve the task.</p>"}
    html = _render_code(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Solve the task." in html
    assert "Samples" not in html
    assert "Default limits" not in html
    assert "Starter code" not in html
    assert "not available offline" in html


def test_render_code_rewrites_images_in_the_statement(mock_resolve):
    mock_resolve.return_value = "local.png"
    block = {"name": "code", "text": '<img src="https://cdn.example.com/flowchart.png">', "options": {}}

    html = _render_code(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local.png"' in html
    mock_resolve.assert_called_once_with("https://cdn.example.com/flowchart.png", "resource_1_flowchart.png")


# -- _render_pycharm -----------------------------------------------------------


def test_render_pycharm_basic_case(mock_resolve):
    block = {
        "name": "pycharm",
        "text": "<p>Implement the function.</p>",
        "options": {
            "title": "Exercise 1",
            "description_format": "html",
            "files": [{"name": "src/Task.kt", "text": "fun main() {\n  TODO()\n}", "is_visible": True}],
        },
    }
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Implement the function." in html
    assert "<h3>src/Task.kt</h3>" in html
    assert "TODO()" in html
    assert "hidden" not in html
    assert "not available offline" in html


def test_render_pycharm_converts_a_markdown_statement_to_html(mock_resolve):
    block = {
        "name": "pycharm",
        "text": "## Objects\n\nExamples accompanying the atom.\n\n```kotlin\nfun main() {\n    println(1)\n}\n```",
        "options": {"description_format": "MD"},
    }
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "<h2>Objects</h2>" in html
    assert "<p>Examples accompanying the atom.</p>" in html
    assert '<pre><code class="language-kotlin">fun main() {\n    println(1)\n}\n</code></pre>' in html


def test_render_pycharm_treats_a_null_description_format_as_html(mock_resolve):
    block = {
        "name": "pycharm",
        "text": "<p>Implement the function.</p>",
        "options": {"description_format": None},
    }
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "<p>Implement the function.</p>" in html


def test_render_pycharm_marks_a_file_the_course_hides(mock_resolve):
    block = {
        "name": "pycharm",
        "text": "",
        "options": {
            "files": [
                {"name": "src/Task.kt", "text": "fun main() {}", "is_visible": True},
                {"name": "test/Tests.kt", "text": "class Tests", "is_visible": False},
            ]
        },
    }
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "<h3>src/Task.kt</h3>" in html
    assert '<h3>test/Tests.kt <span class="hidden-file">hidden</span></h3>' in html
    assert "class Tests" in html


def test_render_pycharm_notes_a_file_with_no_content(mock_resolve):
    block = {"name": "pycharm", "text": "", "options": {"files": [{"name": "fizz.kt", "text": ""}]}}
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "<h3>fizz.kt</h3>" in html
    assert "This file is empty." in html
    assert "<pre>" not in html


def test_render_pycharm_renders_a_statement_when_the_step_has_no_files(mock_resolve):
    block = {"name": "pycharm", "text": "<p>Read this.</p>", "options": {"title": "Examples", "files": []}}
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Read this." in html
    assert "Files" not in html
    assert "not available offline" in html


# -- _render_video --------------------------------------------------------------


def test_render_video_links_the_online_video_when_skip_videos_true(mock_resolve):
    html = _render_video(
        block={"video": {"urls": [{"quality": "720", "url": "https://cdn.example.com/lecture.mp4"}]}},
        resolve=mock_resolve,
        log_label="test-context",
        quality="best",
        skip_videos=True,
    )
    assert '<video controls src="https://cdn.example.com/lecture.mp4"></video>' in html
    assert "Video download skipped" in html
    assert mock_resolve.call_count == 0


def test_render_video_returns_warning_when_no_urls(mock_resolve):
    # urls=[] makes _pick_video_url return None, so _render_video returns
    # its "unavailable" warning before ever downloading anything.
    html = _render_video(
        block={"video": {"urls": []}},
        resolve=mock_resolve,
        log_label="test-context",
        quality="best",
        skip_videos=False,
    )
    assert "unavailable" in html.lower()
    assert mock_resolve.call_count == 0


def test_render_video_calls_resolve_with_selected_url_and_returns_video_tag(mock_resolve):
    mock_resolve.return_value = "video.mp4"
    block = {"video": {"urls": [{"quality": "720", "url": "https://cdn.example.com/lecture.mp4"}]}}

    html = _render_video(
        block=block,
        resolve=mock_resolve,
        log_label="test-context",
        quality="best",
        skip_videos=False,
    )

    assert html == '<video controls src="video.mp4"></video>'
    mock_resolve.assert_called_once_with("https://cdn.example.com/lecture.mp4", "video.mp4")


def test_render_video_returns_warning_when_resolve_fails(mock_resolve):
    mock_resolve.return_value = None
    block = {"video": {"urls": [{"quality": "720", "url": "https://cdn.example.com/lecture.mp4"}]}}

    html = _render_video(
        block=block,
        resolve=mock_resolve,
        log_label="test-context",
        quality="best",
        skip_videos=False,
    )
    assert "download failed" in html.lower()


# -- render_step (integration of the above via the real resolve() closure) -----


def _make_step_node(block, step_id=1):
    return {"id": step_id, "title": "Step title", "block": block, "raw": {"id": step_id, "block": block}}


def _render_step_into(step_dir, step_node, **context_overrides):
    context = StepContext(
        course_id=1,
        course_title="Course",
        course_dir=step_dir.parent,
        module_title="Module",
        lesson_id=2,
        lesson_title="Lesson",
        video_quality="best",
        access_token="test-token",
        **context_overrides,
    )
    render_step(step_node, step_dir, context)


def test_render_step_basic_case(tmp_path, mock_download_resource):
    step_dir = tmp_path / "step_01_text"
    block = {"name": "text", "text": "hello"}
    step_node = _make_step_node(block, step_id=42)

    _render_step_into(step_dir, step_node)

    html = (step_dir / "index.html").read_text()
    assert "Step title" in html
    assert "hello" in html
    source = json.loads((step_dir / "source.json").read_text())
    assert source == step_node["raw"]


def test_render_step_dispatches_code_block_to_code_renderer(tmp_path, mock_download_resource, caplog):
    block = {
        "name": "code",
        "text": "<p>Print the sum.</p>",
        "options": {"samples": [["7 3", "10"]], "code_templates": {"python3": "print()"}},
    }
    step_node = _make_step_node(block)
    step_dir = tmp_path / "step"

    _render_step_into(step_dir, step_node)

    html = (step_dir / "index.html").read_text()
    # only _render_code emits this note, so its presence is what proves the dispatch
    assert "asks you to write a program" in html
    assert "Print the sum." in html
    assert "<summary>python3</summary>" in html
    assert "raw step data" not in html
    assert "no dedicated renderer" not in caplog.text


def test_render_step_dispatches_pycharm_block_to_pycharm_renderer(tmp_path, mock_download_resource):
    block = {
        "name": "pycharm",
        "text": "<p>Implement it.</p>",
        "options": {"title": "Exercise 1", "files": [{"name": "src/Task.kt", "text": "fun main() {}"}]},
    }
    step_node = _make_step_node(block)
    step_dir = tmp_path / "step"

    _render_step_into(step_dir, step_node)

    html = (step_dir / "index.html").read_text()
    # only _render_pycharm emits this note, so its presence is what proves the dispatch
    assert "solved in an IDE" in html
    assert "src/Task.kt" in html
    assert "raw step data" not in html


def test_render_step_downloads_a_url_used_by_two_tags_once(tmp_path, mock_download_resource):
    # A picture wrapped in a link to itself names the same URL twice, and downloading
    # it per tag would leave the step holding two copies of one file.
    mock_download_resource.return_value = "local_diagram.png"
    image_url = "https://cdn.example.com/some_diagram.png"
    block = {"name": "text", "text": f'<a href="{image_url}"><img src="{image_url}"></a>'}
    step_dir = tmp_path / "step"

    _render_step_into(step_dir, _make_step_node(block))

    assert mock_download_resource.call_count == 1
    html = (step_dir / "index.html").read_text()
    assert 'href="local_diagram.png"' in html
    assert 'src="local_diagram.png"' in html


def test_render_step_dispatches_unknown_block_type_to_generic_renderer(tmp_path, mock_download_resource):
    block = {"name": "unsupported-block", "custom_field": "custom_value"}
    step_node = _make_step_node(block)
    step_dir = tmp_path / "step"

    _render_step_into(step_dir, step_node)

    html = (step_dir / "index.html").read_text()
    assert "raw step data" in html
