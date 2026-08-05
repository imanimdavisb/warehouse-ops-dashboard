"""Generate the synthetic fulfillment-center dataset.

Seeded, so every clone of this repo produces identical numbers and the
screenshots in the README stay accurate.

The generator deliberately builds in patterns worth finding:
  * Night shift runs slower than day shift across every department.
  * Returns has the highest defect rate — it handles damaged goods.
  * Q4 volume rises sharply (peak season).
  * Returns on night shift degrades through November and December, which is
    the story the dashboard is meant to surface.

Writes:
  data/warehouse_performance.csv
  data/department_targets.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260101
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"

DATA_DIR = Path(__file__).resolve().parent / "data"

# department -> (baseline units per hour, baseline order accuracy, baseline defect rate)
DEPARTMENTS = {
    "Inbound": (95, 0.991, 0.0035),
    "Pick": (120, 0.994, 0.0030),
    "Pack": (140, 0.996, 0.0025),
    "Ship": (110, 0.993, 0.0028),
    "Returns": (70, 0.982, 0.0090),
}

SHIFTS = {"Day": 1.00, "Night": 0.90}

UNITS_PER_ORDER = 3.2
PEAK_MONTHS = (10, 11, 12)


def seasonal_volume_multiplier(month: int) -> float:
    if month in PEAK_MONTHS:
        return 1.28
    if month in (1, 2):
        return 0.92
    return 1.0


def returns_night_decay(department: str, shift: str, month: int) -> float:
    """The planted problem: Returns/Night slips during peak season."""
    if department == "Returns" and shift == "Night" and month in (11, 12):
        return 0.82
    return 1.0


def generate_performance(rng: np.random.Generator) -> pd.DataFrame:
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    rows = []

    for date in dates:
        is_weekend = date.dayofweek >= 5
        volume_factor = seasonal_volume_multiplier(date.month) * (0.85 if is_weekend else 1.0)

        for department, (base_uph, base_accuracy, base_defect_rate) in DEPARTMENTS.items():
            for shift, shift_factor in SHIFTS.items():
                labor_hours = float(np.round(rng.uniform(70, 140) * volume_factor, 1))

                uph = base_uph * shift_factor
                uph *= returns_night_decay(department, shift, date.month)
                uph *= rng.normal(1.0, 0.07)
                uph = max(uph, 20.0)

                units_picked = int(round(labor_hours * uph))
                orders_picked = max(int(round(units_picked / UNITS_PER_ORDER)), 1)

                accuracy = np.clip(rng.normal(base_accuracy, 0.004), 0.94, 1.0)
                accurate_orders = int(round(orders_picked * accuracy))

                defect_rate = max(rng.normal(base_defect_rate, base_defect_rate * 0.25), 0.0)
                if department == "Returns" and shift == "Night" and date.month in (11, 12):
                    defect_rate *= 1.6
                quality_defects = int(round(units_picked * defect_rate))

                safety_incidents = int(rng.poisson(0.012 * volume_factor))

                rows.append(
                    {
                        "work_date": date.strftime("%Y-%m-%d"),
                        "week_start": (date - pd.Timedelta(days=date.dayofweek)).strftime("%Y-%m-%d"),
                        "month": date.strftime("%Y-%m"),
                        "shift": shift,
                        "department": department,
                        "orders_picked": orders_picked,
                        "accurate_orders": accurate_orders,
                        "units_picked": units_picked,
                        "labor_hours": labor_hours,
                        "quality_defects": quality_defects,
                        "safety_incidents": safety_incidents,
                    }
                )

    return pd.DataFrame(rows)


def generate_targets() -> pd.DataFrame:
    """Goals an operations manager would be held to, slightly above baseline."""
    rows = []
    for department, (base_uph, _, base_defect_rate) in DEPARTMENTS.items():
        for shift, shift_factor in SHIFTS.items():
            rows.append(
                {
                    "department": department,
                    "shift": shift,
                    "target_uph": round(base_uph * shift_factor * 0.99, 1),
                    "target_accuracy_pct": 99.0,
                    "max_defect_rate_pct": round(base_defect_rate * 100 * 1.1, 3),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    rng = np.random.default_rng(SEED)
    DATA_DIR.mkdir(exist_ok=True)

    performance = generate_performance(rng)
    targets = generate_targets()

    performance.to_csv(DATA_DIR / "warehouse_performance.csv", index=False)
    targets.to_csv(DATA_DIR / "department_targets.csv", index=False)

    print(f"Wrote {len(performance):,} performance records to data/warehouse_performance.csv")
    print(f"Wrote {len(targets):,} target records to data/department_targets.csv")


if __name__ == "__main__":
    main()
