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
    Raw Stepik-API-shaped fixture data for a course with two modules: one
    text step (with an embedded image) and one video step.
    """
    return {
        "courses": [{"id": 1, "title": "Sample Course", "sections": [10, 11]}],
        "sections": [
            {"id": 10, "title": "Module One", "position": 1, "units": [100]},
            {"id": 11, "title": "Module Two", "position": 2, "units": [101]},
        ],
        "units": [
            {"id": 100, "position": 1, "lesson": 1000},
            {"id": 101, "position": 1, "lesson": 1001},
        ],
        "lessons": [
            {"id": 1000, "title": "Lesson One", "steps": [10000]},
            {"id": 1001, "title": "Lesson Two", "steps": [10001]},
        ],
        "steps": [
            {
                "id": 10000,
                "position": 1,
                "block": {
                    "name": "text",
                    "title": "Intro",
                    "text": (
                        '<img src="http://cdn.example.com/pic.png">'
                        '<a href="http://cdn.example.com/notes.pdf">notes</a>'
                    ),
                },
            },
            {
                "id": 10001,
                "position": 1,
                "block": {
                    "name": "video",
                    "title": "Demo Video",
                    "video": {"urls": [{"quality": "720", "url": "http://cdn.example.com/vid.mp4"}]},
                },
            },
        ],
    }


def mock_download_resource(url, dest_dir, context, access_token=None, filename_hint=None):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = filename_hint or "placeholder"
    (dest_dir / filename).write_bytes(b"placeholder")
    return filename


def test_main_exports_full_course_tree_to_disk(tmp_path, monkeypatch, course_data):
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))
    monkeypatch.setattr(resource_downloader, "download_resource", mock_download_resource)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])
    assert exit_code == 0

    course_dir = tmp_path / "1_sample-course"
    step1_dir = "module_01_module-one/lesson_01_lesson-one/step_01_text"
    step2_dir = "module_02_module-two/lesson_01_lesson-two/step_01_video"
    expected_files = {
        "index.html",
        "assets/style.css",
        f"{step1_dir}/index.html",
        f"{step1_dir}/source.json",
        f"{step1_dir}/resource_1_pic.png",
        f"{step1_dir}/resource_2_notes.pdf",
        f"{step2_dir}/index.html",
        f"{step2_dir}/source.json",
        f"{step2_dir}/video.mp4",
    }
    actual_files = {p.relative_to(course_dir).as_posix() for p in course_dir.rglob("*") if p.is_file()}
    assert actual_files == expected_files

    toc_html = (course_dir / "index.html").read_text()
    assert "Sample Course" in toc_html
    assert f"{step1_dir}/index.html" in toc_html
    assert f"{step2_dir}/index.html" in toc_html


def test_main_respects_skip_videos_and_skip_attachments_flags(tmp_path, monkeypatch, course_data):
    monkeypatch.setattr(export_course, "StepikClient", lambda: MockStepikClient(course_data))
    monkeypatch.setattr(resource_downloader, "download_resource", mock_download_resource)

    exit_code = export_course.main([
        "--course-id", "1", "--output-dir", str(tmp_path),
        "--skip-videos", "--skip-attachments",
    ])
    assert exit_code == 0

    course_dir = tmp_path / "1_sample-course"
    step1_dir = "module_01_module-one/lesson_01_lesson-one/step_01_text"
    step2_dir = "module_02_module-two/lesson_01_lesson-two/step_01_video"

    # The <a> (attachment) is skipped entirely, so no local file for it, but
    # the <img> is untouched by --skip-attachments and still resolves.
    expected_files = {
        "index.html",
        "assets/style.css",
        f"{step1_dir}/index.html",
        f"{step1_dir}/source.json",
        f"{step1_dir}/resource_1_pic.png",
        f"{step2_dir}/index.html",
        f"{step2_dir}/source.json",
    }
    actual_files = {p.relative_to(course_dir).as_posix() for p in course_dir.rglob("*") if p.is_file()}
    assert actual_files == expected_files

    step1_html = (course_dir / step1_dir / "index.html").read_text()
    assert 'href="http://cdn.example.com/notes.pdf"' in step1_html

    step2_html = (course_dir / step2_dir / "index.html").read_text()
    assert "Video download skipped" in step2_html
