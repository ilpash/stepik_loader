import errno
import os
from unittest.mock import MagicMock, PropertyMock

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


@pytest.mark.parametrize("option", [["--video-quality", "480"], ["--log-level", "TRACE"]])
def test_parse_args_rejects_an_invalid_choice(option):
    with pytest.raises(SystemExit):
        export_course.parse_args(["--course-id", "5", *option])


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


# -- main ----------------------------------------------------------------------


class MockClientWithToken:
    access_token = "mock-token"


@pytest.fixture
def two_step_tree():
    return {
        "id": 1,
        "title": "Sample Course",
        "dir_name": "1_sample-course",
        "modules": [
            {
                "id": 10,
                "position": 1,
                "title": "Module One",
                "dir_name": "module_001_module-one",
                "lessons": [
                    {
                        "id": 1000,
                        "position": 1,
                        "title": "Lesson 1.1",
                        "dir_name": "lesson_001_lesson-1-1",
                        "steps": [
                            {"id": 10000, "position": 1, "title": "First Step", "dir_name": "step_001_text"},
                            {"id": 10001, "position": 2, "title": "Second Step", "dir_name": "step_002_text"},
                        ],
                    }
                ],
            }
        ],
    }


def test_main_stops_when_credentials_are_missing(monkeypatch, caplog):
    def raise_auth_error():
        raise StepikAuthError("STEPIK_CLIENT_ID / STEPIK_CLIENT_SECRET are not set.")

    monkeypatch.setattr(export_course, "StepikClient", raise_auth_error)
    assert export_course.main(["--course-id", "1"]) == 1
    assert "ERROR STEPIK_CLIENT_ID / STEPIK_CLIENT_SECRET are not set." in caplog.text


def test_main_stops_when_the_course_is_not_found(monkeypatch, caplog):
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_not_found_error(client, course_id):
        raise CourseNotFoundError("Stepik returned no course with this id")

    monkeypatch.setattr(export_course, "build_course_tree", raise_not_found_error)
    assert export_course.main(["--course-id", "1"]) == 1
    assert "ERROR Failed to fetch course 1 (Stepik returned no course with this id)" in caplog.text


def test_main_stops_when_credentials_are_rejected_while_fetching(monkeypatch, caplog):
    # StepikClient() only checks that the env vars exist; the token is fetched
    # lazily, so a rejected secret surfaces here rather than at construction.
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_auth_error(client, course_id):
        raise StepikAuthError("Failed to obtain Stepik access token (HTTP 401): invalid_client")

    monkeypatch.setattr(export_course, "build_course_tree", raise_auth_error)
    assert export_course.main(["--course-id", "1"]) == 1
    assert (
        "ERROR Failed to fetch course 1 (Failed to obtain Stepik access token (HTTP 401): invalid_client)"
        in caplog.text
    )


def test_main_stops_when_stepik_cannot_be_reached(monkeypatch, caplog):
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_connection_error(client, course_id):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(export_course, "build_course_tree", raise_connection_error)
    assert export_course.main(["--course-id", "1"]) == 1
    assert "ERROR Failed to fetch course 1 (connection refused)" in caplog.text


def test_main_propagates_unexpected_error_from_fetch_phase(monkeypatch):
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)

    def raise_unexpected_error(client, course_id):
        raise ValueError("unexpected fetch error")

    monkeypatch.setattr(export_course, "build_course_tree", raise_unexpected_error)
    with pytest.raises(ValueError, match="unexpected fetch error"):
        export_course.main(["--course-id", "1"])


def test_main_warns_when_the_course_has_no_steps(tmp_path, monkeypatch, caplog):
    empty_tree = {"id": 1, "title": "Sample Course", "dir_name": "1_sample-course", "modules": []}
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: empty_tree)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert "WARNING Course 1 has no steps to export." in caplog.text


def test_main_skips_a_step_it_cannot_write(tmp_path, monkeypatch, caplog, two_step_tree):
    write_error = OSError(errno.EACCES, "Permission denied")
    mock_render_step = MagicMock(side_effect=[write_error, None])
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert mock_render_step.call_count == 2
    assert (
        f"WARNING [course=1 lesson=1000 step=10000] could not write the step, skipping it: {write_error}" in caplog.text
    )
    assert "INFO Steps exported: 1. Warnings: 1." in caplog.text
    toc_html = (tmp_path / "1_sample-course" / "index.html").read_text()
    assert "1. First Step (not exported)" in toc_html


