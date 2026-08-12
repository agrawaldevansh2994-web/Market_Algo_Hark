"""Instrument registry — loads and validates config/instruments.yaml.

The registry is the single source of truth for what the observatory tracks.
Nothing else in the codebase should hardcode a ticker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "instruments.yaml"

# Sessions determine timezone-contamination risk when joining to Indian equities.
# See research/02-observatory-scope.md §4.1.
SESSIONS = {"ist_close", "us_session", "global_24h", "noon_et"}
SOURCES = {"yfinance", "fred", "nse", "derived", "unresolved"}
FETCHABLE_SOURCES = {"yfinance", "fred"}
ROLES = {"subject", "context"}
STATUSES = {"ok", "verify", "unresolved"}


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    klass: str
    source: str
    ticker: str | None
    currency: str
    session: str
    role: str
    status: str
    answers: tuple[str, ...] = ()
    derived_from: tuple[str, ...] = ()
    notes: str | None = None

    @property
    def is_fetchable(self) -> bool:
        """True if this instrument can be pulled directly from a live source."""
        return self.source in FETCHABLE_SOURCES and bool(self.ticker)

    @property
    def is_derived(self) -> bool:
        return self.source == "derived"

    @property
    def contaminates_same_day(self) -> bool:
        """True if a same-day join against Indian equities is suspect.

        Anything settling after the 15:30 IST close carries the following US
        session inside the same calendar date. Scope §4.1.
        """
        return self.session != "ist_close"


class Registry(dict):
    """Mapping of key -> Instrument, with convenience selectors."""

    def by_class(self, *klasses: str) -> list[Instrument]:
        return [i for i in self.values() if i.klass in klasses]

    def by_source(self, *sources: str) -> list[Instrument]:
        return [i for i in self.values() if i.source in sources]

    def fetchable(self) -> list[Instrument]:
        return [i for i in self.values() if i.is_fetchable]

    def derived(self) -> list[Instrument]:
        return [i for i in self.values() if i.is_derived]

    def unresolved(self) -> list[Instrument]:
        return [i for i in self.values() if i.status == "unresolved"]

    def answering(self, question: str) -> list[Instrument]:
        """Instruments required to answer a scope §3 question, e.g. 'C1'."""
        return [i for i in self.values() if question in i.answers]


def load_registry(path: Path | str = CONFIG_PATH) -> Registry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    reg = Registry()

    for key, spec in raw.items():
        inst = Instrument(
            key=key,
            name=spec["name"],
            klass=spec["klass"],
            source=spec["source"],
            ticker=spec.get("ticker"),
            currency=spec["currency"],
            session=spec["session"],
            role=spec["role"],
            status=spec["status"],
            answers=tuple(spec.get("answers") or ()),
            derived_from=tuple(spec.get("derived_from") or ()),
            notes=spec.get("notes"),
        )
        _validate(inst)
        reg[key] = inst

    # Derived instruments must reference keys that actually exist.
    for inst in reg.derived():
        missing = [k for k in inst.derived_from if k not in reg]
        if missing:
            raise ValueError(f"{inst.key}: derived_from references unknown {missing}")
        if not inst.derived_from:
            raise ValueError(f"{inst.key}: source is 'derived' but derived_from is empty")

    return reg


def _validate(inst: Instrument) -> None:
    if inst.session not in SESSIONS:
        raise ValueError(f"{inst.key}: bad session {inst.session!r}")
    if inst.source not in SOURCES:
        raise ValueError(f"{inst.key}: bad source {inst.source!r}")
    if inst.role not in ROLES:
        raise ValueError(f"{inst.key}: bad role {inst.role!r}")
    if inst.status not in STATUSES:
        raise ValueError(f"{inst.key}: bad status {inst.status!r}")
    if inst.source in FETCHABLE_SOURCES and not inst.ticker:
        raise ValueError(f"{inst.key}: {inst.source} source requires a ticker")
