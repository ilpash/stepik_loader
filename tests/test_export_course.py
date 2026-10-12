import errno
import logging
from unittest.mock import MagicMock

import pytest
import requests

import export_course
from course_tree import CourseNotFoundError
from stepik_client import StepikAuthError

# -- parse_args ----------------------------------------------------------------


def test_parse_args_requires_course_id():
    with pytest.raises(SystemExit):
        export_course.parse_args([])


def test_parse_args_applies_defaults():
    args = export_course.parse_args(["--course-id", "5"])
    assert args.course_id == 5
    assert args.output_dir == "exports"
    assert args.video_quality == "best"
    assert args.skip_videos is False
    assert args.skip_attachments is False
    assert args.log_level == "INFO"


def test_parse_args_rejects_invalid_video_quality():
    with pytest.raises(SystemExit):
        export_course.parse_args(["--course-id", "5", "--video-quality", "480"])


def test_parse_args_reads_every_option():
    args = export_course.parse_args(
        [
            "--course-id",
            "9",
            "--output-dir",
            "out",
            "--video-quality",
            "720",
            "--skip-videos",
            "--skip-attachments",
            "--log-level",
            "DEBUG",
        ]
    )
    assert args.course_id == 9
    assert args.output_dir == "out"
    assert args.video_quality == "720"
    assert args.skip_videos is True
    assert args.skip_attachments is True
    assert args.log_level == "DEBUG"


# -- main error paths ----------------------------------------------------------


class MockClientWithToken:
    access_token = "mock-token"


def test_main_returns_1_when_auth_fails(monkeypatch):
    def raise_auth_error(*args, **kwargs):
        raise StepikAuthError("no creds")

    monkeypatch.setattr(export_course, "StepikClient", raise_auth_error)
    assert export_course.main(["--course-id", "1"]) == 1


def test_main_returns_1_when_course_fetch_fails(monkeypatch):
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_fetch_error(client, course_id):
        raise CourseNotFoundError("course not found or not accessible")

    monkeypatch.setattr(export_course, "build_course_tree", raise_fetch_error)
    assert export_course.main(["--course-id", "1"]) == 1


def test_main_returns_1_when_credentials_are_rejected_while_fetching(monkeypatch):
    # StepikClient() only checks that the env vars exist; the token is fetched
    # lazily, so a rejected secret surfaces here rather than at construction.
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_auth_error(client, course_id):
        raise StepikAuthError("HTTP 401 from https://stepik.org/oauth2/token/")

    monkeypatch.setattr(export_course, "build_course_tree", raise_auth_error)
    assert export_course.main(["--course-id", "1"]) == 1


def test_main_returns_1_when_stepik_cannot_be_reached(monkeypatch):
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_connection_error(client, course_id):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(export_course, "build_course_tree", raise_connection_error)
    assert export_course.main(["--course-id", "1"]) == 1


def test_main_propagates_unexpected_error_from_fetch_phase(monkeypatch):
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_unexpected_error(client, course_id):
        raise ValueError("unexpected fetch error")

    monkeypatch.setattr(export_course, "build_course_tree", raise_unexpected_error)
    with pytest.raises(ValueError, match="unexpected fetch error"):
        export_course.main(["--course-id", "1"])


def test_main_warns_when_the_course_has_no_steps(tmp_path, monkeypatch, caplog):
    empty_tree = {"id": 1, "title": "Course", "dir_name": "1_course", "modules": []}
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: empty_tree)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert "has no steps to export" in caplog.text


@pytest.fixture
def two_step_tree():
    return {
        "id": 1,
        "title": "Course",
        "dir_name": "1_course",
        "modules": [
            {
                "id": 10,
                "position": 1,
                "title": "Module",
                "dir_name": "module_001_module",
                "lessons": [
                    {
                        "id": 1000,
                        "position": 1,
                        "title": "Lesson",
                        "dir_name": "lesson_001_lesson",
                        "steps": [
                            {"id": 10000, "position": 1, "title": "First step", "dir_name": "step_001_text"},
                            {"id": 10001, "position": 2, "title": "Second step", "dir_name": "step_002_text"},
                        ],
                    }
                ],
            }
        ],
    }


def test_main_skips_a_step_it_cannot_write(tmp_path, monkeypatch, caplog, two_step_tree):
    caplog.set_level(logging.INFO, logger="stepik_export")
    mock_render_step = MagicMock(side_effect=[OSError(errno.EACCES, "Permission denied"), None])
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert mock_render_step.call_count == 2
    assert "could not write the step, skipping it" in caplog.text
    assert "Steps exported: 1. Warnings: 1." in caplog.text
    toc_html = (tmp_path / "1_course" / "index.html").read_text()
    assert "1. First step (not exported)" in toc_html


def test_main_stops_when_the_disk_is_full(tmp_path, monkeypatch, caplog, two_step_tree):
    mock_render_step = MagicMock(side_effect=OSError(errno.ENOSPC, "No space left on device"))
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert mock_render_step.call_count == 1
    assert "The disk is full, stopping the export" in caplog.text
    assert not (tmp_path / "1_course" / "index.html").exists()


def test_main_propagates_unexpected_error_from_render_phase(tmp_path, monkeypatch, two_step_tree):
    # Fetch failures and disk errors are handled; any other render-phase error propagates as-is.
    def raise_render_error(*args, **kwargs):
        raise RuntimeError("unexpected render error")

    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", raise_render_error)

    with pytest.raises(RuntimeError, match="unexpected render error"):
        export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])
