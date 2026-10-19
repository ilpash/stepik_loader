import pytest

import toc_builder
from template_env import ASSETS_DIR
from toc_builder import build_toc


@pytest.fixture
def sample_course_tree():
    """
    The shape build_course_tree returns, with only the keys build_toc reads.
    """
    return {
        "id": 1,
        "title": "Sample Course",
        "modules": [
            {
                "position": 1,
                "title": "Module One",
                "dir_name": "module_001_module-one",
                "lessons": [
                    {
                        "position": 1,
                        "title": "Lesson One",
                        "dir_name": "lesson_001_lesson-one",
                        "steps": [
                            {
                                "id": 10000,
                                "position": 1,
                                "title": "First Step",
                                "dir_name": "step_001_text",
                            },
                            {
                                "id": 10001,
                                "position": 3,
                                "title": "Third Step",
                                "dir_name": "step_003_text",
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_build_toc_basic_case(tmp_path, sample_course_tree):
    build_toc(sample_course_tree, tmp_path, set())

    html = (tmp_path / "index.html").read_text()
    assert '<meta charset="utf-8">' in html
    assert "<title>Sample Course</title>" in html
    assert "<h1>Sample Course</h1>" in html
    assert "Exported from Stepik course 1 on " in html
    assert "1. Module One" in html
    assert "1. Lesson One" in html
    assert "1. First Step" in html
    assert "2. " not in html
    assert "3. Third Step" in html

    module = sample_course_tree["modules"][0]
    lesson = module["lessons"][0]
    for step in lesson["steps"]:
        assert f"{module['dir_name']}/{lesson['dir_name']}/{step['dir_name']}/index.html" in html

    assert '<link rel="stylesheet" href="assets/style.css">' in html
    for name in ["step.html.j2", "toc.html.j2", "style.css", "mathjax/tex-svg-full.js", "mathjax/LICENSE"]:
        assert (tmp_path / "assets" / name).read_bytes() == (ASSETS_DIR / name).read_bytes()


def test_build_toc_lists_a_skipped_step_without_a_link(tmp_path, sample_course_tree):
    build_toc(sample_course_tree, tmp_path, {10001})

    html = (tmp_path / "index.html").read_text()
    assert "3. Third Step (not exported)" in html
    assert "step_003_text" not in html


def test_build_toc_escapes_html_in_the_course_title(tmp_path, sample_course_tree):
    sample_course_tree["title"] = "<script>some_script()</script>"

    build_toc(sample_course_tree, tmp_path, set())

    html = (tmp_path / "index.html").read_text()
    assert "<h1>&lt;script&gt;some_script()&lt;/script&gt;</h1>" in html
    assert "<script>" not in html


def test_build_toc_leaves_hidden_files_out_of_the_assets(tmp_path, sample_course_tree, monkeypatch):
    assets_dir = tmp_path / "project" / "assets"
    (assets_dir / "mathjax").mkdir(parents=True)
    (assets_dir / "mathjax" / "tex-svg-full.js").write_text("")
    (assets_dir / "mathjax" / ".DS_Store").write_bytes(b"finder data")
    monkeypatch.setattr(toc_builder, "ASSETS_DIR", assets_dir)
    course_dir = tmp_path / "course"

    build_toc(sample_course_tree, course_dir, set())

    assert (course_dir / "assets" / "mathjax" / "tex-svg-full.js").exists()
    assert not (course_dir / "assets" / "mathjax" / ".DS_Store").exists()
