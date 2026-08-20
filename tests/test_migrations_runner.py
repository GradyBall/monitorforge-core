from pathlib import Path

from monitorforge_core.migrations.runner import (
    _split_sql_statements,
    _validate_migration_statements,
)

BASELINE_SQL_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "monitorforge_core"
    / "migrations"
    / "baseline"
    / "000_baseline_schema.sql"
)


def test_baseline_schema_sql_splits_and_validates_cleanly():
    sql = BASELINE_SQL_PATH.read_text(encoding="utf-8")

    statements = _split_sql_statements(sql)

    assert len(statements) > 0
    _validate_migration_statements("000_baseline_schema.sql", statements)  # raises if invalid

    create_table_statements = [s for s in statements if "CREATE TABLE" in s.upper()]
    create_schema_statements = [s for s in statements if "CREATE SCHEMA" in s.upper()]
    assert len(create_table_statements) == 17
    assert len(create_schema_statements) == 2


def test_split_sql_statements_handles_semicolons_inside_strings():
    sql = "CREATE TABLE t (a TEXT DEFAULT 'a;b'); CREATE TABLE u (b INT);"
    statements = _split_sql_statements(sql)
    assert len(statements) == 2
    assert "a;b" in statements[0]


def test_validate_migration_statements_rejects_transaction_control():
    import pytest

    with pytest.raises(ValueError):
        _validate_migration_statements("bad.sql", ["BEGIN", "CREATE TABLE t (a INT)"])