@pytest.mark.parametrize("error_code", [errno.ENOSPC, errno.EDQUOT])
def test_main_stops_when_the_disk_is_full(error_code, tmp_path, monkeypatch, caplog, two_step_tree):
    disk_error = OSError(error_code, os.strerror(error_code))
    mock_render_step = MagicMock(side_effect=disk_error)
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert mock_render_step.call_count == 1
    assert f"ERROR The disk is full, stopping the export: {disk_error}" in caplog.text
    assert not (tmp_path / "1_sample-course" / "index.html").exists()


def test_main_stops_when_the_export_folder_cannot_be_created(tmp_path, monkeypatch, caplog, two_step_tree):
    not_a_folder = tmp_path / "not_a_folder.txt"
    not_a_folder.write_text("")
    mock_copy_assets = MagicMock()
    mock_render_step = MagicMock()
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "copy_assets", mock_copy_assets)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(not_a_folder)])

    assert exit_code == 1
    assert mock_copy_assets.call_count == 0
    assert mock_render_step.call_count == 0
    assert "ERROR Could not create the export folder, stopping the export" in caplog.text


def test_main_stops_when_the_assets_cannot_be_copied(tmp_path, monkeypatch, caplog, two_step_tree):
    copy_error = OSError(errno.ENOSPC, "No space left on device")
    mock_copy_assets = MagicMock(side_effect=copy_error)
    mock_render_step = MagicMock()
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "copy_assets", mock_copy_assets)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert mock_copy_assets.call_count == 1
    assert mock_render_step.call_count == 0
    assert f"ERROR Could not copy the page assets, stopping the export: {copy_error}" in caplog.text


def test_main_stops_when_the_table_of_contents_cannot_be_written(tmp_path, monkeypatch, caplog, two_step_tree):
    toc_error = OSError(errno.ENOSPC, "No space left on device")
    mock_build_toc = MagicMock(side_effect=toc_error)
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", MagicMock())
    monkeypatch.setattr(export_course, "build_toc", mock_build_toc)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert mock_build_toc.call_count == 1
    assert f"ERROR Could not write the table of contents, stopping the export: {toc_error}" in caplog.text


def test_main_gives_every_step_the_current_access_token(tmp_path, monkeypatch, two_step_tree):
    mock_access_token = PropertyMock(side_effect=["first-token", "second-token"])
    mock_render_step = MagicMock()
    monkeypatch.setattr(MockClientWithToken, "access_token", mock_access_token)
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    contexts = [render_call.args[2] for render_call in mock_render_step.call_args_list]
    assert [context.access_token for context in contexts] == ["first-token", "second-token"]


@pytest.mark.parametrize(
    "token_error",
    [
        StepikAuthError("Failed to obtain Stepik access token after 5 attempts: connection refused"),
        requests.JSONDecodeError("Expecting value", "<html>", 0),
    ],
)
def test_main_stops_when_the_token_cannot_be_refreshed(token_error, tmp_path, monkeypatch, caplog, two_step_tree):
    mock_access_token = PropertyMock(side_effect=["mock-token", token_error])
    mock_render_step = MagicMock()
    monkeypatch.setattr(MockClientWithToken, "access_token", mock_access_token)
    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", mock_render_step)

    exit_code = export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert mock_render_step.call_count == 1
    assert f"ERROR Could not refresh the Stepik access token, stopping the export: {token_error}" in caplog.text
    assert not (tmp_path / "1_sample-course" / "index.html").exists()


def test_main_propagates_unexpected_error_from_render_phase(tmp_path, monkeypatch, two_step_tree):
    # Fetch failures and disk errors are handled; any other render-phase error propagates as-is.
    def raise_render_error(step_node, step_dir, context):
        raise RuntimeError("unexpected render error")

    monkeypatch.setattr(export_course, "StepikClient", MockClientWithToken)
    monkeypatch.setattr(export_course, "build_course_tree", lambda client, course_id: two_step_tree)
    monkeypatch.setattr(export_course, "render_step", raise_render_error)

    with pytest.raises(RuntimeError, match="unexpected render error"):
        export_course.main(["--course-id", "1", "--output-dir", str(tmp_path)])
