-- Fact table: one row per date, department, and shift.
DROP TABLE IF EXISTS warehouse_performance;

CREATE TABLE warehouse_performance (
    work_date        TEXT    NOT NULL,
    week_start       TEXT    NOT NULL,
    month            TEXT    NOT NULL,
    shift            TEXT    NOT NULL,
    department       TEXT    NOT NULL,
    orders_picked    INTEGER NOT NULL,
    accurate_orders  INTEGER NOT NULL,
    units_picked     INTEGER NOT NULL,
    labor_hours      REAL    NOT NULL,
    quality_defects  INTEGER NOT NULL,
    safety_incidents INTEGER NOT NULL
);

-- Dimension table: the goals each department and shift is measured against.
DROP TABLE IF EXISTS department_targets;

CREATE TABLE department_targets (
    department          TEXT NOT NULL,
    shift               TEXT NOT NULL,
    target_uph          REAL NOT NULL,
    target_accuracy_pct REAL NOT NULL,
    max_defect_rate_pct REAL NOT NULL,
    PRIMARY KEY (department, shift)
);

CREATE INDEX idx_performance_month ON warehouse_performance (month);
CREATE INDEX idx_performance_dept_shift ON warehouse_performance (department, shift);
CREATE INDEX idx_performance_week ON warehouse_performance (week_start);
