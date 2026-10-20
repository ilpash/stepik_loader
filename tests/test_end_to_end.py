"""
End-to-end tests of export_course.main(), with the Stepik API and all network
downloads mocked: one long basic-case export of a course that covers every
renderer, plus tests for the export options and for a second export into the
same folder.
"""

import io
import logging

import pytest

import export_course
import resource_downloader
from conftest import MockStepikClient


@pytest.fixture
def course_data():
    """
    Raw Stepik-API-shaped fixture data covering every renderer, every way a
    step can be named, and every format variant of the fields that have them.
    Collections vary in size on purpose -- one module holds two lessons and the
    other holds one, and lesson 1.1 holds a single step while the others hold
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
            {"id": 1000, "title": "Lesson 1.1", "steps": [10000]},
            {"id": 1001, "title": "Lesson 1.2", "steps": [10001, 10002, 10003, 10004, 10010, 10012]},
            {"id": 1002, "title": "Lesson 2.1", "steps": [10005, 10006, 10007, 10008, 10009, 10011]},
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
                        '<img src="/media/attachments/lesson/42/some_diagram.png">'
                        '<img src="data:image/png;base64,some_image_data">'
                        '<audio src="http://cdn.example.com/some_audio.mp3"></audio>'
                        '<audio src="//audio.example.com/some_recording.mp3"></audio>'
                        '<video><source src="http://cdn.example.com/some_clip.mp4"></video>'
                        '<a href="http://cdn.example.com/some_notes.pdf">notes</a>'
                        '<a href="https://stepik.org/media/attachments/lesson/42/some_document.docx">the document</a>'
                        '<a href="/lesson/some-lesson-42/step/3">the next step</a>'
                        '<a href="https://www.youtube.com/watch?v=some_video_id">the lecture</a>'
                        '<a rel="nofollow">some contact</a>'
                        '<a href="http://cdn.example.com/some_picture.png">the picture</a>'
                    ),
                },
            },
            # choice: the note for a quiz whose items are missing, and multiple answers allowed
            {
                "id": 10002,
                "position": 1,
                "block": {
                    "name": "choice",
                    "text": (
                        '<img src="http://cdn.example.com/some_photo.png"><p>Mark every true statement.</p>'
                        '<a href="http://cdn.example.com/some_handout.pdf">the handout</a>'
                    ),
                    "options": {"is_multiple_choice": True},
                },
            },
            # code: several samples, a per-language limit, and a template left empty
            {
                "id": 10001,
                "position": 2,
                "block": {
                    "name": "code",
                    "text": (
                        r'<p>Print the sum <span class="math-tex">\( a + b \)</span>.</p>'
                        '<a href="http://cdn.example.com/some_statement.pdf">the statement</a>'
                    ),
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
            # code: a single sample and template, and no default limits
            {
                "id": 10010,
                "position": 5,
                "block": {
                    "name": "code",
                    "text": "<p>Print the double.</p>",
                    "options": {"samples": [["2", "4"]], "code_templates": {"python3": "n = int(input())"}},
                },
            },
            # code: no samples and no starter code
            {
                "id": 10012,
                "position": 6,
                "block": {
                    "name": "code",
                    "text": "<p>Print the answer.</p>",
                    "options": {"samples": [], "code_templates": {"python3": ""}},
                },
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
                    "text": (
                        "## Some Heading\n\nSome text.\n\n```kotlin\nval atom = 42\n```"
                        "\n\n| Input | Output |\n|-------|--------|\n| 1 | 2 |"
                        "\n\nSee [the guide](http://cdn.example.com/some_guide.pdf)."
                    ),
                    "options": {
                        "title": "Some Title",
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
                    "options": {"title": "Another Title", "description_format": "html", "files": []},
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
                    "options": {
                        "title": "A Different Title",
                        "files": [{"name": "src/Main.kt", "text": "fun main() {}"}],
                    },
                },
            },
            # video: a single quality
            {
                "id": 10011,
                "position": 6,
                "block": {
                    "name": "video",
                    "video": {"urls": [{"quality": "720", "url": "http://cdn.example.com/single-quality-720.mp4"}]},
                },
            },
        ],
    }


@pytest.fixture
def downloaded_urls(monkeypatch):
    urls = []

    def mock_download_resource(url, dest_dir, log_label, access_token, filename_hint):
        urls.append(url)
        (dest_dir / filename_hint).write_bytes(b"placeholder")
        return filename_hint

    monkeypatch.setattr(resource_downloader, "download_resource", mock_download_resource)
    return urls


LESSON_1_1_STEP_1 = "module_001_module-one/lesson_001_lesson-1-1/step_001_text"
LESSON_1_2_STEP_1 = "module_001_module-one/lesson_002_lesson-1-2/step_001_choice"
LESSON_1_2_STEP_2 = "module_001_module-one/lesson_002_lesson-1-2/step_002_code"
LESSON_1_2_STEP_3 = "module_001_module-one/lesson_002_lesson-1-2/step_003_sorting"
LESSON_1_2_STEP_4 = "module_001_module-one/lesson_002_lesson-1-2/step_004_table"
LESSON_1_2_STEP_5 = "module_001_module-one/lesson_002_lesson-1-2/step_005_code"
LESSON_1_2_STEP_6 = "module_001_module-one/lesson_002_lesson-1-2/step_006_code"
LESSON_2_1_STEP_1 = "module_002_module-two/lesson_001_lesson-2-1/step_001_video"
LESSON_2_1_STEP_2 = "module_002_module-two/lesson_001_lesson-2-1/step_002_pycharm"
LESSON_2_1_STEP_3 = "module_002_module-two/lesson_001_lesson-2-1/step_003_pycharm"
LESSON_2_1_STEP_4 = "module_002_module-two/lesson_001_lesson-2-1/step_004_number"
LESSON_2_1_STEP_5 = "module_002_module-two/lesson_001_lesson-2-1/step_005_pycharm"
LESSON_2_1_STEP_6 = "module_002_module-two/lesson_001_lesson-2-1/step_006_video"

ALL_STEPS = [
    LESSON_1_1_STEP_1,
    LESSON_1_2_STEP_1,
    LESSON_1_2_STEP_2,
    LESSON_1_2_STEP_3,
    LESSON_1_2_STEP_4,
    LESSON_1_2_STEP_5,
    LESSON_1_2_STEP_6,
    LESSON_2_1_STEP_1,
    LESSON_2_1_STEP_2,
    LESSON_2_1_STEP_3,
    LESSON_2_1_STEP_4,
    LESSON_2_1_STEP_5,
    LESSON_2_1_STEP_6,
]

ATTACHMENT_FILES = {
    f"{LESSON_1_1_STEP_1}/resource_6_some_notes.pdf",
    f"{LESSON_1_1_STEP_1}/resource_7_some_document.docx",
    f"{LESSON_1_2_STEP_1}/resource_2_some_handout.pdf",
    f"{LESSON_1_2_STEP_2}/resource_1_some_statement.pdf",
    f"{LESSON_2_1_STEP_2}/resource_1_some_guide.pdf",
}
VIDEO_FILES = {f"{LESSON_2_1_STEP_1}/video.mp4", f"{LESSON_2_1_STEP_6}/video.mp4"}

EXPECTED_FILES = {
    "index.html",
    "assets/step.html.j2",
    "assets/toc.html.j2",
    "assets/style.css",
    "assets/mathjax/tex-svg-full.js",
    "assets/mathjax/LICENSE",
    f"{LESSON_1_1_STEP_1}/resource_1_some_picture.png",
    f"{LESSON_1_1_STEP_1}/resource_2_some_diagram.png",
    f"{LESSON_1_1_STEP_1}/resource_3_some_audio.mp3",
    f"{LESSON_1_1_STEP_1}/resource_4_some_recording.mp3",
    f"{LESSON_1_1_STEP_1}/resource_5_some_clip.mp4",
    f"{LESSON_1_2_STEP_1}/resource_1_some_photo.png",
    *ATTACHMENT_FILES,
    *VIDEO_FILES,
    *(f"{step}/index.html" for step in ALL_STEPS),
    *(f"{step}/source.json" for step in ALL_STEPS),
}


def _exported_files(course_dir):
    return {path.relative_to(course_dir).as_posix() for path in course_dir.rglob("*") if path.is_file()}


def test_main_basic_case(tmp_path, monkeypatch, course_data, downloaded_urls, caplog, no_dotenv):
    client = MockStepikClient(course_data)
    monkeypatch.setattr(export_course, "StepikClient", lambda: client)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path / "exports")])
    assert exit_code == 0
    assert no_dotenv.call_count == 1
    assert client.get_by_ids_calls[0] == ("courses", [1])
    # The table step is the only one without a dedicated renderer, so it is the one warning.
    assert "INFO Steps exported: 13. Warnings: 1." in caplog.text
    assert (
        "WARNING [course=1 lesson=1001 step=10004] no dedicated renderer for block type 'table', using generic fallback"
        in caplog.text
    )

    course_dir = tmp_path / "exports" / "1_sample-course"
    assert "INFO [1/13] Module One > Lesson 1.1 > step 10000" in caplog.text
    assert f"INFO Done. Open {course_dir / 'index.html'} in a browser." in caplog.text
    assert _exported_files(course_dir) == EXPECTED_FILES

    # The table of contents links every step, and names each one however that step is named
    toc_html = (course_dir / "index.html").read_text()
    assert "Sample Course" in toc_html
    for step in ALL_STEPS:
        assert f"{step}/index.html" in toc_html
    link_positions = [toc_html.index(f"{step}/index.html") for step in ALL_STEPS]
    assert link_positions == sorted(link_positions)
    assert "Step 10000 (text)" in toc_html
    assert "Step 10001 (code)" in toc_html
    assert "Some Title" in toc_html
    assert "Another Title" in toc_html
    assert "A Different Title" in toc_html
    assert "Step 10005 (video)" in toc_html

    text_html = (course_dir / LESSON_1_1_STEP_1 / "index.html").read_text()
    assert "<title>Step 10000 (text) — Sample Course</title>" in text_html
    assert "Module One › Lesson 1.1" in text_html
    # A step sits three levels below the course root, and both links back must clear it
    assert 'href="../../../assets/style.css"' in text_html
    assert 'href="../../../index.html"' in text_html
    assert 'src="resource_1_some_picture.png"' in text_html
    assert 'src="resource_2_some_diagram.png"' in text_html
    assert 'src="resource_3_some_audio.mp3"' in text_html
    assert 'src="resource_4_some_recording.mp3"' in text_html
    assert 'src="resource_5_some_clip.mp4"' in text_html
    assert 'href="resource_6_some_notes.pdf"' in text_html
    assert 'href="resource_7_some_document.docx"' in text_html
    assert 'src="data:image/png;base64,some_image_data"' in text_html
    assert 'href="https://www.youtube.com/watch?v=some_video_id"' in text_html
    assert 'href="https://stepik.org/lesson/some-lesson-42/step/3"' in text_html
    assert '<a rel="nofollow">some contact</a>' in text_html
    assert 'href="resource_1_some_picture.png"' in text_html
    assert downloaded_urls.count("http://cdn.example.com/some_picture.png") == 1
    assert "<script" not in text_html

    choice_html = (course_dir / LESSON_1_2_STEP_1 / "index.html").read_text()
    assert "Mark every true statement." in choice_html
    assert 'src="resource_1_some_photo.png"' in choice_html
    assert "asks you to choose an answer" in choice_html
    assert "More than one answer may be correct" in choice_html

    code_html = (course_dir / LESSON_1_2_STEP_2 / "index.html").read_text()
    assert "asks you to write a program" in code_html
    assert 'src="../../../assets/mathjax/tex-svg-full.js"' in code_html
    assert "<pre><code>7 3</code></pre>" in code_html
    assert "<pre><code>3</code></pre>" in code_html
    assert "<summary>python3 — 1 s, 128 MB</summary>" in code_html
    assert "&lt;iostream&gt;" in code_html
    assert "kotlin" not in code_html

    sorting_html = (course_dir / LESSON_1_2_STEP_3 / "index.html").read_text()
    assert "Put these in order." in sorting_html
    assert "asks you to sort a list" in sorting_html
    assert "More than one answer" not in sorting_html

    table_html = (course_dir / LESSON_1_2_STEP_4 / "index.html").read_text()
    assert "raw step data" in table_html

    single_sample_html = (course_dir / LESSON_1_2_STEP_5 / "index.html").read_text()
    assert "<pre><code>2</code></pre>" in single_sample_html
    assert "<pre><code>4</code></pre>" in single_sample_html
    assert "<summary>python3</summary>" in single_sample_html
    assert "Default limits" not in single_sample_html

    no_samples_html = (course_dir / LESSON_1_2_STEP_6 / "index.html").read_text()
    assert "asks you to write a program" in no_samples_html
    assert "Samples" not in no_samples_html
    assert "Starter code" not in no_samples_html

    # "best" quality has to pick 1080 out of the three the step offers
    assert "http://cdn.example.com/vid-1080.mp4" in downloaded_urls
    assert "http://cdn.example.com/vid-720.mp4" not in downloaded_urls
    video_html = (course_dir / LESSON_2_1_STEP_1 / "index.html").read_text()
    assert '<video controls src="video.mp4"></video>' in video_html

    markdown_html = (course_dir / LESSON_2_1_STEP_2 / "index.html").read_text()
    assert "<title>Some Title — Sample Course</title>" in markdown_html
    assert "Module Two › Lesson 2.1" in markdown_html
    assert "<h2>Some Heading</h2>" in markdown_html
    assert '<pre><code class="language-kotlin">val atom = 42\n</code></pre>' in markdown_html
    assert "<th>Input</th>" in markdown_html
    assert "<h2>Files</h2>" in markdown_html
    assert "<h3>src/Task.kt</h3>" in markdown_html
    assert '<h3>test/Tests.kt <span class="hidden-file">hidden</span></h3>' in markdown_html
    assert "This file is empty." in markdown_html
    assert "solved in an IDE" in markdown_html

    pycharm_html = (course_dir / LESSON_2_1_STEP_3 / "index.html").read_text()
    assert "Read this one." in pycharm_html
    assert "<h2>Files</h2>" not in pycharm_html

    number_html = (course_dir / LESSON_2_1_STEP_4 / "index.html").read_text()
    assert "expects a typed answer" in number_html

    no_format_html = (course_dir / LESSON_2_1_STEP_5 / "index.html").read_text()
    assert "<p>Read the last one.</p>" in no_format_html
    assert "<h3>src/Main.kt</h3>" in no_format_html

    single_quality_html = (course_dir / LESSON_2_1_STEP_6 / "index.html").read_text()
    assert '<video controls src="video.mp4"></video>' in single_quality_html


def test_main_prints_the_log_at_the_chosen_level(tmp_path, monkeypatch, course_data, downloaded_urls):
    console = io.StringIO()
    monkeypatch.setattr(export_course.console_handler, "stream", console)
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))

    export_course.main(["--course-id", "1", "--output-dir", str(tmp_path), "--log-level", "WARNING"])

    assert console.getvalue() == (
        "WARNING [course=1 lesson=1001 step=10004] no dedicated renderer for block type 'table', "
        "using generic fallback\n"
    )


def test_main_counts_warnings_even_when_the_console_log_level_hides_them(
    tmp_path, monkeypatch, course_data, downloaded_urls, caplog
):
    # Raise the root level: the warnings are then counted only if the stepik_export logger sets its own level.
    caplog.set_level(logging.CRITICAL)
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))

    export_course.main(["--course-id", "1", "--output-dir", str(tmp_path), "--log-level", "ERROR"])

    assert export_course.console_handler.level == logging.ERROR
    assert export_course.warning_counter.count == 1


def test_main_downloads_the_requested_video_quality(tmp_path, monkeypatch, course_data, downloaded_urls):
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path), "--video-quality", "720"])

    assert exit_code == 0
    assert "http://cdn.example.com/vid-720.mp4" in downloaded_urls
    assert "http://cdn.example.com/vid-1080.mp4" not in downloaded_urls


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
    assert _exported_files(course_dir) == EXPECTED_FILES - {*ATTACHMENT_FILES, *VIDEO_FILES}

    text_html = (course_dir / LESSON_1_1_STEP_1 / "index.html").read_text()
    assert 'href="http://cdn.example.com/some_notes.pdf"' in text_html
    assert 'href="https://stepik.org/lesson/some-lesson-42/step/3"' in text_html

    video_html = (course_dir / LESSON_2_1_STEP_1 / "index.html").read_text()
    assert '<video controls src="http://cdn.example.com/vid-1080.mp4"></video>' in video_html
    assert "Video download skipped" in video_html
    assert downloaded_urls == [
        "http://cdn.example.com/some_picture.png",
        "https://stepik.org/media/attachments/lesson/42/some_diagram.png",
        "http://cdn.example.com/some_audio.mp3",
        "https://audio.example.com/some_recording.mp3",
        "http://cdn.example.com/some_clip.mp4",
        "http://cdn.example.com/some_photo.png",
    ]


def test_main_overwrites_an_earlier_export(tmp_path, monkeypatch, course_data, downloaded_urls, caplog):
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))
    argv = ["--course-id", "1", "--output-dir", str(tmp_path)]
    export_course.main(argv)
    step_page = tmp_path / "1_sample-course" / LESSON_1_1_STEP_1 / "index.html"
    step_page.write_text("an earlier export")
    caplog.clear()

    exit_code = export_course.main(argv)

    assert exit_code == 0
    assert "INFO Steps exported: 13. Warnings: 1." in caplog.text
    assert "an earlier export" not in step_page.read_text()
