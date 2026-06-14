"""Tests for {% include %} resolution and its trusted-root confinement (issue #5).

`{% include %}` resolves files inside *trusted roots* — the project tree and the
user-provided facts_dir (passed as extra_search_paths). The common pattern
`{% include facts_dir + "/foo.md" %}` produces an absolute name when facts_dir
is absolute (the default under --facts-dir); that is supported because facts_dir
is a directory the user designated. Absolute paths outside every trusted root
are refused so a template cannot read arbitrary files on disk.
"""

import pytest

from vibepaper.render import make_jinja_env, render_file


def test_relative_include_within_project_tree(tmp_path):
    (tmp_path / "snippet.md").write_text("hello relative\n")
    (tmp_path / "section.md").write_text('{% include "snippet.md" %}')
    env = make_jinja_env(tmp_path)
    out = render_file(tmp_path / "section.md", tmp_path / "build", {}, env)
    assert out.read_text() == "hello relative\n"


def test_absolute_include_from_facts_dir(tmp_path):
    # The real-world case: facts_dir is absolute and outside project_root, but
    # the user designated it via --facts-dir, so it is a trusted root.
    facts_dir = tmp_path / "output" / "run"
    facts_dir.mkdir(parents=True)
    (facts_dir / "table.md").write_text("a generated table\n")

    project_root = tmp_path / "project"
    project_root.mkdir()
    section = project_root / "section.md"
    section.write_text('{% include facts_dir + "/table.md" %}')

    env = make_jinja_env(project_root, extra_search_paths=[facts_dir])
    out = render_file(
        section, project_root / "build", {"facts_dir": str(facts_dir)}, env
    )
    assert out.read_text() == "a generated table\n"


def test_absolute_include_outside_trusted_roots_is_refused(tmp_path):
    # A path outside both project_root and facts_dir must not be readable,
    # even though the file exists and the process has permission.
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "secret.md").write_text("should not be read\n")

    facts_dir = tmp_path / "facts"
    facts_dir.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()
    section = project_root / "section.md"
    section.write_text('{% include other + "/secret.md" %}')

    env = make_jinja_env(project_root, extra_search_paths=[facts_dir])
    with pytest.raises(RuntimeError) as exc:
        render_file(
            section, project_root / "build", {"other": str(outside)}, env
        )

    message = str(exc.value)
    assert "include" in message.lower()
    assert "facts directory" in message.lower()  # names the trusted-root rule
    assert "should not be read" not in message  # file contents never surfaced
