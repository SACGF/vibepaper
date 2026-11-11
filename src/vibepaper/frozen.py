"""Frozen facts: values deliberately kept from an earlier run (issue #14).

Some facts are not re-measured on purpose: a benchmark against a remote public
database, results from cached external responses, a table frozen at
submission. The script that owns the CSV re-emits the whole file, so without
this the old values had to be merged back by hand after every re-run.

``paper/frozen_facts.csv`` (committed with the paper) records them::

    fact,value,reason
    benchmark.uta_remote_tps,0.13,"public UTA REST, measured 2025-06; not re-run"

Every command that loads facts applies it on top of the facts CSVs, so a
frozen value survives re-runs and ``vibepaper diff`` never reports it as
changed. ``vibepaper freeze ns.field --reason "..."`` adds rows.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from .facts import TYPES, FactTypeError, fact_type

HEADER = ["fact", "value", "reason"]


@dataclass
class FrozenFact:
    fact: str
    value: object
    reason: str


def _coerce(text: str):
    """Numeric strings become numbers, as ``load_facts`` does."""
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text


def read_frozen(path: Path) -> list[FrozenFact]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or reader.fieldnames[:2] != HEADER[:2]:
            raise ValueError(f"{path}: expected a header 'fact,value,reason'")
        rows = []
        for n, row in enumerate(reader, start=2):
            fact, value = (row.get("fact") or "").strip(), (row.get("value") or "").strip()
            if "." not in fact:
                raise ValueError(f"{path}:{n}: fact must be 'namespace.field', got {fact!r}")
            if value == "":
                raise ValueError(f"{path}:{n}: {fact} has no value")
            rows.append(FrozenFact(fact, _coerce(value), (row.get("reason") or "").strip()))
    return rows


def write_frozen(path: Path, rows: list[FrozenFact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(HEADER)
        for r in sorted(rows, key=lambda r: r.fact):
            writer.writerow([r.fact, r.value, r.reason])


def apply_frozen(context: dict, path: Path) -> list[FrozenFact]:
    """Overwrite ``context`` values with the frozen ones; returns the rows."""
    rows = read_frozen(path)
    for r in rows:
        namespace, field = r.fact.split(".", 1)
        ns = context.setdefault(namespace, {})
        if not isinstance(ns, dict):
            raise ValueError(f"{path}: {r.fact}: '{namespace}' is not a facts namespace")
        old_type = fact_type(ns.get(field))
        if old_type:
            # A frozen value keeps the type its facts CSV declares (issue #12).
            try:
                ns[field] = TYPES[old_type](r.value)
            except FactTypeError as exc:
                raise ValueError(f"{path}: {r.fact}: {exc}") from None
        else:
            ns[field] = r.value
    return rows


def freeze(path: Path, context: dict, facts: list[str], reason: str) -> list[str]:
    """Add (or update) rows for ``facts`` with their current values in
    ``context``. Returns one message per fact."""
    rows = {r.fact: r for r in read_frozen(path)}
    messages = []
    for fact in facts:
        namespace, _, field = fact.partition(".")
        ns = context.get(namespace)
        if not field or not isinstance(ns, dict) or field not in ns:
            raise ValueError(f"no fact {fact!r} in the facts directory")
        value = ns[field]
        if hasattr(value, "item"):
            value = value.item()
        old = rows.get(fact)
        rows[fact] = FrozenFact(fact, value, reason or (old.reason if old else ""))
        if old is None:
            messages.append(f"froze {fact} = {value!r}")
        elif old.value != value:
            messages.append(f"updated {fact}: {old.value!r} → {value!r}")
        else:
            messages.append(f"{fact} already frozen at {value!r}")
    write_frozen(path, list(rows.values()))
    return messages


def unfreeze(path: Path, facts: list[str]) -> list[str]:
    rows = {r.fact: r for r in read_frozen(path)}
    messages = []
    for fact in facts:
        if rows.pop(fact, None) is None:
            raise ValueError(f"{fact} is not in {path}")
        messages.append(f"unfroze {fact}")
    write_frozen(path, list(rows.values()))
    return messages
