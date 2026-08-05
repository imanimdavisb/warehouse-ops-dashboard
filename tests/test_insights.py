import pandas as pd

from warehouse import insights
from warehouse.formatting import EMPTY, fmt_delta, fmt_int, fmt_pct, fmt_rate


def target_frame(rows):
    columns = [
        "department", "shift", "uph", "target_uph", "pct_to_target",
        "accuracy_pct", "target_accuracy_pct", "defect_rate_pct",
        "max_defect_rate_pct", "safety_incidents", "attainment_rank",
    ]
    return pd.DataFrame(rows, columns=columns)


HEALTHY = target_frame([
    ["Pick", "Day", 126.0, 126.0, 100.0, 99.5, 99.0, 0.30, 0.40, 0, 1],
    ["Pack", "Day", 145.0, 147.0, 98.6, 99.6, 99.0, 0.25, 0.30, 0, 2],
])

STRUGGLING = target_frame([
    ["Pick", "Day", 126.0, 126.0, 100.0, 99.5, 99.0, 0.30, 0.40, 0, 1],
    ["Returns", "Night", 48.0, 66.0, 72.7, 97.8, 99.0, 1.40, 1.00, 2, 2],
])


def test_group_far_behind_goal_is_flagged_with_the_gap():
    result = insights.worst_attainment(STRUGGLING)
    assert result.level == "alert"
    assert "Returns / Night" in result.message
    assert "27.3%" in result.message


def test_everyone_near_goal_produces_no_alert():
    assert insights.worst_attainment(HEALTHY) is None


def test_top_performer_named_only_when_at_or_above_goal():
    assert "Pick / Day" in insights.best_attainment(HEALTHY).message
    behind_only = target_frame([
        ["Pick", "Day", 100.0, 126.0, 79.4, 99.5, 99.0, 0.3, 0.4, 0, 1],
    ])
    assert insights.best_attainment(behind_only) is None


def test_accuracy_below_goal_is_flagged():
    assert "Returns / Night" in insights.accuracy_below_target(STRUGGLING).message
    assert insights.accuracy_below_target(HEALTHY) is None


def test_defect_rate_over_the_ceiling_is_flagged_with_a_count():
    result = insights.defects_above_threshold(STRUGGLING)
    assert "1 of 2 groups" in result.message
    assert insights.defects_above_threshold(HEALTHY) is None


def test_empty_selection_produces_no_target_insights():
    empty = target_frame([])
    assert insights.worst_attainment(empty) is None
    assert insights.accuracy_below_target(empty) is None
    assert insights.defects_above_threshold(empty) is None


def monthly_frame(changes):
    return pd.DataFrame({
        "month": [f"2025-{i + 1:02d}" for i in range(len(changes))],
        "uph": [100.0] * len(changes),
        "uph_change": changes,
    })


def test_throughput_direction_reads_the_latest_month():
    assert insights.throughput_direction(monthly_frame([None, -4.2])).level == "warn"
    assert insights.throughput_direction(monthly_frame([None, 3.1])).level == "ok"
    assert "steady" in insights.throughput_direction(monthly_frame([None, 0.2])).message


def test_a_single_month_has_nothing_to_compare():
    assert insights.throughput_direction(monthly_frame([None])) is None


def test_any_incident_is_an_alert_and_zero_is_ok():
    assert insights.safety_status(3).level == "alert"
    assert insights.safety_status(0).level == "ok"
    assert insights.safety_status(None).level == "ok"


def test_staffing_tip_names_only_departments_behind_goal():
    tip = insights.staffing_tip(STRUGGLING)
    assert "Returns" in tip.message
    assert "Pick" not in tip.message
    assert insights.staffing_tip(HEALTHY) is None


def test_generate_insights_always_reports_safety():
    results = insights.generate_insights(0, target_frame([]), monthly_frame([None]))
    assert [i.level for i in results] == ["ok"]


def test_formatters_handle_missing_values():
    assert fmt_int(None) == EMPTY
    assert fmt_pct(float("nan")) == EMPTY
    assert fmt_rate(None) == EMPTY
    assert fmt_delta(None) is None
    assert fmt_int(12345) == "12,345"
    assert fmt_pct(99.456) == "99.46%"
    assert fmt_rate(102.34) == "102.3"
    assert fmt_delta(1.5, "pp") == "+1.50pp"
    assert fmt_delta(-1.5) == "-1.50"
