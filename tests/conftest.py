import pytest
from vibepaper.render import make_jinja_env


@pytest.fixture
def render(tmp_path):
    """Render a Jinja2 template string against a context dict.

    Usage:
        assert render("{{ n | commas }}", n=254129) == "254,129"
    """
    env = make_jinja_env(tmp_path)

    def _render(template: str, **ctx) -> str:
        return env.from_string(template).render(**ctx)

    return _render
