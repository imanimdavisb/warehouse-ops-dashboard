"""SQL templates and the dynamic filter builder.

Each template has a `{where}` slot. Only the *shape* of the WHERE clause is
interpolated — the number of `?` placeholders. Selected values are always bound
as parameters by SQLite, so the dynamic filtering is injection-safe.

Queries that join `department_targets` alias the fact table as `p`, so
`build_filter_clause` takes an optional alias to qualify the column names.

No Streamlit imports here, which is what makes this testable in CI.
"""

from __future__ import annotations

FILTER_OPTIONS = """
SELECT DISTINCT month, shift, department
FROM warehouse_performance
ORDER BY month, shift, department
"""

ROW_COUNT = """
SELECT COUNT(*) AS row_count
FROM warehouse_performance
{where}
"""

LATEST_DATE = """
SELECT MAX(work_date) AS latest_date
FROM warehouse_performance
{where}
"""

# The leading ? binds the latest date used by "orders picked today",
# so callers pass [latest_date, *filter_params].
KPI_SUMMARY = """
SELECT
    SUM(CASE WHEN work_date = ? THEN orders_picked ELSE 0 END) AS orders_picked_today,
    ROUND(100.0 * SUM(accurate_orders) / NULLIF(SUM(orders_picked), 0), 2) AS order_accuracy,
    ROUND(1.0 * SUM(units_picked) / NULLIF(SUM(labor_hours), 0), 2) AS units_per_hour,
    SUM(safety_incidents) AS safety_incidents,
    ROUND(100.0 * (1 - 1.0 * SUM(quality_defects) / NULLIF(SUM(units_picked), 0)), 2) AS quality_score
FROM warehouse_performance
{where}
"""

# LAG() gives month-over-month movement without a self-join.
MONTHLY_TREND = """
WITH monthly AS (
    SELECT
        month,
        1.0 * SUM(units_picked) / NULLIF(SUM(labor_hours), 0) AS uph,
        100.0 * SUM(accurate_orders) / NULLIF(SUM(orders_picked), 0) AS accuracy_pct,
        100.0 * SUM(quality_defects) / NULLIF(SUM(units_picked), 0) AS defect_rate_pct
    FROM warehouse_performance
    {where}
    GROUP BY month
)
SELECT
    month,
    ROUND(uph, 2) AS uph,
    ROUND(uph - LAG(uph) OVER (ORDER BY month), 2) AS uph_change,
    ROUND(accuracy_pct, 2) AS accuracy_pct,
    ROUND(accuracy_pct - LAG(accuracy_pct) OVER (ORDER BY month), 2) AS accuracy_change,
    ROUND(defect_rate_pct, 3) AS defect_rate_pct
FROM monthly
ORDER BY month
"""

# A rolling 4-week average smooths the weekly noise so the trend is readable.
WEEKLY_PICK_RATE = """
WITH weekly AS (
    SELECT
        week_start,
        SUM(units_picked) AS units_picked,
        SUM(labor_hours) AS labor_hours
    FROM warehouse_performance
    {where}
    GROUP BY week_start
)
SELECT
    week_start,
    ROUND(1.0 * units_picked / NULLIF(labor_hours, 0), 2) AS pick_rate,
    ROUND(
        AVG(1.0 * units_picked / NULLIF(labor_hours, 0)) OVER (
            ORDER BY week_start
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ), 2
    ) AS rolling_4wk_avg
FROM weekly
ORDER BY week_start
"""

