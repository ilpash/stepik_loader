import pytest

from conftest import MockStepikClient
from course_tree import MAX_SLUG_LEN, _dir_name, build_course_tree


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
    assert _dir_name(3, "Hello World!") == "003_hello-world"


def test_dir_name_applies_prefix():
    assert _dir_name(1, "Intro", prefix="module_") == "module_001_intro"


def test_dir_name_falls_back_to_untitled_when_title_missing():
    assert _dir_name(1, None) == "001_untitled"


def test_dir_name_transliterates_cyrillic_title():
    # Many Stepik course/lesson titles use Cyrillic script, and dir_name
    # must still come out as a plain ASCII, filesystem-safe slug.
    assert _dir_name(2, "Алгоритмы и Структуры Данных") == "002_algoritmy-i-struktury-dannykh"


def test_dir_name_truncates_slug_to_max_length():
    long_title = "word " * 30
    slug = _dir_name(1, long_title).split("_", 1)[1]
    assert len(slug) <= MAX_SLUG_LEN


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
                "dir_name": "module_001_only-module",
                "lessons": [
                    {
                        "id": 1000,
                        "title": "Only Lesson",
                        "dir_name": "lesson_001_only-lesson",
                        "steps": [
                            {
                                "id": 10000,
                                "dir_name": "step_001_text",
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
                "dir_name": "module_001_module-one",
                "lessons": [
                    {
                        "id": 1000,
                        "title": "Lesson One",
                        "dir_name": "lesson_001_lesson-one",
                        "steps": [
                            {
                                "id": 10000,
                                "dir_name": "step_001_text",
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
                "dir_name": "module_002_module-two",
                "lessons": [
                    {
                        "id": 1001,
                        "title": "Lesson Two",
                        "dir_name": "lesson_001_lesson-two",
                        "steps": [
                            {
                                "id": 10001,
                                "dir_name": "step_001_video",
                                "block": {"name": "video", "video": {"urls": []}},
                                "raw": {"id": 10001, "position": 1, "block": {"name": "video", "video": {"urls": []}}},
                            },
                        ],
                    },
                    {
                        "id": 1002,
                        "title": "Lesson Three",
                        "dir_name": "lesson_002_lesson-three",
                        "steps": [
                            {
                                "id": 10002,
                                "dir_name": "step_001_text",
                                "block": {"name": "text", "text": "step one"},
                                "raw": {"id": 10002, "position": 1, "block": {"name": "text", "text": "step one"}},
                            },
                            {
                                "id": 10003,
                                "dir_name": "step_002_text",
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


def test_build_course_tree_logs_warning_when_lesson_not_found(mock_client_data, caplog):
    mock_client_data["units"][0]["lesson"] = 99999

    client = MockStepikClient(mock_client_data)
    build_course_tree(client, 1)

    assert "could not be resolved" in caplog.text


def test_build_course_tree_logs_warning_when_step_not_found(mock_client_data, caplog):
    mock_client_data["lessons"][0]["steps"] = [99999]

    client = MockStepikClient(mock_client_data)
    build_course_tree(client, 1)

    assert "could not be resolved" in caplog.text


def test_build_course_tree_truncates_course_slug(minimal_mock_client_data):
    minimal_mock_client_data["courses"][0]["title"] = "word " * 30

    client = MockStepikClient(minimal_mock_client_data)
    tree = build_course_tree(client, 1)

    slug = tree["dir_name"].split("_", 1)[1]
    assert len(slug) <= MAX_SLUG_LEN


def test_build_course_tree_keeps_sort_order_for_a_large_lesson(minimal_mock_client_data):
    # dir_name must sort correctly in a plain directory listing even for a
    # lesson with a large number of steps.
    step_ids = list(range(20000, 20000 + 210))
    minimal_mock_client_data["lessons"][0]["steps"] = step_ids
    minimal_mock_client_data["steps"] = [
        {"id": sid, "position": i, "block": {"name": "text", "text": "x"}} for i, sid in enumerate(step_ids, start=1)
    ]

    client = MockStepikClient(minimal_mock_client_data)
    tree = build_course_tree(client, 1)
    steps = tree["modules"][0]["lessons"][0]["steps"]

    assert steps[0]["dir_name"] == "step_001_text"
    assert steps[104]["dir_name"] == "step_105_text"
    assert steps[-1]["dir_name"] == "step_210_text"
    dir_names = [s["dir_name"] for s in steps]
    assert dir_names == sorted(dir_names)


def test_build_course_tree_raises_when_course_not_found():
    client = MockStepikClient({"courses": []})
    with pytest.raises(ValueError):
        build_course_tree(client, 1)
