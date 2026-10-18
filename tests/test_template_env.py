import pytest
from jinja2 import UndefinedError

from template_env import get_template


def test_get_template_fails_on_an_undefined_variable():
    with pytest.raises(UndefinedError):
        get_template("toc.html.j2").render()