# The centrepiece: actuals joined to goals, ranked by attainment.
PERFORMANCE_VS_TARGET = """
WITH actual AS (
    SELECT
        p.department,
        p.shift,
        SUM(p.units_picked) AS units_picked,
        SUM(p.labor_hours) AS labor_hours,
        SUM(p.orders_picked) AS orders_picked,
        SUM(p.accurate_orders) AS accurate_orders,
        SUM(p.quality_defects) AS quality_defects,
        SUM(p.safety_incidents) AS safety_incidents
    FROM warehouse_performance p
    {where}
    GROUP BY p.department, p.shift
)
SELECT
    a.department,
    a.shift,
    ROUND(1.0 * a.units_picked / NULLIF(a.labor_hours, 0), 1) AS uph,
    t.target_uph,
    ROUND(
        100.0 * (1.0 * a.units_picked / NULLIF(a.labor_hours, 0)) / NULLIF(t.target_uph, 0), 1
    ) AS pct_to_target,
    ROUND(100.0 * a.accurate_orders / NULLIF(a.orders_picked, 0), 2) AS accuracy_pct,
    t.target_accuracy_pct,
    ROUND(100.0 * a.quality_defects / NULLIF(a.units_picked, 0), 3) AS defect_rate_pct,
    t.max_defect_rate_pct,
    a.safety_incidents,
    RANK() OVER (
        ORDER BY (1.0 * a.units_picked / NULLIF(a.labor_hours, 0)) / NULLIF(t.target_uph, 0) DESC
    ) AS attainment_rank
FROM actual a
JOIN department_targets t
    ON t.department = a.department
   AND t.shift = a.shift
ORDER BY pct_to_target DESC
"""

ACCURACY_BY_DEPARTMENT = """
SELECT
    department,
    ROUND(100.0 * SUM(accurate_orders) / NULLIF(SUM(orders_picked), 0), 2) AS accuracy_pct
FROM warehouse_performance
{where}
GROUP BY department
ORDER BY accuracy_pct DESC
"""

DEFECTS_BY_DEPARTMENT = """
SELECT
    department,
    SUM(quality_defects) AS quality_defects,
    ROUND(100.0 * SUM(quality_defects) / NULLIF(SUM(units_picked), 0), 3) AS defect_rate_pct
FROM warehouse_performance
{where}
GROUP BY department
ORDER BY quality_defects DESC
"""

INCIDENTS_BY_MONTH = """
SELECT month, SUM(safety_incidents) AS safety_incidents
FROM warehouse_performance
{where}
GROUP BY month
ORDER BY month
"""

PRODUCTIVITY_BY_SHIFT = """
SELECT
    shift,
    ROUND(1.0 * SUM(units_picked) / NULLIF(SUM(labor_hours), 0), 2) AS units_per_hour
FROM warehouse_performance
{where}
GROUP BY shift
ORDER BY units_per_hour DESC
"""

_FILTER_COLUMNS = ("month", "shift", "department")


def build_filter_clause(
    months: list[str] | None,
    shifts: list[str] | None,
    departments: list[str] | None,
    alias: str = "",
) -> tuple[str, list[str]]:
    """Return a `WHERE ... IN (?, ?)` clause plus the values to bind to it.

    An empty selection for a dimension means no constraint on that dimension.
    Pass `alias="p"` for queries that join a second table.
    """
    prefix = f"{alias}." if alias else ""
    conditions: list[str] = []
    params: list[str] = []

    for column, values in zip(_FILTER_COLUMNS, (months, shifts, departments), strict=True):
        if not values:
            continue
        placeholders = ", ".join("?" for _ in values)
        conditions.append(f"{prefix}{column} IN ({placeholders})")
        params.extend(values)

    if not conditions:
        return "", params

    return "WHERE " + "\n      AND ".join(conditions), params


def render(template: str, where_clause: str) -> str:
    """Fill a template's `{where}` slot."""
    return template.format(where=where_clause).strip()


def preview(template: str, where_clause: str, params: list) -> str:
    """Display-only SQL with values inlined, for the UI's SQL panel.

    Never executed — it exists so a reader can see the exact query behind a
    chart, filters and all.
    """
    sql = render(template, where_clause)
    for value in params:
        literal = f"'{value}'" if isinstance(value, str) else str(value)
        sql = sql.replace("?", literal, 1)
    return sql + ";"
