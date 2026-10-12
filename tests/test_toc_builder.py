import pytest

from template_env import TEMPLATES_DIR
from toc_builder import build_toc


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
                "position": 1,
                "title": "Module One",
                "dir_name": "module_001_module-one",
                "lessons": [
                    {
                        "id": 1000,
                        "position": 1,
                        "title": "Lesson One",
                        "dir_name": "lesson_001_lesson-one",
                        "steps": [
                            {
                                "id": 10000,
                                "position": 1,
                                "title": "First Step",
                                "dir_name": "step_001_text",
                                "block": {"name": "text"},
                            },
                            {
                                "id": 10001,
                                "position": 3,
                                "title": "Third Step",
                                "dir_name": "step_003_text",
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
    assert "1. Module One" in html
    assert "1. Lesson One" in html
    assert "1. First Step" in html
    assert "2. " not in html
    assert "3. Third Step" in html

    module = sample_course_tree["modules"][0]
    lesson = module["lessons"][0]
    for step in lesson["steps"]:
        href = f"{module['dir_name']}/{lesson['dir_name']}/{step['dir_name']}/index.html"
        assert href in html
        assert step["title"] in html
