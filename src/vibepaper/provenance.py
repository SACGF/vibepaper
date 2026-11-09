"""Facts provenance: which tool versions produced a facts file, and when (issue #13).

An optional sidecar next to each facts CSV::

    output/facts/benchmark.csv
    output/facts/benchmark.provenance.json

    {"date": "2026-10-30",
     "command": "python scripts/benchmark.py --full",
     "tools": {"cdot": "0.2.37", "cdot_data": "0.2.36"}}

It is loaded as ``benchmark._prov``, so version strings in captions and
methods come from the facts instead of being typed by hand::

    Measured with cdot {{ benchmark._prov.tools.cdot }} on {{ benchmark._prov.date }}.

``vibepaper lint`` flags a paragraph or table that uses facts from files whose
``tools`` give different versions of the same tool, and ``vibepaper diff``
reports provenance changes alongside the fact changes. Any other keys are
kept as given.

Producer scripts can write the sidecar with :func:`write_provenance`.
"""

import datetime
import json
import sys
from importlib import metadata
from pathlib import Path

from .errors import ConfigError

SUFFIX = ".provenance.json"
KEY = "_prov"


def sidecar_path(csv_path: Path) -> Path:
    return csv_path.with_name(csv_path.stem + SUFFIX)


def read_provenance(csv_path: Path) -> dict | None:
    """The sidecar of ``csv_path`` as a dict, or None if there is none."""
    path = sidecar_path(csv_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: not valid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a JSON object")
    tools = data.get("tools", {})
    if not isinstance(tools, dict) or not all(isinstance(v, str) for v in tools.values()):
        raise ConfigError(f'{path}: "tools" must map tool names to version strings')
    return data


def write_provenance(
    csv_path,
    tools: dict | list | None = None,
    command: str | None = None,
    date: str | None = None,
    **extra,
) -> Path:
    """Write ``<csv>.provenance.json`` next to a facts CSV.

    ``tools`` maps names to versions; a list of names (or a ``None`` version)
    looks up the installed package version. ``command`` defaults to how this
    script was run, ``date`` to today. Extra keyword arguments are stored too::

        write_provenance("output/facts/benchmark.csv", tools=["cdot"],
                         data_release="0.2.36")
    """
    if isinstance(tools, (list, tuple)):
        tools = {name: None for name in tools}
    resolved = {}
    for name, version in (tools or {}).items():
        if version is None:
            try:
                version = metadata.version(name)
            except metadata.PackageNotFoundError:
                raise ValueError(f"tool {name!r} is not an installed package; pass its version") from None
        resolved[name] = str(version)
    data = {
        "date": date or datetime.date.today().isoformat(),
        "command": command if command is not None else " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
        "tools": resolved,
        **extra,
    }
    path = sidecar_path(Path(csv_path))
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def mixed_versions(namespaces: set[str], context: dict) -> list[str]:
    """Descriptions like ``cdot 0.2.36 (clinvar_vcf) vs 0.2.37 (benchmark)``
    for tools whose version differs between the given namespaces."""
    by_tool: dict[str, dict[str, list[str]]] = {}
    for ns in sorted(namespaces):
        prov = context.get(ns, {}).get(KEY) if isinstance(context.get(ns), dict) else None
        for tool, version in ((prov or {}).get("tools") or {}).items():
            by_tool.setdefault(tool, {}).setdefault(version, []).append(ns)
    out = []
    for tool, versions in sorted(by_tool.items()):
        if len(versions) > 1:
            parts = [f"{v} ({', '.join(nss)})" for v, nss in sorted(versions.items())]
            out.append(f"{tool} " + " vs ".join(parts))
    return out


def provenance_changes(old_flat: dict, new_flat: dict) -> list[str]:
    """``ns: key old → new`` for every changed provenance entry, by namespace."""
    marker = f".{KEY}."
    names = sorted(n for n in set(old_flat) | set(new_flat) if marker in n)
    by_ns: dict[str, list[str]] = {}
    for name in names:
        a, b = old_flat.get(name), new_flat.get(name)
        if a != b:
            ns, key = name.split(marker, 1)
            by_ns.setdefault(ns, []).append(f"{key} {a if a is not None else '(none)'} → "
                                            f"{b if b is not None else '(none)'}")
    return [f"{ns}: " + ", ".join(items) for ns, items in by_ns.items()]
