"""Pre-registration, the trial log, and the sealed holdout (gates 2, 3, 10).

The log is append-only JSONL under `observatory/trials/` and is **tracked in
git** — commit history is the tamper-evident record of how many things were
tried before a result was believed (CLAUDE.md §3, research/01 §3.1). The DSR
reads its trial count from here, so a trial that is not logged is a trial the
statistics cannot correct for.

Rules the code enforces:
* An experiment must be registered (hypothesis, expected sign, parameter grid,
  holdout start) before any trial of it is recorded.
* A registration is immutable: re-registering the same id raises.
* The holdout can be unlocked once per experiment, ever. The unlock is logged
  with the results it produced. A second unlock raises.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

LOG_DIR = Path(__file__).resolve().parents[1] / "trials"
LOG_FILE = LOG_DIR / "log.jsonl"


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=LOG_DIR.parent, timeout=5).stdout.strip() or None
    except Exception:
        return None


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if hasattr(x, "item"):
        return x.item()
    if isinstance(x, (pd.Timestamp, dt.date)):
        return str(x)
    return x


class TrialLog:
    def __init__(self, path: Path | str = LOG_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ reading
    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def registration(self, experiment: str) -> dict | None:
        return next((r for r in self.records() if r["kind"] == "register" and r["experiment"] == experiment), None)

    def trials(self, experiment: str | None = None) -> pd.DataFrame:
        rows = [r for r in self.records() if r["kind"] == "trial" and (experiment is None or r["experiment"] == experiment)]
        if not rows:
            return pd.DataFrame()
        df = pd.json_normalize(rows)
        return df

    def n_trials(self, experiment: str | None = None) -> int:
        """Trials to deflate by. With experiment=None, every trial ever run."""
        return len([r for r in self.records() if r["kind"] == "trial"
                    and (experiment is None or r["experiment"] == experiment)])

    # ------------------------------------------------------------ writing
    def _append(self, rec: dict) -> dict:
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "git": _git_commit(), **rec}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_jsonable(rec), ensure_ascii=False) + "\n")
        return rec

    def register(self, experiment: str, hypothesis: str, expected_sign: str, param_grid: dict,
                 holdout_start: str, universe: str, notes: str = "") -> dict:
        if self.registration(experiment):
            raise ValueError(f"{experiment!r} is already registered; registrations are immutable")
        body = {"hypothesis": hypothesis, "expected_sign": expected_sign, "param_grid": param_grid,
                "holdout_start": holdout_start, "universe": universe, "notes": notes}
        digest = hashlib.sha256(json.dumps(_jsonable(body), sort_keys=True).encode()).hexdigest()[:12]
        return self._append({"kind": "register", "experiment": experiment, "hash": digest, **body})

    def record(self, experiment: str, params: dict, metrics: dict, data_start: str, data_end: str) -> dict:
        reg = self.registration(experiment)
        if reg is None:
            raise ValueError(f"register {experiment!r} before recording trials (gate 2)")
        if pd.Timestamp(data_end) >= pd.Timestamp(reg["holdout_start"]):
            unlocked = any(r["kind"] == "unlock" and r["experiment"] == experiment for r in self.records())
            if not unlocked:
                raise ValueError("trial touches the sealed holdout; use HoldoutSeal.unlock (once)")
        return self._append({"kind": "trial", "experiment": experiment, "params": params,
                             "metrics": metrics, "data_start": data_start, "data_end": data_end})


class HoldoutSeal:
    """Hands out data up to the holdout start; the rest only via a logged, one-time unlock."""

    def __init__(self, experiment: str, log: TrialLog | None = None):
        self.log = log or TrialLog()
        reg = self.log.registration(experiment)
        if reg is None:
            raise ValueError(f"register {experiment!r} first")
        self.experiment = experiment
        self.start = pd.Timestamp(reg["holdout_start"])

    def dev(self, df: pd.DataFrame | pd.Series):
        return df.loc[df.index < self.start]

    @property
    def unlocked(self) -> bool:
        return any(r["kind"] == "unlock" and r["experiment"] == self.experiment for r in self.log.records())

    def unlock(self, df, reason: str, chosen_params: dict):
        """Release the full sample, once. The params are frozen in the log first."""
        if self.unlocked:
            raise PermissionError(f"holdout for {self.experiment!r} was already unlocked — "
                                  "a failed holdout rejects the strategy; it is not re-tuned (gate 10)")
        self.log._append({"kind": "unlock", "experiment": self.experiment,
                          "reason": reason, "chosen_params": chosen_params})
        return df
