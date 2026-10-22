import json
from unittest.mock import MagicMock

import pytest

import resource_downloader
from step_renderer import (
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


@pytest.fixture
def mock_download_resource(monkeypatch):
    mock_download = MagicMock(return_value="local_resource")
    monkeypatch.setattr(resource_downloader, "download_resource", mock_download)
    return mock_download


# -- _render_text --------------------------------------------------------------


def test_render_text_basic_case(mock_resolve):
    mock_resolve.return_value = "local.png"
    block = {"text": '<img src="https://cdn.example.com/diagram.png">'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local.png"' in html
    mock_resolve.assert_called_once_with("https://cdn.example.com/diagram.png", "resource_1_diagram.png")


def test_render_text_skips_non_http_src(mock_resolve):
    block = {"text": '<img src="data:image/png;base64,some_image_data">'}
    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "data:image/png;base64,some_image_data" in html
    assert mock_resolve.call_count == 0


def test_render_text_skips_anchor_tags_when_skip_attachments_true(mock_resolve):
    block = {"text": '<a href="https://cdn.example.com/handout.pdf">link</a>'}
    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=True)
    assert 'href="https://cdn.example.com/handout.pdf"' in html
    assert mock_resolve.call_count == 0


def test_render_text_downloads_an_image_from_a_root_relative_url(mock_resolve):
    # Stepik writes its own media root-relative, which resolves against file:// offline.
    mock_resolve.return_value = "local_photo.jpg"
    block = {"text": '<img src="/media/attachments/lesson/42/some_photo.jpg">'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local_photo.jpg"' in html
    mock_resolve.assert_called_once_with(
        "https://stepik.org/media/attachments/lesson/42/some_photo.jpg", "resource_1_some_photo.jpg"
    )


def test_render_text_keeps_the_absolute_url_when_a_download_fails(mock_resolve):
    mock_resolve.return_value = None
    block = {"text": '<img src="/media/attachments/lesson/42/some_photo.jpg">'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="https://stepik.org/media/attachments/lesson/42/some_photo.jpg"' in html


def test_render_text_downloads_audio_from_a_protocol_relative_url(mock_resolve):
    mock_resolve.return_value = "local_recording.mp3"
    block = {"text": '<audio src="//audio.example.com/some_recording.mp3"></audio>'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'src="local_recording.mp3"' in html
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
    attachment_url = "https://cdn.example.com/notes.pdf"
    block = {"text": f'<a href="{attachment_url}">notes</a>'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'href="local_notes.pdf"' in html
    mock_resolve.assert_called_once_with(attachment_url, "resource_1_notes.pdf")


def test_render_text_downloads_a_stepik_attachment_of_an_unknown_type(mock_resolve):
    mock_resolve.return_value = "local_document.docx"
    attachment_url = "https://stepik.org/media/attachments/lesson/42/some_document.docx"
    block = {"text": f'<a href="{attachment_url}">the document</a>'}

    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)

    assert 'href="local_document.docx"' in html
    mock_resolve.assert_called_once_with(attachment_url, "resource_1_some_document.docx")


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


def test_render_text_keeps_an_anchor_without_a_link(mock_resolve):
    block = {"text": '<a rel="nofollow">some contact</a>'}
    html = _render_text(block=block, resolve=mock_resolve, skip_attachments=False)
    assert html == '<a rel="nofollow">some contact</a>'
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


# -- _pick_video_url -----------------------------------------------------------


def _video_url(quality):
    return {"quality": quality, "url": f"https://cdn.example.com/lecture-{quality}.mp4"}


def test_pick_video_url_basic_case(caplog):
    urls = [_video_url("360"), _video_url("720"), _video_url("1080")]
    assert _pick_video_url(urls, "720", "test-log-label") == _video_url("720")
    assert "not available" not in caplog.text


def test_pick_video_url_returns_none_for_empty_list():
    assert _pick_video_url([], "best", "test-log-label") is None


def test_pick_video_url_best_picks_highest_quality():
    urls = [_video_url("360"), _video_url("1080"), _video_url("720")]
    assert _pick_video_url(urls, "best", "test-log-label") == _video_url("1080")


def test_pick_video_url_falls_back_to_nearest_when_exact_missing(caplog):
    # 720 falls between 480 and 1080, nearer to 480 (240 away) than 1080 (360 away).
    urls = [_video_url("360"), _video_url("480"), _video_url("1080")]
    result = _pick_video_url(urls, "720", "test-log-label")
    assert result == _video_url("480")
    assert "WARNING [test-log-label] requested video quality 720 not available, using 480 instead" in caplog.text


@pytest.mark.parametrize("unreadable_quality", [None, "unknown"])
@pytest.mark.parametrize("requested", ["best", "360"])
def test_pick_video_url_skips_an_entry_with_an_unreadable_quality(requested, unreadable_quality):
    urls = [_video_url(unreadable_quality), _video_url("1080")]
    result = _pick_video_url(urls, requested, "test-log-label")
    assert result == _video_url("1080")


# -- _render_video -------------------------------------------------------------


def test_render_video_basic_case(mock_resolve):
    mock_resolve.return_value = "video.mp4"
    block = {"video": {"urls": [{"quality": "720", "url": "https://cdn.example.com/lecture.mp4"}]}}

    html = _render_video(
        block=block,
        resolve=mock_resolve,
        log_label="test-log-label",
        video_quality="best",
        skip_videos=False,
    )

    assert html == '<video controls src="video.mp4"></video>'
    mock_resolve.assert_called_once_with("https://cdn.example.com/lecture.mp4", "video.mp4")


def test_render_video_links_the_online_video_when_skip_videos_true(mock_resolve):
    video_url = "https://cdn.example.com/lecture.mp4?expires=some_time&signature=some_signature"
    html = _render_video(
        block={"video": {"urls": [{"quality": "720", "url": video_url}]}},
        resolve=mock_resolve,
        log_label="test-log-label",
        video_quality="best",
        skip_videos=True,
    )
    assert 'src="https://cdn.example.com/lecture.mp4?expires=some_time&amp;signature=some_signature"' in html
    assert "Video download skipped" in html
    assert mock_resolve.call_count == 0


def test_render_video_returns_warning_when_no_urls(mock_resolve, caplog):
    # urls=[] makes _pick_video_url return None, so _render_video returns
    # its "unavailable" warning before ever downloading anything.
    html = _render_video(
        block={"video": {"urls": []}},
        resolve=mock_resolve,
        log_label="test-log-label",
        video_quality="best",
        skip_videos=False,
    )
    assert "Video unavailable" in html
    assert mock_resolve.call_count == 0
    assert "WARNING [test-log-label] video step has no downloadable URLs" in caplog.text


def test_render_video_returns_warning_when_the_entry_has_no_url(mock_resolve, caplog):
    html = _render_video(
        block={"video": {"urls": [{"quality": "720"}]}},
        resolve=mock_resolve,
        log_label="test-log-label",
        video_quality="best",
        skip_videos=False,
    )
    assert "Video unavailable" in html
    assert mock_resolve.call_count == 0
    assert "WARNING [test-log-label] video step has no downloadable URLs" in caplog.text


def test_render_video_links_the_online_video_when_the_download_fails(mock_resolve):
    mock_resolve.return_value = None
    block = {"video": {"urls": [{"quality": "720", "url": "https://cdn.example.com/lecture.mp4"}]}}

    html = _render_video(
        block=block,
        resolve=mock_resolve,
        log_label="test-log-label",
        video_quality="best",
        skip_videos=False,
    )
    assert '<video controls src="https://cdn.example.com/lecture.mp4"></video>' in html
    assert "Video download failed" in html


# -- _render_quiz --------------------------------------------------------------


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


@pytest.mark.parametrize(
    ("block_type", "note"),
    [
        ("choice", "asks you to choose an answer"),
        ("sorting", "asks you to sort a list"),
        ("matching", "asks you to match pairs"),
        ("string", "expects a typed answer"),
        ("number", "expects a typed answer"),
        ("free-answer", "expects a typed answer"),
    ],
)
def test_render_quiz_basic_case_for_every_quiz_type(block_type, note, mock_resolve):
    block = {"name": block_type, "text": "The question", "options": {}}
    html = _render_quiz(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "The question" in html
    assert note in html


def test_render_quiz_omits_multiple_answer_note_for_single_choice(mock_resolve):
    block = {"name": "choice", "text": "Pick one", "options": {"is_multiple_choice": False}}
    html = _render_quiz(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "More than one answer" not in html


# -- _render_code --------------------------------------------------------------


def test_render_code_basic_case(mock_resolve):
    block = {
        "name": "code",
        "text": "<p>Swap the sides of the comparison.</p>",
        "options": {
            "samples": [["7 < 9", "9 > 7"]],
            "execution_time_limit": 5,
            "execution_memory_limit": 256,
            "limits": {"python3": {"time": 1, "memory": 128}, "c++": {"time": 2, "memory": 256}},
            "code_templates": {"python3": "line = input()", "c++": "#include <iostream>"},
        },
    }
    html = _render_code(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Swap the sides of the comparison." in html
    assert "<h2>Samples</h2>" in html
    assert "<pre><code>7 &lt; 9</code></pre>" in html
    assert "<pre><code>9 &gt; 7</code></pre>" in html
    assert "Default limits: 5 s, 256 MB." in html
    assert "<h2>Starter code</h2>" in html
    assert "<summary>python3 — 1 s, 128 MB</summary>" in html
    assert "<summary>c++ — 2 s, 256 MB</summary>" in html
    assert html.index("<summary>c++") < html.index("<summary>python3")
    # The C++ template's <iostream> becomes the entities &lt;iostream&gt;, so a
    # browser prints it as text instead of parsing it as a tag.
    assert "<pre><code>#include &lt;iostream&gt;</code></pre></details>" in html
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
            "title": "Some Title",
            "description_format": "html",
            "files": [
                {
                    "name": "src/Task.kt",
                    "text": "fun main() {\n  val numbers = listOf<Int>()\n  TODO()\n}",
                    "is_visible": True,
                }
            ],
        },
    }
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Implement the function." in html
    assert "<h2>Files</h2>" in html
    assert "<h3>src/Task.kt</h3>" in html
    assert "<pre><code>fun main() {\n  val numbers = listOf&lt;Int&gt;()\n  TODO()\n}</code></pre>" in html
    assert "hidden" not in html
    assert "not available offline" in html


@pytest.mark.parametrize("description_format", ["MD", "md"])
def test_render_pycharm_converts_a_markdown_statement_to_html(description_format, mock_resolve):
    block = {
        "name": "pycharm",
        "text": (
            "## Some Heading\n\nSome text.\n\n```kotlin\nfun main() {\n    println(1)\n}\n```"
            "\n\n| Input | Output |\n|-------|--------|\n| 1 | 2 |"
        ),
        "options": {"description_format": description_format},
    }
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "<h2>Some Heading</h2>" in html
    assert "<p>Some text.</p>" in html
    assert '<pre><code class="language-kotlin">fun main() {\n    println(1)\n}\n</code></pre>' in html
    assert "<th>Input</th>" in html


@pytest.mark.parametrize(
    "options", [{}, {"description_format": None}, {"description_format": "html"}, {"description_format": "HTML"}]
)
def test_render_pycharm_treats_any_other_description_format_as_html(options, mock_resolve):
    block = {"name": "pycharm", "text": "## Some Heading", "options": options}
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "## Some Heading" in html


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


@pytest.mark.parametrize("file_text", ["", "\n"])
def test_render_pycharm_notes_a_file_with_no_content(file_text, mock_resolve):
    block = {"name": "pycharm", "text": "", "options": {"files": [{"name": "src/Empty.kt", "text": file_text}]}}
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "<h3>src/Empty.kt</h3>" in html
    assert "This file is empty." in html
    assert "<pre>" not in html


def test_render_pycharm_renders_a_statement_when_the_step_has_no_files(mock_resolve):
    block = {"name": "pycharm", "text": "<p>Read this.</p>", "options": {"title": "Some Title", "files": []}}
    html = _render_pycharm(block=block, resolve=mock_resolve, skip_attachments=False)
    assert "Read this." in html
    assert "Files" not in html
    assert "not available offline" in html


# -- _render_generic -----------------------------------------------------------


def test_render_generic_basic_case(caplog):
    block = {"name": "unknown-type", "text": "<p>Привет</p>", "custom_field": "custom_value"}
    html = _render_generic(block, "test-log-label")
    assert "<pre><code>" in html
    assert "&quot;custom_field&quot;" in html
    assert "Привет" in html
    assert (
        "WARNING [test-log-label] no dedicated renderer for block type 'unknown-type', using generic fallback"
        in caplog.text
    )


# -- render_step ---------------------------------------------------------------


def _make_step_node(block, step_id=1):
    return {
        "id": step_id,
        "title": "Some Title",
        "block_type": block["name"],
        "block": block,
        "raw": {"id": step_id, "block": block},
    }


def _render_step_into(step_dir, step_node):
    context = StepContext(
        course_id=1,
        course_title="Sample Course",
        course_dir=step_dir.parent,
        module_title="Module One",
        lesson_id=2,
        lesson_title="Lesson 1.1",
        video_quality="best",
        access_token="test-token",
        skip_videos=False,
        skip_attachments=False,
    )
    render_step(step_node, step_dir, context)


def test_render_step_basic_case(tmp_path, mock_download_resource):
    step_dir = tmp_path / "step"
    image_url = "https://cdn.example.com/some_picture.png"
    block = {"name": "text", "text": f'<p>Привет</p><img src="{image_url}">'}
    step_node = _make_step_node(block, step_id=42)

    _render_step_into(step_dir, step_node)

    html = (step_dir / "index.html").read_text()
    assert '<meta charset="utf-8">' in html
    assert "<title>Some Title — Sample Course</title>" in html
    assert "<script" not in html
    assert '<a href="../index.html">Sample Course</a>' in html
    assert "Module One › Lesson 1.1" in html
    assert '<span class="block-type">text</span>' in html
    assert "<h1>Some Title</h1>" in html
    assert "Привет" in html
    assert 'src="local_resource"' in html
    # Every other renderer adds a note to this block, so its absence is what proves the dispatch
    assert 'class="warning"' not in html
    mock_download_resource.assert_called_once_with(
        image_url,
        step_dir,
        "course=1 lesson=2 step=42",
        access_token="test-token",
        filename_hint="resource_1_some_picture.png",
    )
    source = (step_dir / "source.json").read_text()
    assert json.loads(source) == step_node["raw"]
    assert "Привет" in source


def test_render_step_escapes_html_in_the_title(tmp_path, mock_download_resource):
    step_dir = tmp_path / "step"
    step_node = {**_make_step_node({"name": "text", "text": "hello"}), "title": "<script>some_script()</script>"}

    _render_step_into(step_dir, step_node)

    html = (step_dir / "index.html").read_text()
    assert "<h1>&lt;script&gt;some_script()&lt;/script&gt;</h1>" in html
    assert "<script>" not in html


def test_render_step_loads_mathjax_on_a_page_with_a_formula(tmp_path, mock_download_resource):
    step_dir = tmp_path / "step"
    formula = r'<span class="math-tex">\( 1 \le n \)</span>'
    block = {"name": "text", "text": f"<p>The input holds {formula} numbers.</p>"}

    _render_step_into(step_dir, _make_step_node(block))

    html = (step_dir / "index.html").read_text()
    assert '<script id="MathJax-script" async src="../assets/mathjax/tex-svg-full.js"></script>' in html
    assert formula in html


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
    # Only _render_code emits this note, so its presence is what proves the dispatch
    assert "asks you to write a program" in html
    assert "Print the sum." in html
    assert "<summary>python3</summary>" in html
    assert "raw step data" not in html
    assert "no dedicated renderer" not in caplog.text


def test_render_step_dispatches_pycharm_block_to_pycharm_renderer(tmp_path, mock_download_resource):
    block = {
        "name": "pycharm",
        "text": "<p>Implement it.</p>",
        "options": {"title": "Some Title", "files": [{"name": "src/Task.kt", "text": "fun main() {}"}]},
    }
    step_node = _make_step_node(block)
    step_dir = tmp_path / "step"

    _render_step_into(step_dir, step_node)

    html = (step_dir / "index.html").read_text()
    # Only _render_pycharm emits this note, so its presence is what proves the dispatch
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
