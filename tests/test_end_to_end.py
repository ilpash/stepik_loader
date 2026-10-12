"""
End-to-end tests of export_course.main(), with the Stepik API and all network
downloads mocked: one long basic-case export of a course that covers every
renderer, plus tests for the export options.
"""

import logging
from pathlib import Path

import pytest

import export_course
import resource_downloader
from conftest import MockStepikClient


@pytest.fixture
def course_data():
    """
    Raw Stepik-API-shaped fixture data covering every block type, every way a
    step can be named, and every format variant of the fields that have them.
    Collections vary in size on purpose -- one module holds two lessons and the
    other holds one, and lesson one holds a single step while the others hold
    several -- so each loop is exercised with one entry and with many. Step
    positions are shuffled, so the ordering is proven rather than incidental.
    """
    return {
        "courses": [{"id": 1, "title": "Sample Course", "sections": [10, 11]}],
        "sections": [
            {"id": 10, "title": "Module One", "position": 1, "units": [100, 101]},
            {"id": 11, "title": "Module Two", "position": 2, "units": [102]},
        ],
        "units": [
            {"id": 100, "position": 1, "lesson": 1000},
            {"id": 101, "position": 2, "lesson": 1001},
            {"id": 102, "position": 1, "lesson": 1002},
        ],
        "lessons": [
            {"id": 1000, "title": "Lesson One", "steps": [10000]},
            {"id": 1001, "title": "Lesson Two", "steps": [10001, 10002, 10003, 10004]},
            {"id": 1002, "title": "Lesson Three", "steps": [10005, 10006, 10007, 10008, 10009]},
        ],
        "steps": [
            # text: every resource attribute, every way a url can be written (absolute,
            # root-relative, protocol-relative, and a non-http src that must stay as it
            # is), and both kinds of anchor -- a file to download and a page to keep linked
            {
                "id": 10000,
                "position": 1,
                "block": {
                    "name": "text",
                    "text": (
                        '<img src="http://cdn.example.com/some_picture.png">'
                        '<img src="/media/attachments/lessons/460/some_diagram.png">'
                        '<img src="data:image/png;base64,abc">'
                        '<audio src="http://cdn.example.com/some_audio.mp3"></audio>'
                        '<audio src="//audio.example.com/some_recording.mp3"></audio>'
                        '<video><source src="http://cdn.example.com/some_clip.mp4"></video>'
                        '<a href="http://cdn.example.com/some_notes.pdf">notes</a>'
                        '<a href="/lesson/some-lesson-42/step/3">the next step</a>'
                        '<a href="https://www.youtube.com/watch?v=some_video_id">the lecture</a>'
                    ),
                },
            },
            # choice: the note for a quiz whose items are missing, and multiple answers allowed
            {
                "id": 10002,
                "position": 1,
                "block": {
                    "name": "choice",
                    "text": '<img src="http://cdn.example.com/some_photo.png"><p>Mark every true statement.</p>',
                    "options": {"is_multiple_choice": True},
                },
            },
            # code: several samples, a per-language limit, and a template left empty
            {
                "id": 10001,
                "position": 2,
                "block": {
                    "name": "code",
                    "text": "<p>Print the sum.</p>",
                    "options": {
                        "samples": [["7 3", "10"], ["1 2", "3"]],
                        "execution_time_limit": 5,
                        "execution_memory_limit": 256,
                        "limits": {"python3": {"time": 1, "memory": 128}},
                        "code_templates": {"python3": "print()", "c++": "#include <iostream>", "kotlin": ""},
                    },
                },
            },
            # sorting: the same missing-items note, with no multiple-choice setting at all
            {
                "id": 10003,
                "position": 3,
                "block": {"name": "sorting", "text": "<p>Put these in order.</p>", "options": {}},
            },
            # table: a type with no dedicated renderer, so the generic fallback runs
            {
                "id": 10004,
                "position": 4,
                "block": {"name": "table", "text": "<p>A table step.</p>", "options": {}},
            },
            # video: several qualities, so --video-quality best has something to choose between
            {
                "id": 10005,
                "position": 1,
                "block": {
                    "name": "video",
                    "video": {
                        "urls": [
                            {"quality": "360", "url": "http://cdn.example.com/vid-360.mp4"},
                            {"quality": "1080", "url": "http://cdn.example.com/vid-1080.mp4"},
                            {"quality": "720", "url": "http://cdn.example.com/vid-720.mp4"},
                        ]
                    },
                },
            },
            # pycharm: a markdown statement, and files that are visible, hidden and empty
            {
                "id": 10006,
                "position": 2,
                "block": {
                    "name": "pycharm",
                    "text": "## Objects\n\nExamples accompanying the atom.\n\n```kotlin\nval atom = 42\n```",
                    "options": {
                        "title": "Exercise 1",
                        "description_format": "MD",
                        "files": [
                            {"name": "src/Task.kt", "text": "fun main() {}", "is_visible": True},
                            {"name": "test/Tests.kt", "text": "class Tests", "is_visible": False},
                            {"name": "src/Empty.kt", "text": ""},
                        ],
                    },
                },
            },
            # pycharm: an html statement and no files at all
            {
                "id": 10007,
                "position": 3,
                "block": {
                    "name": "pycharm",
                    "text": "<p>Read this one.</p>",
                    "options": {"title": "Exercise 2", "description_format": "html", "files": []},
                },
            },
            # number: the note for a quiz that expects a typed answer
            {
                "id": 10008,
                "position": 4,
                "block": {
                    "name": "number",
                    "text": "<p>Enter the answer.</p>",
                    "options": {"is_multiple_choice": False},
                },
            },
            # pycharm: a statement with no description format at all
            {
                "id": 10009,
                "position": 5,
                "block": {
                    "name": "pycharm",
                    "text": "<p>Read the last one.</p>",
                    "options": {"title": "Exercise 3"},
                },
            },
        ],
    }


