import pytest

import export_course
from stepik_client import StepikAuthError

# -- parse_args ---------------------------------------------------------------


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


def test_parse_args_parses_flags_and_overrides():
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


# -- main error paths ------------------------------------------------------------


def test_main_returns_1_when_auth_fails(monkeypatch):
    def raise_auth_error(*args, **kwargs):
        raise StepikAuthError("no creds")

    monkeypatch.setattr(export_course, "StepikClient", raise_auth_error)
    assert export_course.main(["--course-id", "1"]) == 1


def test_main_returns_1_when_course_fetch_fails(monkeypatch):
    monkeypatch.setattr(export_course, "StepikClient", object)

    def raise_fetch_error(client, course_id):
        raise ValueError("course not found or not accessible")

    monkeypatch.setattr(export_course, "build_course_tree", raise_fetch_error)
    assert export_course.main(["--course-id", "1"]) == 1


def test_main_propagates_unexpected_error_from_render_phase(tmp_path, monkeypatch):
    # Only fetch failures are caught and turned into exit code 1; render-phase errors propagate as-is.
    class StubClientWithToken:
        access_token = "mock-token"

    tree = {
        "id": 1,
        "title": "Course",
        "dir_name": "1_course",
        "modules": [
            {
                "dir_name": "module_01_m",
                "title": "Module",
                "lessons": [
                    {
                        "id": 1000,
                        "dir_name": "lesson_01_l",
                        "title": "Lesson",
                        "steps": [{"id": 10000, "dir_name": "step_01_text"}],
                    }
                ],
            }
        ],
    }

    def mock_build_course_tree(client, course_id):
        return tree

    def raise_render_error(*args, **kwargs):
        raise RuntimeError("disk write failed")

    monkeypatch.setattr(export_course, "StepikClient", StubClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", mock_build_course_tree)
    monkeypatch.setattr(export_course, "render_step", raise_render_error)

    with pytest.raises(RuntimeError, match="disk write failed"):
        export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])
