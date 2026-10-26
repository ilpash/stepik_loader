import pytest

from conftest import MockStepikClient
from course_tree import CourseAccessError, CourseNotFoundError, _dir_name, build_course_tree


@pytest.fixture
def minimal_mock_client_data():
    return {
        "courses": [{"id": 1, "title": "Tiny Course", "sections": [10]}],
        "sections": [{"id": 10, "title": "Only Module", "position": 1, "units": [100]}],
        "units": [{"id": 100, "position": 1, "lesson": 1000}],
        "lessons": [{"id": 1000, "title": "Only Lesson", "steps": [10000]}],
        "steps": [{"id": 10000, "position": 1, "block": {"name": "text", "text": "hi"}}],
    }


@pytest.fixture
def mock_client_data():
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
            {"id": 1000, "title": "Lesson 1.1", "steps": [10000]},
            {"id": 1001, "title": "Lesson 2.1", "steps": [10001]},
            {"id": 1002, "title": "Lesson 2.2", "steps": [10002, 10003]},
        ],
        "steps": [
            {"id": 10000, "position": 1, "block": {"name": "text", "text": "hello"}},
            {"id": 10001, "position": 1, "block": {"name": "video", "video": {"urls": []}}},
            {"id": 10002, "position": 1, "block": {"name": "text", "text": "step one"}},
            {
                "id": 10003,
                "position": 2,
                "block": {"name": "pycharm", "text": "step two", "options": {"title": "Some Title"}},
            },
        ],
    }


# -- _dir_name -----------------------------------------------------------------


def test_dir_name_basic_case():
    assert _dir_name("module_", 3, "Hello World!") == "module_003_hello-world"


def test_dir_name_falls_back_to_untitled_without_a_usable_title():
    assert _dir_name("lesson_", 1, "") == "lesson_001_untitled"
    assert _dir_name("lesson_", 1, "!!!") == "lesson_001_untitled"


def test_dir_name_transliterates_cyrillic_title():
    # Many Stepik course/lesson titles use Cyrillic script, and dir_name
    # must still come out as a plain ASCII, filesystem-safe slug.
    assert _dir_name("lesson_", 2, "Некоторое Название") == "lesson_002_nekotoroe-nazvanie"


def test_dir_name_truncates_slug_to_max_length():
    # Cut at MAX_SLUG_LEN = 50 characters, right after the tenth "word-", and slugify drops that last "-".
    assert _dir_name("lesson_", 1, "word " * 30) == "lesson_001_" + "word-" * 9 + "word"


# -- build_course_tree ---------------------------------------------------------


def test_build_course_tree_basic_case(mock_client_data):
    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    expected = {
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
                            {
                                "id": 10000,
                                "position": 1,
                                "title": "Step 10000 (text)",
                                "dir_name": "step_001_text",
                                "block_type": "text",
                                "block": {"name": "text", "text": "hello"},
                                "raw": {"id": 10000, "position": 1, "block": {"name": "text", "text": "hello"}},
                            },
                        ],
                    },
                ],
            },
            {
                "id": 11,
                "position": 2,
                "title": "Module Two",
                "dir_name": "module_002_module-two",
                "lessons": [
                    {
                        "id": 1001,
                        "position": 1,
                        "title": "Lesson 2.1",
                        "dir_name": "lesson_001_lesson-2-1",
                        "steps": [
                            {
                                "id": 10001,
                                "position": 1,
                                "title": "Step 10001 (video)",
                                "dir_name": "step_001_video",
                                "block_type": "video",
                                "block": {"name": "video", "video": {"urls": []}},
                                "raw": {"id": 10001, "position": 1, "block": {"name": "video", "video": {"urls": []}}},
                            },
                        ],
                    },
                    {
                        "id": 1002,
                        "position": 2,
                        "title": "Lesson 2.2",
                        "dir_name": "lesson_002_lesson-2-2",
                        "steps": [
                            {
                                "id": 10002,
                                "position": 1,
                                "title": "Step 10002 (text)",
                                "dir_name": "step_001_text",
                                "block_type": "text",
                                "block": {"name": "text", "text": "step one"},
                                "raw": {"id": 10002, "position": 1, "block": {"name": "text", "text": "step one"}},
                            },
                            {
                                "id": 10003,
                                "position": 2,
                                "title": "Some Title",
                                "dir_name": "step_002_pycharm",
                                "block_type": "pycharm",
                                "block": {"name": "pycharm", "text": "step two", "options": {"title": "Some Title"}},
                                "raw": {
                                    "id": 10003,
                                    "position": 2,
                                    "block": {
                                        "name": "pycharm",
                                        "text": "step two",
                                        "options": {"title": "Some Title"},
                                    },
                                },
                            },
                        ],
                    },
                ],
            },
        ],
    }
    assert tree == expected

    expected_calls = [
        ("courses", [1]),
        ("sections", [10, 11]),
        ("units", [100, 101, 102]),
        ("lessons", [1000, 1001, 1002]),
        ("steps", [10000, 10001, 10002, 10003]),
    ]
    assert client.get_by_ids_calls == expected_calls


def test_build_course_tree_sorts_by_position(mock_client_data):
    # Feed every level out of position order. Each expected order below is descending
    # by id, so neither insertion order nor sorting by id would produce it.
    mock_client_data["sections"][0]["position"] = 2
    mock_client_data["sections"][1]["position"] = 1
    mock_client_data["units"][1]["position"] = 2
    mock_client_data["units"][2]["position"] = 1
    mock_client_data["steps"][2]["position"] = 2
    mock_client_data["steps"][3]["position"] = 1

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    assert [module["id"] for module in tree["modules"]] == [11, 10]
    module_two = tree["modules"][0]
    assert [lesson["id"] for lesson in module_two["lessons"]] == [1002, 1001]
    assert [step["id"] for step in module_two["lessons"][0]["steps"]] == [10003, 10002]