@pytest.fixture
def downloaded_urls(monkeypatch):
    urls = []

    def mock_download_resource(url, dest_dir, log_label, access_token=None, filename_hint=None):
        urls.append(url)
        (Path(dest_dir) / filename_hint).write_bytes(b"placeholder")
        return filename_hint

    monkeypatch.setattr(resource_downloader, "download_resource", mock_download_resource)
    return urls


LESSON_1_STEP_1 = "module_001_module-one/lesson_001_lesson-one/step_001_text"
LESSON_2_STEP_1 = "module_001_module-one/lesson_002_lesson-two/step_001_choice"
LESSON_2_STEP_2 = "module_001_module-one/lesson_002_lesson-two/step_002_code"
LESSON_2_STEP_3 = "module_001_module-one/lesson_002_lesson-two/step_003_sorting"
LESSON_2_STEP_4 = "module_001_module-one/lesson_002_lesson-two/step_004_table"
LESSON_3_STEP_1 = "module_002_module-two/lesson_001_lesson-three/step_001_video"
LESSON_3_STEP_2 = "module_002_module-two/lesson_001_lesson-three/step_002_pycharm"
LESSON_3_STEP_3 = "module_002_module-two/lesson_001_lesson-three/step_003_pycharm"
LESSON_3_STEP_4 = "module_002_module-two/lesson_001_lesson-three/step_004_number"
LESSON_3_STEP_5 = "module_002_module-two/lesson_001_lesson-three/step_005_pycharm"

ALL_STEPS = [
    LESSON_1_STEP_1,
    LESSON_2_STEP_1,
    LESSON_2_STEP_2,
    LESSON_2_STEP_3,
    LESSON_2_STEP_4,
    LESSON_3_STEP_1,
    LESSON_3_STEP_2,
    LESSON_3_STEP_3,
    LESSON_3_STEP_4,
    LESSON_3_STEP_5,
]

ATTACHMENT_FILE = f"{LESSON_1_STEP_1}/resource_6_some_notes.pdf"
VIDEO_FILE = f"{LESSON_3_STEP_1}/video.mp4"

