"""Warehouse operations dashboard.

Presentation only. SQL lives in warehouse/queries.py and the business rules in
warehouse/insights.py, so both are tested in CI without launching Streamlit.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from warehouse import queries as q
from warehouse.db import query
from warehouse.formatting import fmt_delta, fmt_int, fmt_pct, fmt_rate
from warehouse.insights import generate_insights

st.set_page_config(page_title="Warehouse Operations Dashboard", page_icon="📦", layout="wide")

CHART_HEIGHT = 340

st.title("Warehouse Operations Dashboard")
st.caption(
    "Throughput, quality, and safety against goal for a simulated fulfillment "
    "center. Independent educational project — synthetic data, not affiliated "
    "with any company."
)

# --- Filters ---------------------------------------------------------------
options = query(q.FILTER_OPTIONS)
all_months = sorted(options["month"].dropna().unique().tolist())
all_shifts = sorted(options["shift"].dropna().unique().tolist())
all_departments = sorted(options["department"].dropna().unique().tolist())

with st.sidebar:
    st.header("Filters")
    selected_months = st.multiselect("Month", all_months, default=all_months)
    selected_shifts = st.multiselect("Shift", all_shifts, default=all_shifts)
    selected_departments = st.multiselect("Department", all_departments, default=all_departments)
    st.divider()
    st.caption("Narrow the selection to review a single month, shift, or department.")

if not (selected_months and selected_shifts and selected_departments):
    st.warning("Pick at least one month, shift, and department to see the numbers.")
    st.stop()

where, filter_params = q.build_filter_clause(
    selected_months, selected_shifts, selected_departments
)
where_p, _ = q.build_filter_clause(
    selected_months, selected_shifts, selected_departments, alias="p"
)
params = tuple(filter_params)

row_count = int(query(q.render(q.ROW_COUNT, where), params).iloc[0]["row_count"])
if row_count == 0:
    st.warning("No records match this combination of filters. Widen the selection to continue.")
    st.stop()

# --- Executive summary -----------------------------------------------------
latest_date = query(q.render(q.LATEST_DATE, where), params).iloc[0]["latest_date"]
kpis = query(q.render(q.KPI_SUMMARY, where), (latest_date, *params)).iloc[0]
monthly = query(q.render(q.MONTHLY_TREND, where), params)
vs_target = query(q.render(q.PERFORMANCE_VS_TARGET, where_p), params)

last_month = monthly.iloc[-1] if not monthly.empty else None

st.subheader("Executive summary")
st.caption(
    f"{row_count:,} records selected. Deltas compare the latest month in range "
    f"to the one before. Orders picked today uses {latest_date}."
)

columns = st.columns(5)
columns[0].metric("Orders picked today", fmt_int(kpis["orders_picked_today"]))
columns[1].metric(
    "Order accuracy",
    fmt_pct(kpis["order_accuracy"]),
    fmt_delta(last_month["accuracy_change"] if last_month is not None else None, "pp"),
)
columns[2].metric(
    "Units per hour",
    fmt_rate(kpis["units_per_hour"]),
    fmt_delta(last_month["uph_change"] if last_month is not None else None),
)
columns[3].metric(
    "Safety incidents",
    fmt_int(kpis["safety_incidents"]),
    delta_color="inverse",
)
columns[4].metric("Quality score", fmt_pct(kpis["quality_score"]))

# --- Attainment vs goal ----------------------------------------------------
st.subheader("Throughput against goal")

attainment = vs_target.copy()
attainment["group"] = attainment["department"] + " / " + attainment["shift"]
attainment["status"] = pd.cut(
    attainment["pct_to_target"],
    bins=[-float("inf"), 90, 100, float("inf")],
    labels=["Behind", "Near goal", "At or above goal"],
)

chart = px.bar(
    attainment.sort_values("pct_to_target"),
    x="pct_to_target",
    y="group",
    orientation="h",
    color="status",
    color_discrete_map={
        "Behind": "#C0392B",
        "Near goal": "#E1A32B",
        "At or above goal": "#1F6F5C",
    },
    labels={"pct_to_target": "% of goal", "group": "", "status": ""},
    text="pct_to_target",
)
chart.add_vline(x=100, line_dash="dash", line_color="#6B7A77")
chart.update_xaxes(range=[85, 105])
chart.update_traces(texttemplate="%{text:.0f}%", textposition="outside", cliponaxis=False)
chart.update_layout(
    height=max(CHART_HEIGHT, 28 * len(attainment) + 120),
    margin=dict(t=20, b=10, l=10, r=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(chart, width='stretch')

with st.expander("SQL behind this chart — a CTE, a join to targets, and RANK()"):
    st.code(q.preview(q.PERFORMANCE_VS_TARGET, where_p, filter_params), language="sql")

# --- Trend -----------------------------------------------------------------
weekly = query(q.render(q.WEEKLY_PICK_RATE, where), params)
weekly["week_start"] = pd.to_datetime(weekly["week_start"])

st.subheader("Pick rate by week")
trend = go.Figure()
trend.add_trace(
    go.Scatter(
        x=weekly["week_start"],
        y=weekly["pick_rate"],
        name="Weekly",
        mode="lines+markers",
        line=dict(color="#9BB5AE", width=1.5),
    )
)
trend.add_trace(
    go.Scatter(
        x=weekly["week_start"],
        y=weekly["rolling_4wk_avg"],
        name="4-week average",
        mode="lines",
        line=dict(color="#1F6F5C", width=3),
    )
)
trend.update_layout(
    height=CHART_HEIGHT,
    margin=dict(t=20, b=10, l=10, r=10),
    yaxis_title="Units per hour",
    xaxis_title="",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(trend, width='stretch')

with st.expander("SQL behind this chart — a windowed rolling average"):
    st.code(q.preview(q.WEEKLY_PICK_RATE, where, filter_params), language="sql")

# --- Breakdowns ------------------------------------------------------------
accuracy = query(q.render(q.ACCURACY_BY_DEPARTMENT, where), params)
defects = query(q.render(q.DEFECTS_BY_DEPARTMENT, where), params)
incidents = query(q.render(q.INCIDENTS_BY_MONTH, where), params)
productivity = query(q.render(q.PRODUCTIVITY_BY_SHIFT, where), params)


def bar(data, x, y, title, labels, text=True):
    figure = px.bar(data, x=x, y=y, text_auto=text, title=title, labels=labels)
    figure.update_layout(height=CHART_HEIGHT, margin=dict(t=60, b=10, l=10, r=10))
    return figure


left, right = st.columns(2)

with left:
    figure = bar(
        accuracy,
        "department",
        "accuracy_pct",
        "Accuracy by department",
        {"department": "", "accuracy_pct": "Accuracy (%)"},
        text=".2f",
    )
    floor = accuracy["accuracy_pct"].min()
    figure.update_yaxes(range=[max(0, (floor or 0) - 1), 100])
    st.plotly_chart(figure, width='stretch')

with right:
    st.plotly_chart(
        bar(
            defects,
            "department",
            "defect_rate_pct",
            "Defect rate by department",
            {"department": "", "defect_rate_pct": "Defects (% of units)"},
            text=".3f",
        ),
        width='stretch',
    )

left, right = st.columns(2)

with left:
    st.plotly_chart(
        bar(
            incidents,
            "month",
            "safety_incidents",
            "Safety incidents by month",
            {"month": "", "safety_incidents": "Incidents"},
        ),
        width='stretch',
    )

with right:
    st.plotly_chart(
        bar(
            productivity,
            "shift",
            "units_per_hour",
            "Productivity by shift",
            {"shift": "", "units_per_hour": "Units per hour"},
            text=".1f",
        ),
        width='stretch',
    )

# --- Scorecard -------------------------------------------------------------
st.subheader("Scorecard by department and shift")

scorecard = vs_target.rename(
    columns={
        "department": "Department",
        "shift": "Shift",
        "uph": "UPH",
        "target_uph": "Target UPH",
        "pct_to_target": "% of goal",
        "accuracy_pct": "Accuracy %",
        "target_accuracy_pct": "Accuracy goal",
        "defect_rate_pct": "Defect %",
        "max_defect_rate_pct": "Defect limit",
        "safety_incidents": "Incidents",
        "attainment_rank": "Rank",
    }
)

st.dataframe(
    scorecard.style
    .background_gradient(subset=["% of goal"], cmap="RdYlGn", vmin=85, vmax=110)
    .format({
        "UPH": "{:.1f}", "Target UPH": "{:.1f}", "% of goal": "{:.1f}%",
        "Accuracy %": "{:.2f}%", "Accuracy goal": "{:.1f}%",
        "Defect %": "{:.3f}%", "Defect limit": "{:.3f}%",
    }),
    width='stretch',
    hide_index=True,
)

st.download_button(
    "Download scorecard (CSV)",
    scorecard.to_csv(index=False).encode("utf-8"),
    file_name="warehouse_scorecard.csv",
    mime="text/csv",
)

with st.expander("Month-over-month detail"):
    st.dataframe(monthly, width='stretch', hide_index=True)

# --- Insights --------------------------------------------------------------
st.subheader("What an operations manager would flag")
for insight in generate_insights(kpis["safety_incidents"], vs_target, monthly):
    st.info(insight.render())
