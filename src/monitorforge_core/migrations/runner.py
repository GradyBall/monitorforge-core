"""Numbered-SQL-file migration runner.

Lifted from the Peñasquito monitoring DB almost unchanged -- unlike the
ingestion/parsing code, this had no project-specific coupling at all: it
just runs `*.sql` files from a directory, in order, against Postgres, once
each, under an advisory lock. Every project (Peñasquito, Bisbee, future
ones) needs exactly this, not a project-flavored variant of it.

Migrations must not manage their own transactions (BEGIN/COMMIT/ROLLBACK) --
the runner wraps each migration file in one transaction itself.
"""

import os

from sqlalchemy import text
from sqlalchemy.orm import Session

# Arbitrary but consistent lock id so concurrent app workers don't race to
# apply migrations against the same database.
MIGRATION_LOCK_ID = 123456789
TRANSACTION_CONTROL_STATEMENTS = {"begin", "commit", "rollback", "start transaction"}


def _has_executable_sql(statement: str) -> bool:
    """Return True when a statement contains non-comment SQL tokens."""
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None
    index = 0
    length = len(statement)

    while index < length:
        if in_line_comment:
            if statement[index] == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if statement.startswith("*/", index):
                index += 2
                in_block_comment = False
            else:
                index += 1
            continue

        if dollar_tag is not None:
            if statement.startswith(dollar_tag, index):
                index += len(dollar_tag)
                dollar_tag = None
            else:
                index += 1
            continue

        if in_single_quote:
            if statement[index] == "'" and (index == 0 or statement[index - 1] != "\\"):
                in_single_quote = False
            index += 1
            continue

        if in_double_quote:
            if statement[index] == '"' and (index == 0 or statement[index - 1] != "\\"):
                in_double_quote = False
            index += 1
            continue

        if statement.startswith("--", index):
            in_line_comment = True
            index += 2
            continue

        if statement.startswith("/*", index):
            in_block_comment = True
            index += 2
            continue

        if statement[index] == "$":
            tag_end = index + 1
            while tag_end < length and (statement[tag_end].isalnum() or statement[tag_end] == "_"):
                tag_end += 1
            if tag_end < length and statement[tag_end] == "$":
                dollar_tag = statement[index : tag_end + 1]
                index = tag_end + 1
                continue

        if statement[index] == "'":
            in_single_quote = True
            return True

        if statement[index] == '"':
            in_double_quote = True
            return True

        if not statement[index].isspace():
            return True

        index += 1

    return False


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL on semicolons while preserving dollar-quoted PostgreSQL blocks."""
    statements: list[str] = []
    buffer: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None
    index = 0
    length = len(sql)

    while index < length:
        if in_line_comment:
            char = sql[index]
            buffer.append(char)
            index += 1
            if char == "\n":
                in_line_comment = False
            continue

        if in_block_comment:
            if sql.startswith("*/", index):
                buffer.append("*/")
                index += 2
                in_block_comment = False
            else:
                buffer.append(sql[index])
                index += 1
            continue

        if dollar_tag is not None:
            if sql.startswith(dollar_tag, index):
                buffer.append(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
            else:
                buffer.append(sql[index])
                index += 1
            continue

        if in_single_quote:
            char = sql[index]
            buffer.append(char)
            index += 1
            if char == "'" and (index >= 2 and sql[index - 2] != "\\"):
                in_single_quote = False
            continue

        if in_double_quote:
            char = sql[index]
            buffer.append(char)
            index += 1
            if char == '"' and (index >= 2 and sql[index - 2] != "\\"):
                in_double_quote = False
            continue

        if sql.startswith("--", index):
            buffer.append("--")
            index += 2
            in_line_comment = True
            continue

        if sql.startswith("/*", index):
            buffer.append("/*")
            index += 2
            in_block_comment = True
            continue

        if sql[index] == "$":
            tag_end = index + 1
            while tag_end < length and (sql[tag_end].isalnum() or sql[tag_end] == "_"):
                tag_end += 1
            if tag_end < length and sql[tag_end] == "$":
                dollar_tag = sql[index : tag_end + 1]
                buffer.append(dollar_tag)
                index = tag_end + 1
                continue

        char = sql[index]
        if char == "'":
            in_single_quote = True
            buffer.append(char)
            index += 1
            continue

        if char == '"':
            in_double_quote = True
            buffer.append(char)
            index += 1
            continue

        if char == ";":
            statement = "".join(buffer).strip()
            if statement and _has_executable_sql(statement):
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    trailing = "".join(buffer).strip()
    if trailing and _has_executable_sql(trailing):
        statements.append(trailing)
    return statements


def _strip_leading_sql_comments(statement: str) -> str:
    """Remove leading SQL comments and whitespace before inspecting the statement keyword."""
    remaining = statement.lstrip()
    while remaining.startswith("--") or remaining.startswith("/*"):
        if remaining.startswith("--"):
            newline_index = remaining.find("\n")
            if newline_index == -1:
                return ""
            remaining = remaining[newline_index + 1 :].lstrip()
            continue

        block_end = remaining.find("*/")
        if block_end == -1:
            return ""
        remaining = remaining[block_end + 2 :].lstrip()
    return remaining


def _transaction_control_keyword(statement: str) -> str | None:
    """Return the transaction-control statement keyword, if this statement is one."""
    statement_body = _strip_leading_sql_comments(statement)
    normalized = " ".join(statement_body.strip().rstrip(";").split()).lower()
    for keyword in TRANSACTION_CONTROL_STATEMENTS:
        if normalized == keyword or normalized.startswith(f"{keyword} "):
            return keyword.upper()
    return None


def _validate_migration_statements(filename: str, statements: list[str]) -> None:
    """Reject migration files that attempt to manage their own transaction."""
    for statement in statements:
        transaction_keyword = _transaction_control_keyword(statement)
        if transaction_keyword is not None:
            raise ValueError(
                f"Migration {filename} contains transaction-control statement "
                f"{transaction_keyword}; migrations must let the runner manage transactions."
            )


def run_migrations(session: Session, migrations_dir: str) -> list[str]:
    """Run any pending `*.sql` files from ``migrations_dir``, in filename order.

    Returns the list of migration filenames that were applied (empty if
    everything was already up to date). Safe to call on every app startup.
    """
    applied_now: list[str] = []
    engine = session.get_bind()

    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})

        try:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS public.migrations_history (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL UNIQUE,
                        applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            conn.commit()

            result = conn.execute(text("SELECT filename FROM public.migrations_history"))
            applied = {row[0] for row in result}
            conn.commit()

            sql_files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))

            for filename in sql_files:
                if filename in applied:
                    continue

                filepath = os.path.join(migrations_dir, filename)
                with open(filepath) as f:
                    sql = f.read()
                statements = _split_sql_statements(sql)
                _validate_migration_statements(filename, statements)

                migration_transaction = conn.begin()
                try:
                    for statement in statements:
                        conn.execute(text(statement))

                    conn.execute(
                        text("INSERT INTO public.migrations_history (filename) VALUES (:filename)"),
                        {"filename": filename},
                    )
                    migration_transaction.commit()
                    applied_now.append(filename)
                except Exception:
                    migration_transaction.rollback()
                    raise
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})

    return applied_now
