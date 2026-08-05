"""Database access: bootstrap on first run, then cached read-only queries."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "warehouse_ops.db"

BUILD_STEPS = ("generate_data.py", "setup_database.py")


def build_database() -> None:
    """Generate the dataset and load it into SQLite, in order."""
    for script in BUILD_STEPS:
        subprocess.run([sys.executable, str(ROOT / script)], check=True)


@st.cache_resource(show_spinner="Building the warehouse database…")
def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        build_database()
    return sqlite3.connect(DB_PATH, check_same_thread=False)


@st.cache_data(ttl=600, show_spinner=False)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a parameterised read query, cached on the SQL and its parameters."""
    return pd.read_sql_query(sql, get_connection(), params=list(params))
