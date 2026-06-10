from __future__ import annotations

import json
import os
import re
import base64
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from app.config import get_settings

DB_PATH = Path(os.getenv("QUOTATION_DB_PATH", "quotation_history.db"))
DEFAULT_USERS = (
    {"name": "Admin", "email": "admin@example.com", "password": "Admin@123456", "role": "admin"},
    {"name": "User", "email": "user@example.com", "password": "User@123456", "role": "user"},
)


def database_url() -> str:
    return get_settings().database_url


def is_postgres() -> bool:
    return database_url().startswith(("postgresql://", "postgres://"))


def sqlite_path_from_url(url: str) -> Path:
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    if url.startswith("sqlite://"):
        parsed = urlparse(url)
        return Path(parsed.path)
    return DB_PATH


class PgCursor:
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor
        self.lastrowid: int | None = None

    def _wrap(self) -> "PgCursor":
        try:
            row = self.cursor.fetchone()
        except Exception:
            row = None
        if row and "id" in row:
            self.lastrowid = int(row["id"])
        return self

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()


class PgConnection:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def _sql(self, sql: str) -> str:
        sql = sql.replace("?", "%s")
        sql = re.sub(r"\bcurrent_timestamp\b", "current_timestamp", sql, flags=re.I)
        return sql

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> PgCursor:
        normalized = self._sql(sql)
        wants_id = normalized.lstrip().lower().startswith("insert into ") and " returning " not in normalized.lower()
        if wants_id:
            normalized = f"{normalized} returning id"
        cursor = self.conn.execute(normalized, tuple(params or ()))
        wrapped = PgCursor(cursor)
        return wrapped._wrap() if wants_id else wrapped

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> Any:
        return self.conn.executemany(self._sql(sql), params)

    def executescript(self, sql: str) -> None:
        with self.conn.cursor() as cursor:
            for statement in [part.strip() for part in sql.split(";") if part.strip()]:
                cursor.execute(statement)


@contextmanager
def connect():
    if is_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL requires psycopg. Install project requirements first.") from exc
        raw_conn = psycopg.connect(database_url().replace("postgres://", "postgresql://", 1), row_factory=dict_row)
        conn: Any = PgConnection(raw_conn)
    else:
        path = sqlite_path_from_url(database_url())
        path.parent.mkdir(parents=True, exist_ok=True)
        raw_conn = sqlite3.connect(path)
        raw_conn.row_factory = sqlite3.Row
        conn = raw_conn
    try:
        yield conn
        raw_conn.commit()
    finally:
        raw_conn.close()


