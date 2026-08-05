import sqlite3

import pytest

from warehouse import queries as q


def test_no_selection_produces_no_where_clause():
    clause, params = q.build_filter_clause([], [], [])
    assert clause == ""
    assert params == []


def test_single_dimension_binds_one_placeholder_per_value():
    clause, params = q.build_filter_clause(["2025-01", "2025-02"], [], [])
    assert clause == "WHERE month IN (?, ?)"
    assert params == ["2025-01", "2025-02"]


def test_alias_qualifies_columns_for_joined_queries():
    clause, _ = q.build_filter_clause(["2025-01"], ["Day"], [], alias="p")
    assert "p.month IN (?)" in clause
    assert "p.shift IN (?)" in clause


def test_placeholder_count_matches_param_count():
    clause, params = q.build_filter_clause(["a", "b"], ["Day"], ["Pick"])
    assert clause.count("?") == len(params)


def test_user_values_never_reach_the_sql_string():
    clause, _ = q.build_filter_clause(["'; DROP TABLE warehouse_performance; --"], [], [])
    assert "DROP TABLE" not in clause


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE warehouse_performance (
            work_date TEXT, week_start TEXT, month TEXT, shift TEXT, department TEXT,
            orders_picked INTEGER, accurate_orders INTEGER, units_picked INTEGER,
            labor_hours REAL, quality_defects INTEGER, safety_incidents INTEGER
        );
        CREATE TABLE department_targets (
            department TEXT, shift TEXT, target_uph REAL,
            target_accuracy_pct REAL, max_defect_rate_pct REAL
        );
        """
    )
    conn.executemany(
        "INSERT INTO warehouse_performance VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("2025-01-06", "2025-01-06", "2025-01", "Day", "Pick", 100, 99, 500, 10.0, 5, 0),
            ("2025-01-07", "2025-01-06", "2025-01", "Night", "Pick", 80, 78, 360, 10.0, 9, 1),
            ("2025-02-03", "2025-02-03", "2025-02", "Day", "Pick", 120, 119, 620, 10.0, 4, 0),
        ],
    )
    conn.executemany(
        "INSERT INTO department_targets VALUES (?,?,?,?,?)",
        [("Pick", "Day", 55.0, 99.0, 1.0), ("Pick", "Night", 45.0, 99.0, 1.0)],
    )
    conn.commit()
    return conn


UNALIASED = [
    q.ROW_COUNT,
    q.LATEST_DATE,
    q.MONTHLY_TREND,
    q.WEEKLY_PICK_RATE,
    q.ACCURACY_BY_DEPARTMENT,
    q.DEFECTS_BY_DEPARTMENT,
    q.INCIDENTS_BY_MONTH,
    q.PRODUCTIVITY_BY_SHIFT,
]


@pytest.mark.parametrize("template", UNALIASED)
def test_templates_run_filtered_and_unfiltered(connection, template):
    clause, params = q.build_filter_clause(["2025-01"], ["Day"], ["Pick"])
    connection.execute(q.render(template, clause), params).fetchall()
    connection.execute(q.render(template, ""), []).fetchall()


def test_kpi_summary_scopes_orders_today_to_the_latest_date(connection):
    clause, params = q.build_filter_clause(["2025-01"], ["Day", "Night"], ["Pick"])
    row = connection.execute(q.render(q.KPI_SUMMARY, clause), ["2025-01-06", *params]).fetchone()
    assert row[0] == 100
    assert row[3] == 1


def test_null_aggregates_when_nothing_matches(connection):
    clause, params = q.build_filter_clause(["1999-01"], [], [])
    row = connection.execute(q.render(q.KPI_SUMMARY, clause), ["1999-01-01", *params]).fetchone()
    assert row[1] is None  # the app must format this without crashing


def test_monthly_trend_computes_a_month_over_month_change(connection):
    rows = connection.execute(q.render(q.MONTHLY_TREND, "")).fetchall()
    assert rows[0][2] is None  # first month has no prior month to compare
    assert rows[1][2] is not None


def test_rolling_average_equals_the_series_while_under_four_weeks(connection):
    rows = connection.execute(q.render(q.WEEKLY_PICK_RATE, "")).fetchall()
    first = rows[0]
    assert first[1] == first[2]


def test_performance_vs_target_joins_and_ranks(connection):
    clause, params = q.build_filter_clause([], [], [], alias="p")
    rows = connection.execute(q.render(q.PERFORMANCE_VS_TARGET, clause), params).fetchall()
    assert len(rows) == 2  # one row per department/shift pair with a target
    ranks = sorted(row[-1] for row in rows)
    assert ranks == [1, 2]


def test_performance_vs_target_respects_filters(connection):
    clause, params = q.build_filter_clause([], ["Day"], [], alias="p")
    rows = connection.execute(q.render(q.PERFORMANCE_VS_TARGET, clause), params).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "Day"


def test_pct_to_target_is_actual_over_goal(connection):
    clause, params = q.build_filter_clause([], ["Night"], [], alias="p")
    row = connection.execute(q.render(q.PERFORMANCE_VS_TARGET, clause), params).fetchone()
    assert row[2] == 36.0  # 360 units / 10 hours
    assert row[4] == 80.0  # 36 of a 45 unit/hr goal


def test_preview_inlines_values_for_display():
    clause, params = q.build_filter_clause(["2025-01"], [], [])
    preview = q.preview(q.WEEKLY_PICK_RATE, clause, params)
    assert "'2025-01'" in preview
    assert "?" not in preview
    assert preview.endswith(";")