EXPECTED_FILES = {
    "index.html",
    "assets/style.css",
    f"{LESSON_1_STEP_1}/resource_1_some_picture.png",
    f"{LESSON_1_STEP_1}/resource_2_some_diagram.png",
    f"{LESSON_1_STEP_1}/resource_3_some_audio.mp3",
    f"{LESSON_1_STEP_1}/resource_4_some_recording.mp3",
    f"{LESSON_1_STEP_1}/resource_5_some_clip.mp4",
    f"{LESSON_2_STEP_1}/resource_1_some_photo.png",
    ATTACHMENT_FILE,
    VIDEO_FILE,
    *(f"{step}/index.html" for step in ALL_STEPS),
    *(f"{step}/source.json" for step in ALL_STEPS),
}


def _exported_files(course_dir):
    return {path.relative_to(course_dir).as_posix() for path in course_dir.rglob("*") if path.is_file()}


def test_main_exports_full_course_tree_to_disk(tmp_path, monkeypatch, course_data, downloaded_urls, caplog):
    caplog.set_level(logging.INFO, logger="stepik_export")
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])
    assert exit_code == 0
    # The table step is the only one without a dedicated renderer, so it is the one warning.
    assert "Steps exported: 10. Warnings: 1." in caplog.text

    course_dir = tmp_path / "1_sample-course"
    assert _exported_files(course_dir) == EXPECTED_FILES

    # The table of contents links every step, and names each one however that step is named
    toc_html = (course_dir / "index.html").read_text()
    assert "Sample Course" in toc_html
    assert f"{LESSON_1_STEP_1}/index.html" in toc_html
    assert f"{LESSON_2_STEP_1}/index.html" in toc_html
    assert f"{LESSON_2_STEP_2}/index.html" in toc_html
    assert f"{LESSON_2_STEP_3}/index.html" in toc_html
    assert f"{LESSON_2_STEP_4}/index.html" in toc_html
    assert f"{LESSON_3_STEP_1}/index.html" in toc_html
    assert f"{LESSON_3_STEP_2}/index.html" in toc_html
    assert f"{LESSON_3_STEP_3}/index.html" in toc_html
    assert f"{LESSON_3_STEP_4}/index.html" in toc_html
    assert f"{LESSON_3_STEP_5}/index.html" in toc_html
    assert "Step 10000 (text)" in toc_html
    assert "Step 10001 (code)" in toc_html
    assert "Exercise 1" in toc_html
    assert "Exercise 2" in toc_html
    assert "Exercise 3" in toc_html
    assert "Step 10005 (video)" in toc_html

    text_html = (course_dir / LESSON_1_STEP_1 / "index.html").read_text()
    # A step sits three levels below the course root, and both links back must clear it
    assert 'href="../../../assets/style.css"' in text_html
    assert 'href="../../../index.html"' in text_html
    assert 'src="resource_1_some_picture.png"' in text_html
    assert 'src="resource_2_some_diagram.png"' in text_html
    assert 'src="resource_3_some_audio.mp3"' in text_html
    assert 'src="resource_4_some_recording.mp3"' in text_html
    assert 'src="resource_5_some_clip.mp4"' in text_html
    assert 'href="resource_6_some_notes.pdf"' in text_html
    assert 'src="data:image/png;base64,abc"' in text_html
    assert 'href="https://www.youtube.com/watch?v=some_video_id"' in text_html
    assert 'href="https://stepik.org/lesson/some-lesson-42/step/3"' in text_html

    choice_html = (course_dir / LESSON_2_STEP_1 / "index.html").read_text()
    assert "Mark every true statement." in choice_html
    assert 'src="resource_1_some_photo.png"' in choice_html
    assert "asks you to choose an answer" in choice_html
    assert "More than one answer may be correct" in choice_html

    code_html = (course_dir / LESSON_2_STEP_2 / "index.html").read_text()
    assert "asks you to write a program" in code_html
    assert "<pre><code>7 3</code></pre>" in code_html
    assert "<pre><code>3</code></pre>" in code_html
    assert "<summary>python3 — 1 s, 128 MB</summary>" in code_html
    assert "&lt;iostream&gt;" in code_html
    assert "kotlin" not in code_html

    sorting_html = (course_dir / LESSON_2_STEP_3 / "index.html").read_text()
    assert "Put these in order." in sorting_html
    assert "asks you to sort a list" in sorting_html
    assert "More than one answer" not in sorting_html

    table_html = (course_dir / LESSON_2_STEP_4 / "index.html").read_text()
    assert "raw step data" in table_html

    # "best" quality has to pick 1080 out of the three the step offers
    assert "http://cdn.example.com/vid-1080.mp4" in downloaded_urls
    assert "http://cdn.example.com/vid-720.mp4" not in downloaded_urls
    video_html = (course_dir / LESSON_3_STEP_1 / "index.html").read_text()
    assert '<video controls src="video.mp4"></video>' in video_html

    markdown_html = (course_dir / LESSON_3_STEP_2 / "index.html").read_text()
    assert "<h2>Objects</h2>" in markdown_html
    assert '<pre><code class="language-kotlin">val atom = 42\n</code></pre>' in markdown_html
    assert "<h3>src/Task.kt</h3>" in markdown_html
    assert '<h3>test/Tests.kt <span class="hidden-file">hidden</span></h3>' in markdown_html
    assert "This file is empty." in markdown_html
    assert "solved in an IDE" in markdown_html

    pycharm_html = (course_dir / LESSON_3_STEP_3 / "index.html").read_text()
    assert "Read this one." in pycharm_html
    assert "<h2>Files</h2>" not in pycharm_html

    number_html = (course_dir / LESSON_3_STEP_4 / "index.html").read_text()
    assert "expects a typed answer" in number_html

    no_format_html = (course_dir / LESSON_3_STEP_5 / "index.html").read_text()
    assert "<p>Read the last one.</p>" in no_format_html