def init_db() -> None:
    with connect() as conn:
        if is_postgres():
            conn.executescript(
                """
            create table if not exists users (
                id serial primary key,
                name text not null,
                email text unique not null,
                password_hash text,
                role text not null default 'user',
                created_at timestamptz not null default current_timestamp
            );

            create table if not exists auth_tokens (
                id serial primary key,
                user_id integer not null references users(id),
                token_hash text unique not null,
                expires_at text not null,
                revoked_at text,
                created_at timestamptz not null default current_timestamp
            );

            create table if not exists stored_files (
                id serial primary key,
                original_filename text not null,
                storage_backend text not null,
                bucket text not null,
                object_key text not null,
                sha256 text not null,
                mime_type text,
                size_bytes integer not null,
                created_by integer references users(id),
                created_at timestamptz not null default current_timestamp
            );

            create table if not exists materials (
                id serial primary key,
                cas_number text,
                standard_name text not null,
                english_name text,
                chinese_name text,
                synonyms text not null default '[]',
                smiles text,
                inchikey text,
                match_status text not null default 'unresolved',
                created_at timestamptz not null default current_timestamp,
                updated_at timestamptz not null default current_timestamp
            );

            create table if not exists import_files (
                id serial primary key,
                filename text not null,
                uploaded_by text,
                import_type text not null,
                status text not null,
                total_rows integer not null default 0,
                success_rows integer not null default 0,
                failed_rows integer not null default 0,
                stored_file_id integer references stored_files(id),
                file_sha256 text,
                is_duplicate boolean not null default false,
                archived_at text,
                created_at timestamptz not null default current_timestamp
            );

            create table if not exists field_mappings (
                id serial primary key,
                excel_header text not null unique,
                system_field text not null,
                confirmed_by text,
                created_at timestamptz not null default current_timestamp,
                updated_at timestamptz not null default current_timestamp
            );

            create table if not exists procurement_records (
                id serial primary key,
                material_id integer,
                raw_name text not null,
                price numeric,
                currency text not null default 'CNY',
                quantity_value numeric,
                quantity_unit text,
                normalized_quantity numeric,
                normalized_unit text,
                unit_price numeric,
                record_type text not null,
                remark text,
                record_date text,
                requester text,
                supplier text,
                source_file_id integer,
                created_by text,
                archived_at text,
                created_at timestamptz not null default current_timestamp
            );

            create table if not exists quotation_items (
                id serial primary key,
                material_id integer not null,
                required_quantity numeric not null,
                required_unit text not null,
                latest_unit_price numeric,
                estimated_cost numeric,
                price_source_record_id integer,
                created_at timestamptz not null default current_timestamp
            );

            create table if not exists quotations (
                id serial primary key,
                filename text not null,
                customer text,
                quoted_on text,
                currency text not null default 'USD',
                stored_file_id integer references stored_files(id),
                file_sha256 text,
                is_duplicate boolean not null default false,
                archived_at text,
                imported_at timestamptz not null default current_timestamp
            );

            create table if not exists line_items (
                id serial primary key,
                quotation_id integer not null references quotations(id),
                catalog_no text not null,
                product_name text,
                unit_price real,
                quantity real,
                unit text,
                notes text
            );

            create table if not exists fx_rates (
                id serial primary key,
                base_currency text not null,
                quote_currency text not null,
                rate numeric not null,
                effective_on text not null,
                created_by integer references users(id),
                created_at timestamptz not null default current_timestamp,
                unique(base_currency, quote_currency, effective_on)
            );

            create table if not exists alerts (
                id serial primary key,
                catalog_no text not null,
                threshold_percent numeric not null,
                direction text not null default 'any',
                enabled boolean not null default true,
                created_by integer references users(id),
                created_at timestamptz not null default current_timestamp
            );

            create index if not exists idx_line_items_catalog_no on line_items(catalog_no);
            create index if not exists idx_line_items_quotation_id on line_items(quotation_id);
            create index if not exists idx_import_files_sha256 on import_files(file_sha256);
            create index if not exists idx_quotations_sha256 on quotations(file_sha256);
            """
            )
            _ensure_default_users(conn)
            return

        conn.executescript(
            """
            create table if not exists users (
                id integer primary key autoincrement,
                name text not null,
                email text unique not null,
                password_hash text,
                role text not null default 'user',
                created_at text not null default current_timestamp
            );

            create table if not exists auth_tokens (
                id integer primary key autoincrement,
                user_id integer not null,
                token_hash text unique not null,
                expires_at text not null,
                revoked_at text,
                created_at text not null default current_timestamp,
                foreign key(user_id) references users(id)
            );

            create table if not exists stored_files (
                id integer primary key autoincrement,
                original_filename text not null,
                storage_backend text not null,
                bucket text not null,
                object_key text not null,
                sha256 text not null,
                mime_type text,
                size_bytes integer not null,
                created_by integer,
                created_at text not null default current_timestamp,
                foreign key(created_by) references users(id)
            );

            create table if not exists materials (
                id integer primary key autoincrement,
                cas_number text,
                standard_name text not null,
                english_name text,
                chinese_name text,
                synonyms text not null default '[]',
                smiles text,
                inchikey text,
                match_status text not null default 'unresolved',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create table if not exists import_files (
                id integer primary key autoincrement,
                filename text not null,
                uploaded_by text,
                import_type text not null,
                status text not null,
                total_rows integer not null default 0,
                success_rows integer not null default 0,
                failed_rows integer not null default 0,
                stored_file_id integer,
                file_sha256 text,
                is_duplicate integer not null default 0,
                archived_at text,
                created_at text not null default current_timestamp
            );

            create table if not exists field_mappings (
                id integer primary key autoincrement,
                excel_header text not null unique,
                system_field text not null,
                confirmed_by text,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );

            create table if not exists procurement_records (
                id integer primary key autoincrement,
                material_id integer,
                raw_name text not null,
                price numeric,
                currency text not null default 'CNY',
                quantity_value numeric,
                quantity_unit text,
                normalized_quantity numeric,
                normalized_unit text,
                unit_price numeric,
                record_type text not null,
                remark text,
                record_date text,
                requester text,
                supplier text,
                source_file_id integer,
                created_by text,
                archived_at text,
                created_at text not null default current_timestamp,
                foreign key(material_id) references materials(id),
                foreign key(source_file_id) references import_files(id)
            );

            create table if not exists quotation_items (
                id integer primary key autoincrement,
                material_id integer not null,
                required_quantity numeric not null,
                required_unit text not null,
                latest_unit_price numeric,
                estimated_cost numeric,
                price_source_record_id integer,
                created_at text not null default current_timestamp,
                foreign key(material_id) references materials(id),
                foreign key(price_source_record_id) references procurement_records(id)
            );

            create table if not exists quotations (
                id integer primary key autoincrement,
                filename text not null,
                customer text,
                quoted_on text,
                currency text not null default 'USD',
                stored_file_id integer,
                file_sha256 text,
                is_duplicate integer not null default 0,
                archived_at text,
                imported_at text not null default current_timestamp
            );

            create table if not exists line_items (
                id integer primary key autoincrement,
                quotation_id integer not null,
                catalog_no text not null,
                product_name text,
                unit_price real,
                quantity real,
                unit text,
                notes text,
                foreign key(quotation_id) references quotations(id)
            );

            """
        )
        _ensure_sqlite_columns(conn)
        _ensure_default_users(conn)


