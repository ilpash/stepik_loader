import pytest

from toc_builder import TEMPLATES_DIR, build_toc


@pytest.fixture
def sample_course_tree():
    """
    A fixed nested dict matching build_course_tree's output shape.
    """
    return {
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
                                "block": {"name": "text"},
                            },
                            {
                                "id": 10001,
                                "dir_name": "step_002_text",
                                "block": {"name": "text"},
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_build_toc_creates_assets_dir_and_copies_style_css(tmp_path, sample_course_tree):
    build_toc(sample_course_tree, tmp_path)

    copied_css = (tmp_path / "assets" / "style.css").read_text()
    original_css = (TEMPLATES_DIR / "style.css").read_text()
    assert copied_css == original_css


def test_build_toc_writes_index_html_with_course_title_and_modules(tmp_path, sample_course_tree):
    build_toc(sample_course_tree, tmp_path)

    html = (tmp_path / "index.html").read_text()
    assert "Sample Course" in html

    module = sample_course_tree["modules"][0]
    lesson = module["lessons"][0]
    for step in lesson["steps"]:
        href = f"{module['dir_name']}/{lesson['dir_name']}/{step['dir_name']}/index.html"
        assert href in html


def test_build_toc_step_title_falls_back_to_dir_name_when_title_missing(tmp_path, sample_course_tree):
    # None of the sample steps have a "title" key, so the fallback (dir_name) must be used.
    build_toc(sample_course_tree, tmp_path)

    html = (tmp_path / "index.html").read_text()
    step = sample_course_tree["modules"][0]["lessons"][0]["steps"][0]
    assert step["dir_name"] in html