def test_main_counts_warnings_even_when_the_console_log_level_hides_them(
    tmp_path, monkeypatch, course_data, downloaded_urls, caplog
):
    # Matches a fresh process, which starts with no root handler.
    caplog.set_level(logging.CRITICAL)
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))

    export_course.main(["--course-id", "1", "--output-dir", str(tmp_path), "--log-level", "ERROR"])

    assert export_course.warning_counter.count == 1


def test_main_respects_the_skip_flags(tmp_path, monkeypatch, course_data, downloaded_urls):
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))

    exit_code = export_course.main(
        [
            "--course-id",
            "1",
            "--output-dir",
            str(tmp_path),
            "--skip-videos",
            "--skip-attachments",
        ]
    )
    assert exit_code == 0

    course_dir = tmp_path / "1_sample-course"

    # The <a> (attachment) is skipped entirely, so no local file for it, but
    # the <img> and <audio> are untouched by --skip-attachments and still resolve.
    assert _exported_files(course_dir) == EXPECTED_FILES - {ATTACHMENT_FILE, VIDEO_FILE}

    text_html = (course_dir / LESSON_1_STEP_1 / "index.html").read_text()
    assert 'href="http://cdn.example.com/some_notes.pdf"' in text_html
    assert 'href="https://stepik.org/lesson/some-lesson-42/step/3"' in text_html

    video_html = (course_dir / LESSON_3_STEP_1 / "index.html").read_text()
    assert '<video controls src="http://cdn.example.com/vid-1080.mp4"></video>' in video_html
    assert "Video download skipped" in video_html
    assert downloaded_urls == [
        "http://cdn.example.com/some_picture.png",
        "https://stepik.org/media/attachments/lessons/460/some_diagram.png",
        "http://cdn.example.com/some_audio.mp3",
        "https://audio.example.com/some_recording.mp3",
        "http://cdn.example.com/some_clip.mp4",
        "http://cdn.example.com/some_photo.png",
    ]
