import pytest

from conftest import MockStepikClient
from course_tree import _dir_name, build_course_tree


@pytest.fixture
def minimal_mock_client_data():
    """
    Raw Stepik-API-shaped fixture data for the minimal case: exactly one
    module, one lesson, one step.
    """
    return {
        "courses": [{"id": 1, "title": "Tiny Course", "sections": [10]}],
        "sections": [{"id": 10, "title": "Only Module", "position": 1, "units": [100]}],
        "units": [{"id": 100, "position": 1, "lesson": 1000}],
        "lessons": [{"id": 1000, "title": "Only Lesson", "steps": [10000]}],
        "steps": [{"id": 10000, "position": 1, "block": {"name": "text", "text": "hi"}}],
    }


@pytest.fixture
def mock_client_data():
    """
    Raw Stepik-API-shaped fixture data for a course with two modules: one
    with a single lesson (one step), and one with two lessons (one step
    and two steps, respectively).
    """
    return {
        "courses": [{"id": 1, "title": "Sample Course", "sections": [10, 11]}],
        "sections": [
            {"id": 10, "title": "Module One", "position": 1, "units": [100]},
            {"id": 11, "title": "Module Two", "position": 2, "units": [101, 102]},
        ],
        "units": [
            {"id": 100, "position": 1, "lesson": 1000},
            {"id": 101, "position": 1, "lesson": 1001},
            {"id": 102, "position": 2, "lesson": 1002},
        ],
        "lessons": [
            {"id": 1000, "title": "Lesson One", "steps": [10000]},
            {"id": 1001, "title": "Lesson Two", "steps": [10001]},
            {"id": 1002, "title": "Lesson Three", "steps": [10002, 10003]},
        ],
        "steps": [
            {"id": 10000, "position": 1, "block": {"name": "text", "text": "hello"}},
            {"id": 10001, "position": 1, "block": {"name": "video", "video": {"urls": []}}},
            {"id": 10002, "position": 1, "block": {"name": "text", "text": "step one"}},
            {"id": 10003, "position": 2, "block": {"name": "text", "text": "step two"}},
        ],
    }


def test_dir_name_pads_index_and_slugifies_title():
    assert _dir_name(3, "Hello World!") == "03_hello-world"


def test_dir_name_applies_prefix():
    assert _dir_name(1, "Intro", prefix="module_") == "module_01_intro"


def test_dir_name_falls_back_to_untitled_when_title_missing():
    assert _dir_name(1, None) == "01_untitled"


def test_dir_name_transliterates_cyrillic_title():
    # Many Stepik course/lesson titles use Cyrillic script, and dir_name
    # must still come out as a plain ASCII, filesystem-safe slug.
    assert _dir_name(2, "Алгоритмы и Структуры Данных") == "02_algoritmy-i-struktury-dannykh"


def test_build_course_tree_handles_single_module_lesson_and_step(minimal_mock_client_data):
    client = MockStepikClient(minimal_mock_client_data)
    tree = build_course_tree(client, 1)

    expected = {
        "id": 1,
        "title": "Tiny Course",
        "dir_name": "1_tiny-course",
        "modules": [
            {
                "id": 10,
                "title": "Only Module",
                "dir_name": "module_01_only-module",
                "lessons": [
                    {
                        "id": 1000,
                        "title": "Only Lesson",
                        "dir_name": "lesson_01_only-lesson",
                        "steps": [
                            {
                                "id": 10000,
                                "dir_name": "step_01_text",
                                "block": {"name": "text", "text": "hi"},
                                "raw": {"id": 10000, "position": 1, "block": {"name": "text", "text": "hi"}},
                            },
                        ],
                    },
                ],
            },
        ],
    }
    assert tree == expected


def test_build_course_tree_happy_path(mock_client_data):
    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    expected = {
        "id": 1,
        "title": "Sample Course",
        "dir_name": "1_sample-course",
        "modules": [
            {
                "id": 10,
                "title": "Module One",
                "dir_name": "module_01_module-one",
                "lessons": [
                    {
                        "id": 1000,
                        "title": "Lesson One",
                        "dir_name": "lesson_01_lesson-one",
                        "steps": [
                            {
                                "id": 10000,
                                "dir_name": "step_01_text",
                                "block": {"name": "text", "text": "hello"},
                                "raw": {"id": 10000, "position": 1, "block": {"name": "text", "text": "hello"}},
                            },
                        ],
                    },
                ],
            },
            {
                "id": 11,
                "title": "Module Two",
                "dir_name": "module_02_module-two",
                "lessons": [
                    {
                        "id": 1001,
                        "title": "Lesson Two",
                        "dir_name": "lesson_01_lesson-two",
                        "steps": [
                            {
                                "id": 10001,
                                "dir_name": "step_01_video",
                                "block": {"name": "video", "video": {"urls": []}},
                                "raw": {"id": 10001, "position": 1, "block": {"name": "video", "video": {"urls": []}}},
                            },
                        ],
                    },
                    {
                        "id": 1002,
                        "title": "Lesson Three",
                        "dir_name": "lesson_02_lesson-three",
                        "steps": [
                            {
                                "id": 10002,
                                "dir_name": "step_01_text",
                                "block": {"name": "text", "text": "step one"},
                                "raw": {"id": 10002, "position": 1, "block": {"name": "text", "text": "step one"}},
                            },
                            {
                                "id": 10003,
                                "dir_name": "step_02_text",
                                "block": {"name": "text", "text": "step two"},
                                "raw": {"id": 10003, "position": 2, "block": {"name": "text", "text": "step two"}},
                            },
                        ],
                    },
                ],
            },
        ],
    }
    assert tree == expected


def test_build_course_tree_sorts_by_position(mock_client_data):
    # Feed sections out of position order; tree should still come out ascending.
    mock_client_data["sections"][0]["position"] = 2
    mock_client_data["sections"][1]["position"] = 1

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    assert [m["title"] for m in tree["modules"]] == ["Module Two", "Module One"]


def test_build_course_tree_skips_lesson_not_found(mock_client_data):
    # Unit 100 points at a lesson id that doesn't exist in the lessons list.
    mock_client_data["units"][0]["lesson"] = 99999

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    module_one = tree["modules"][0]
    assert module_one["lessons"] == []


def test_build_course_tree_raises_when_course_not_found():
    client = MockStepikClient({"courses": []})
    with pytest.raises(ValueError):
        build_course_tree(client, 1)