def _hash_default_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _ensure_default_users(conn: Any) -> None:
    for user in DEFAULT_USERS:
        existing = conn.execute("select id from users where lower(email) = lower(?)", (user["email"],)).fetchone()
        if existing:
            continue
        conn.execute(
            "insert into users (name, email, password_hash, role) values (?, ?, ?, ?)",
            (user["name"], user["email"], _hash_default_password(user["password"]), user["role"]),
        )


def _ensure_sqlite_columns(conn: sqlite3.Connection) -> None:
    def columns(table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}

    additions = {
        "users": {"password_hash": "text"},
        "import_files": {
            "stored_file_id": "integer",
            "file_sha256": "text",
            "is_duplicate": "integer not null default 0",
            "archived_at": "text",
        },
        "procurement_records": {"archived_at": "text"},
        "quotations": {
            "stored_file_id": "integer",
            "file_sha256": "text",
            "is_duplicate": "integer not null default 0",
            "archived_at": "text",
        },
    }
    for table, wanted in additions.items():
        existing = columns(table)
        for name, definition in wanted.items():
            if name not in existing:
                conn.execute(f"alter table {table} add column {name} {definition}")

    conn.executescript(
        """
        create table if not exists fx_rates (
            id integer primary key autoincrement,
            base_currency text not null,
            quote_currency text not null,
            rate numeric not null,
            effective_on text not null,
            created_by integer,
            created_at text not null default current_timestamp,
            unique(base_currency, quote_currency, effective_on)
        );

        create table if not exists alerts (
            id integer primary key autoincrement,
            catalog_no text not null,
            threshold_percent numeric not null,
            direction text not null default 'any',
            enabled integer not null default 1,
            created_by integer,
            created_at text not null default current_timestamp
        );

        create index if not exists idx_line_items_catalog_no on line_items(catalog_no);
        create index if not exists idx_line_items_quotation_id on line_items(quotation_id);
        create index if not exists idx_import_files_sha256 on import_files(file_sha256);
        create index if not exists idx_quotations_sha256 on quotations(file_sha256);
        """
    )


def row_to_dict(row: Any | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    if "synonyms" in data and isinstance(data["synonyms"], str):
        try:
            data["synonyms"] = json.loads(data["synonyms"])
        except json.JSONDecodeError:
            data["synonyms"] = []
    return data


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [row_to_dict(row) for row in rows if row is not None]


def find_or_create_material(candidate: dict, raw_name: str) -> int:
    cas = candidate.get("cas_number")
    standard_name = candidate.get("standard_name") or raw_name
    synonyms = candidate.get("synonyms") or [raw_name]
    match_status = candidate.get("match_status") or ("confirmed" if cas else "unresolved")

    with connect() as conn:
        if cas:
            existing = conn.execute("select id from materials where cas_number = ?", (cas,)).fetchone()
            if existing:
                return int(existing["id"])
        existing = conn.execute("select id from materials where lower(standard_name) = lower(?)", (standard_name,)).fetchone()
        if existing:
            return int(existing["id"])

        cur = conn.execute(
            """
            insert into materials (cas_number, standard_name, english_name, chinese_name, synonyms, match_status)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                cas,
                standard_name,
                candidate.get("english_name"),
                candidate.get("chinese_name"),
                json.dumps(sorted(set([*synonyms, raw_name])), ensure_ascii=False),
                match_status,
            ),
        )
        return int(cur.lastrowid)
