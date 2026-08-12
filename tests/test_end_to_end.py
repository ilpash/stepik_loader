"""
One full-pipeline smoke test: export_course.main() end to end, with the
Stepik API and all network downloads mocked, proving the whole tree-build ->
render -> TOC pipeline actually produces a correct offline folder on disk.
"""

from pathlib import Path

import pytest

import export_course
import resource_downloader
from conftest import MockStepikClient


@pytest.fixture
def course_data():
    """
    Raw Stepik-API-shaped fixture data covering every block type, every way a
    step can be named, and both format variants of the fields that have them.
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
            {"id": 1002, "title": "Lesson Three", "steps": [10005, 10006, 10007, 10008]},
        ],
        "steps": [
            # text: every resource attribute plus a non-http src that must be left alone
            {
                "id": 10000,
                "position": 1,
                "block": {
                    "name": "text",
                    "text": (
                        '<img src="http://cdn.example.com/pic.png">'
                        '<img src="data:image/png;base64,abc">'
                        '<audio src="http://cdn.example.com/clip.mp3"></audio>'
                        '<a href="http://cdn.example.com/notes.pdf">notes</a>'
                    ),
                },
            },
            # choice: the note for a quiz whose items are missing, and multiple answers allowed
            {
                "id": 10002,
                "position": 1,
                "block": {
                    "name": "choice",
                    "text": "<p>Mark every true statement.</p>",
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
                    "text": "## Objects\n\nExamples accompanying the atom.",
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
        ],
    }


@pytest.fixture
def downloaded_urls(monkeypatch):
    """Records every URL the export asks for, and writes a placeholder file for it."""
    urls = []

    def mock_download_resource(url, dest_dir, context, access_token=None, filename_hint=None):
        urls.append(url)
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = filename_hint or "placeholder"
        (dest_dir / filename).write_bytes(b"placeholder")
        return filename

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


def test_main_exports_full_course_tree_to_disk(tmp_path, monkeypatch, course_data, downloaded_urls):
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])
    assert exit_code == 0

    course_dir = tmp_path / "1_sample-course"
    expected_files = {
        "index.html",
        "assets/style.css",
        f"{LESSON_1_STEP_1}/index.html",
        f"{LESSON_1_STEP_1}/source.json",
        f"{LESSON_1_STEP_1}/resource_1_pic.png",
        f"{LESSON_1_STEP_1}/resource_2_clip.mp3",
        f"{LESSON_1_STEP_1}/resource_3_notes.pdf",
        f"{LESSON_2_STEP_1}/index.html",
        f"{LESSON_2_STEP_1}/source.json",
        f"{LESSON_2_STEP_2}/index.html",
        f"{LESSON_2_STEP_2}/source.json",
        f"{LESSON_2_STEP_3}/index.html",
        f"{LESSON_2_STEP_3}/source.json",
        f"{LESSON_2_STEP_4}/index.html",
        f"{LESSON_2_STEP_4}/source.json",
        f"{LESSON_3_STEP_1}/index.html",
        f"{LESSON_3_STEP_1}/source.json",
        f"{LESSON_3_STEP_1}/video.mp4",
        f"{LESSON_3_STEP_2}/index.html",
        f"{LESSON_3_STEP_2}/source.json",
        f"{LESSON_3_STEP_3}/index.html",
        f"{LESSON_3_STEP_3}/source.json",
        f"{LESSON_3_STEP_4}/index.html",
        f"{LESSON_3_STEP_4}/source.json",
    }
    actual_files = {p.relative_to(course_dir).as_posix() for p in course_dir.rglob("*") if p.is_file()}
    assert actual_files == expected_files

    # the table of contents links every step, and names each one however that step is named
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
    assert "Step 10000 (text)" in toc_html
    assert "Step 10001 (code)" in toc_html
    assert "Exercise 1" in toc_html
    assert "Exercise 2" in toc_html
    assert "Step 10005 (video)" in toc_html

    text_html = (course_dir / LESSON_1_STEP_1 / "index.html").read_text()
    assert 'src="resource_1_pic.png"' in text_html
    assert 'src="resource_2_clip.mp3"' in text_html
    assert 'href="resource_3_notes.pdf"' in text_html
    assert 'src="data:image/png;base64,abc"' in text_html

    choice_html = (course_dir / LESSON_2_STEP_1 / "index.html").read_text()
    assert "Mark every true statement." in choice_html
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
    assert "<h3>src/Task.kt</h3>" in markdown_html
    assert '<h3>test/Tests.kt <span class="hidden-file">hidden</span></h3>' in markdown_html
    assert "This file is empty." in markdown_html
    assert "solved in an IDE" in markdown_html

    pycharm_html = (course_dir / LESSON_3_STEP_3 / "index.html").read_text()
    assert "Read this one." in pycharm_html
    assert "<h2>Files</h2>" not in pycharm_html

    number_html = (course_dir / LESSON_3_STEP_4 / "index.html").read_text()
    assert "expects a typed answer" in number_html


def test_main_respects_skip_videos_and_skip_attachments_flags(tmp_path, monkeypatch, course_data, downloaded_urls):
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
    expected_files = {
        "index.html",
        "assets/style.css",
        f"{LESSON_1_STEP_1}/index.html",
        f"{LESSON_1_STEP_1}/source.json",
        f"{LESSON_1_STEP_1}/resource_1_pic.png",
        f"{LESSON_1_STEP_1}/resource_2_clip.mp3",
        f"{LESSON_2_STEP_1}/index.html",
        f"{LESSON_2_STEP_1}/source.json",
        f"{LESSON_2_STEP_2}/index.html",
        f"{LESSON_2_STEP_2}/source.json",
        f"{LESSON_2_STEP_3}/index.html",
        f"{LESSON_2_STEP_3}/source.json",
        f"{LESSON_2_STEP_4}/index.html",
        f"{LESSON_2_STEP_4}/source.json",
        f"{LESSON_3_STEP_1}/index.html",
        f"{LESSON_3_STEP_1}/source.json",
        f"{LESSON_3_STEP_2}/index.html",
        f"{LESSON_3_STEP_2}/source.json",
        f"{LESSON_3_STEP_3}/index.html",
        f"{LESSON_3_STEP_3}/source.json",
        f"{LESSON_3_STEP_4}/index.html",
        f"{LESSON_3_STEP_4}/source.json",
    }
    actual_files = {p.relative_to(course_dir).as_posix() for p in course_dir.rglob("*") if p.is_file()}
    assert actual_files == expected_files

    text_html = (course_dir / LESSON_1_STEP_1 / "index.html").read_text()
    assert 'href="http://cdn.example.com/notes.pdf"' in text_html

    video_html = (course_dir / LESSON_3_STEP_1 / "index.html").read_text()
    assert "Video download skipped" in video_html
    assert downloaded_urls == ["http://cdn.example.com/pic.png", "http://cdn.example.com/clip.mp3"]
