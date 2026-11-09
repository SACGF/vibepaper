"""`vibepaper check`: asserts evaluated against partial facts (issue #21)."""

from vibepaper.check import check_text
from vibepaper.render import make_jinja_env


def test_check_reports_each_status(tmp_path):
    text = (
        "{% assert a.x > a.y, 'x over y' %}\n"
        "Prose {{ a.x }}.\n"
        "{# {% assert a.x < 0, 'commented out' %} #}\n"
        "{% assert a.x < a.y, 'y over x' %}\n"
        "{% assert gone.n > 0, 'needs gone' %}\n"
        "{%- assert a.nope == 1 -%}\n"
        "{% assert a.x > a.label, 'bad compare' %}\n"
    )
    ctx = {"a": {"x": 5, "y": 3, "label": "text"}}
    results = check_text(text, "r.md", make_jinja_env(tmp_path), ctx)
    assert [(r.line, r.status, r.message) for r in results] == [
        (1, "PASS", "x over y"),
        (4, "FAIL", "y over x"),
        (5, "MISSING", "needs gone"),
        (6, "MISSING", "condition is false"),
        (7, "ERROR", "bad compare"),
    ]
    assert results[1].values == {"a.x": 5, "a.y": 3}
    assert results[2].detail == "needs facts: gone.csv"
