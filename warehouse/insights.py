"""Operations-manager insight rules.

Pure functions over the same query results the charts use, so the callouts
always match what is on screen and can be tested without a database.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

BEHIND_TARGET_PCT = 95.0  # below this share of goal is worth flagging
AHEAD_TARGET_PCT = 100.0

LEVEL_ICONS = {"ok": "🟢", "watch": "🟠", "warn": "🟡", "alert": "🔴", "tip": "💡"}


@dataclass(frozen=True)
class Insight:
    level: str
    message: str

    def render(self) -> str:
        return f"{LEVEL_ICONS.get(self.level, '•')} {self.message}"


def _label(row) -> str:
    return f"{row['department']} / {row['shift']}"


def worst_attainment(vs_target: pd.DataFrame) -> Insight | None:
    """Name the department and shift furthest behind its throughput goal."""
    if vs_target.empty or vs_target["pct_to_target"].isna().all():
        return None

    row = vs_target.sort_values("pct_to_target").iloc[0]
    if row["pct_to_target"] >= BEHIND_TARGET_PCT:
        return None

    shortfall = round(100 - row["pct_to_target"], 1)
    return Insight(
        "alert",
        f"{_label(row)} is {shortfall}% below its throughput goal "
        f"({row['uph']} vs {row['target_uph']} units/hr) — the biggest gap in this selection.",
    )


def best_attainment(vs_target: pd.DataFrame) -> Insight | None:
    if vs_target.empty or vs_target["pct_to_target"].isna().all():
        return None

    row = vs_target.sort_values("pct_to_target", ascending=False).iloc[0]
    if row["pct_to_target"] < AHEAD_TARGET_PCT:
        return None

    return Insight(
        "ok",
        f"{_label(row)} is the top performer at {row['pct_to_target']}% of goal "
        f"({row['uph']} units/hr). Worth studying what they do differently.",
    )


def accuracy_below_target(vs_target: pd.DataFrame) -> Insight | None:
    if vs_target.empty:
        return None

    behind = vs_target[vs_target["accuracy_pct"] < vs_target["target_accuracy_pct"]]
    if behind.empty:
        return None

    row = behind.sort_values("accuracy_pct").iloc[0]
    return Insight(
        "warn",
        f"{_label(row)} is under the accuracy goal at {row['accuracy_pct']}% "
        f"against a {row['target_accuracy_pct']}% target.",
    )


def defects_above_threshold(vs_target: pd.DataFrame) -> Insight | None:
    if vs_target.empty:
        return None

    over = vs_target[vs_target["defect_rate_pct"] > vs_target["max_defect_rate_pct"]]
    if over.empty:
        return None

    row = over.sort_values("defect_rate_pct", ascending=False).iloc[0]
    return Insight(
        "watch",
        f"{_label(row)} has a {row['defect_rate_pct']}% defect rate against a "
        f"{row['max_defect_rate_pct']}% ceiling. {len(over)} of "
        f"{len(vs_target)} groups are over the limit.",
    )


def throughput_direction(monthly: pd.DataFrame) -> Insight | None:
    """Read the most recent month-over-month change in units per hour."""
    if len(monthly) < 2:
        return None

    row = monthly.iloc[-1]
    change = row["uph_change"]
    if pd.isna(change):
        return None

    if change < -1:
        return Insight(
            "warn",
            f"Throughput fell {abs(round(change, 2))} units/hr in {row['month']} "
            "versus the month before.",
        )
    if change > 1:
        return Insight(
            "ok",
            f"Throughput rose {round(change, 2)} units/hr in {row['month']} "
            "versus the month before.",
        )
    return Insight("ok", f"Throughput held steady in {row['month']}.")


def safety_status(safety_incidents) -> Insight:
    count = int(safety_incidents or 0)
    if count == 0:
        return Insight("ok", "No safety incidents reported for this selection.")

    return Insight(
        "alert",
        f"{count:,} safety incident(s) reported for this selection. "
        "Any incident should trigger a supervisor review.",
    )


def staffing_tip(vs_target: pd.DataFrame) -> Insight | None:
    if vs_target.empty:
        return None

    behind = vs_target[vs_target["pct_to_target"] < BEHIND_TARGET_PCT]
    if behind.empty:
        return None

    names = ", ".join(sorted({str(dept) for dept in behind["department"]}))
    return Insight(
        "tip",
        f"Consider cross-training or re-balancing headcount into {names}, "
        "where attainment is furthest behind goal.",
    )


def generate_insights(
    safety_incidents,
    vs_target: pd.DataFrame,
    monthly: pd.DataFrame,
) -> list[Insight]:
    candidates = [
        worst_attainment(vs_target),
        accuracy_below_target(vs_target),
        defects_above_threshold(vs_target),
        throughput_direction(monthly),
        safety_status(safety_incidents),
        best_attainment(vs_target),
        staffing_tip(vs_target),
    ]
    return [insight for insight in candidates if insight is not None]