def test_build_course_tree_skips_an_unresolved_section(mock_client_data, caplog):
    # The course's first section id is absent from the sections the API returned.
    mock_client_data["courses"][0]["sections"] = [99999, 11]

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    assert [module["dir_name"] for module in tree["modules"]] == ["module_002_module-two"]
    assert "WARNING course 1 references section 99999 which could not be resolved, skipping" in caplog.text


def test_build_course_tree_skips_an_unresolved_unit(mock_client_data, caplog):
    # Module Two's first unit id is absent from the units the API returned.
    mock_client_data["sections"][1]["units"] = [99999, 102]

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    assert [lesson["dir_name"] for lesson in tree["modules"][1]["lessons"]] == ["lesson_002_lesson-2-2"]
    assert "WARNING section 11 references unit 99999 which could not be resolved, skipping" in caplog.text


def test_build_course_tree_skips_an_unresolved_lesson(mock_client_data, caplog):
    # Unit 101 points at a lesson id that doesn't exist in the lessons list.
    mock_client_data["units"][1]["lesson"] = 99999

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    assert [lesson["dir_name"] for lesson in tree["modules"][1]["lessons"]] == ["lesson_002_lesson-2-2"]
    assert "WARNING unit 101 (section 11) references lesson 99999 which could not be resolved, skipping" in caplog.text


def test_build_course_tree_skips_an_unresolved_step(mock_client_data, caplog):
    # Lesson 2.2's first step id is absent from the steps the API returned.
    mock_client_data["lessons"][2]["steps"] = [99999, 10003]

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    assert [step["dir_name"] for step in tree["modules"][1]["lessons"][1]["steps"]] == ["step_002_pycharm"]
    assert "WARNING lesson 1002 references step 99999 which could not be resolved, skipping" in caplog.text


def test_build_course_tree_warns_about_a_lesson_it_cannot_open(mock_client_data, caplog):
    # Lesson 2.1 comes back the way Stepik sends a lesson your account can't open.
    mock_client_data["lessons"][1]["steps"] = []
    mock_client_data["lessons"][1]["actions"] = {}

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    lesson = tree["modules"][1]["lessons"][0]
    assert lesson["dir_name"] == "lesson_001_lesson-2-1"
    assert lesson["steps"] == []
    assert "WARNING your Stepik account has no access to lesson 1001, skipping its steps" in caplog.text


def test_build_course_tree_raises_when_no_lesson_can_be_opened(mock_client_data):
    # Every lesson comes back the way Stepik sends a lesson your account can't open.
    for lesson in mock_client_data["lessons"]:
        lesson["steps"] = []
        lesson["actions"] = {}

    client = MockStepikClient(mock_client_data)
    with pytest.raises(CourseAccessError, match="your Stepik account has no access to its lessons"):
        build_course_tree(client, 1)


def test_build_course_tree_accepts_a_course_whose_lessons_are_empty(mock_client_data, caplog):
    # Every lesson is one your account can open, but whose author added no steps.
    for lesson in mock_client_data["lessons"]:
        lesson["steps"] = []
        lesson["actions"] = {"learn_lesson": "#"}

    client = MockStepikClient(mock_client_data)
    tree = build_course_tree(client, 1)

    lessons = [lesson for module in tree["modules"] for lesson in module["lessons"]]
    assert [lesson["steps"] for lesson in lessons] == [[], [], []]
    assert not caplog.text


def test_build_course_tree_accepts_a_course_with_no_lessons(caplog):
    client = MockStepikClient(
        {
            "courses": [{"id": 1, "title": "Sample Course", "sections": []}],
            "sections": [],
            "units": [],
            "lessons": [],
            "steps": [],
        }
    )
    tree = build_course_tree(client, 1)

    assert tree["modules"] == []
    assert not caplog.text


def test_build_course_tree_truncates_course_slug(minimal_mock_client_data):
    minimal_mock_client_data["courses"][0]["title"] = "word " * 30

    client = MockStepikClient(minimal_mock_client_data)
    tree = build_course_tree(client, 1)

    # Cut at MAX_SLUG_LEN = 50 characters, right after the tenth "word-", and slugify drops that last "-".
    assert tree["dir_name"] == "1_" + "word-" * 9 + "word"


def test_build_course_tree_keeps_sort_order_for_a_large_lesson(minimal_mock_client_data):
    # dir_name must sort correctly in a plain directory listing even for a
    # lesson with a large number of steps.
    step_ids = list(range(20000, 20000 + 210))
    minimal_mock_client_data["lessons"][0]["steps"] = step_ids
    minimal_mock_client_data["steps"] = [
        {"id": step_id, "position": position, "block": {"name": "text", "text": "a step"}}
        for position, step_id in enumerate(step_ids, start=1)
    ]

    client = MockStepikClient(minimal_mock_client_data)
    tree = build_course_tree(client, 1)
    steps = tree["modules"][0]["lessons"][0]["steps"]

    assert steps[0]["dir_name"] == "step_001_text"
    assert steps[104]["dir_name"] == "step_105_text"
    assert steps[-1]["dir_name"] == "step_210_text"
    dir_names = [step["dir_name"] for step in steps]
    assert dir_names == sorted(dir_names)


def test_build_course_tree_raises_when_course_not_found():
    client = MockStepikClient({"courses": []})
    with pytest.raises(CourseNotFoundError, match="Stepik returned no course with this id"):
        build_course_tree(client, 1)
