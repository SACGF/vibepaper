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

An optional fourth ``type`` column (``fraction``, ``percent``, ...) types a
value, which also suits a constant that no script produces, such as a value
cited from another paper (issue #46)::

    fact,value,reason,type
    literature.kit_lod,0.003,"Smith 2020, Table 2",fraction

``vibepaper freeze literature.kit_lod --value 0.003 --type fraction --reason
"..."`` writes that row. A blank type keeps the type the facts CSV declares.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from .facts import TYPES, FactTypeError, fact_type, typed, untyped

HEADER = ["fact", "value", "reason"]
TYPED_HEADER = HEADER + ["type"]


@dataclass
class FrozenFact:
    fact: str
    value: object
    reason: str
    type: str = ""


def _coerce(text: str):
    """Numeric strings become numbers, as ``load_facts`` does."""
    return untyped(text)


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
            type_name = (row.get("type") or "").strip()
            if type_name:
                try:
                    parsed = typed(value, type_name)
                except FactTypeError as exc:
                    raise ValueError(f"{path}:{n}: {fact}: {exc}") from None
            else:
                parsed = _coerce(value)
            rows.append(FrozenFact(fact, parsed, (row.get("reason") or "").strip(), type_name))
    return rows


def write_frozen(path: Path, rows: list[FrozenFact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The type column is written only when a row has a type, so files from
    # before issue #46 are unchanged.
    has_type = any(r.type for r in rows)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(TYPED_HEADER if has_type else HEADER)
        for r in sorted(rows, key=lambda r: r.fact):
            writer.writerow([r.fact, r.value, r.reason] + ([r.type] if has_type else []))


def apply_frozen(context: dict, path: Path) -> list[FrozenFact]:
    """Overwrite ``context`` values with the frozen ones; returns the rows."""
    rows = read_frozen(path)
    for r in rows:
        namespace, field = r.fact.split(".", 1)
        ns = context.setdefault(namespace, {})
        if not isinstance(ns, dict):
            raise ValueError(f"{path}: {r.fact}: '{namespace}' is not a facts namespace")
        old_type = fact_type(ns.get(field))
        if r.type:
            if old_type and old_type != r.type:
                raise ValueError(f"{path}: {r.fact}: frozen as {r.type}, but its facts CSV "
                                 f"types it {old_type}")
            ns[field] = r.value
        elif old_type:
            # A frozen value keeps the type its facts CSV declares (issue #12).
            try:
                ns[field] = TYPES[old_type](r.value)
            except FactTypeError as exc:
                raise ValueError(f"{path}: {r.fact}: {exc}") from None
        else:
            ns[field] = r.value
    return rows


def freeze(path: Path, context: dict, facts: list[str], reason: str,
           value: str | None = None, type_name: str = "") -> list[str]:
    """Add (or update) rows for ``facts`` with their current values in
    ``context``. With ``value`` (one fact only), record that value instead,
    for a fact no facts CSV has, such as a cited constant (issue #46).
    ``type_name`` types the value. Returns one message per fact."""
    rows = {r.fact: r for r in read_frozen(path)}
    messages = []
    if value is not None and len(facts) != 1:
        raise ValueError("--value freezes one fact at a time")
    for fact in facts:
        namespace, _, field = fact.partition(".")
        if not field:
            raise ValueError(f"fact must be 'namespace.field', got {fact!r}")
        ns = context.get(namespace)
        old = rows.get(fact)
        if value is not None:
            try:
                new = typed(value, type_name) if type_name else _coerce(value)
            except FactTypeError as exc:
                raise ValueError(f"{fact}: {exc}") from None
        else:
            if not isinstance(ns, dict) or field not in ns:
                raise ValueError(f"no fact {fact!r} in the facts directory; to record a value "
                                 "no script produces (a cited constant), pass --value")
            new = ns[field]
            if hasattr(new, "item"):
                new = new.item()
            if type_name:
                try:
                    new = typed(str(new), type_name)
                except FactTypeError as exc:
                    raise ValueError(f"{fact}: {exc}") from None
        kind = type_name or (old.type if old else "")
        rows[fact] = FrozenFact(fact, new, reason or (old.reason if old else ""), kind)
        if old is None:
            messages.append(f"froze {fact} = {new!r}" + (f" ({kind})" if kind else ""))
        elif old.value != new:
            messages.append(f"updated {fact}: {old.value!r} → {new!r}")
        else:
            messages.append(f"{fact} already frozen at {new!r}")
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
