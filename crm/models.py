"""
Модели и DDL для мини-CRM (SQLite 3).

Типы SQLite:
  INTEGER, REAL, TEXT, BLOB, NULL
Булевы значения храним как INTEGER 0/1.
Даты/время — TEXT в ISO-8601 (YYYY-MM-DD HH:MM:SS).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Статусы / константы
# ---------------------------------------------------------------------------

CLIENT_STATUSES = ("active", "archived")
DEAL_STATUSES = ("new", "in_progress", "won", "lost", "cancelled")

# ---------------------------------------------------------------------------
# Dataclass-модели строк (удобно маппить из sqlite3.Row)
# ---------------------------------------------------------------------------


@dataclass
class Client:
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Deal:
    id: int
    title: str
    description: Optional[str] = None
    client_id: Optional[int] = None
    amount: float = 0.0
    currency: str = "RUB"
    status: str = "new"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Task:
    id: int
    title: str
    description: Optional[str] = None
    client_id: Optional[int] = None
    deal_id: Optional[int] = None
    due_at: Optional[str] = None
    is_done: int = 0  # 0 / 1
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# DDL — создаются при инициализации CRMDatabase, если таблиц ещё нет
# ---------------------------------------------------------------------------

DDL_CLIENTS = """
CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT,
    phone       TEXT,
    company     TEXT,
    notes       TEXT,
    status      TEXT    NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'archived')),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

DDL_DEALS = """
CREATE TABLE IF NOT EXISTS deals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT,
    client_id   INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    amount      REAL    NOT NULL DEFAULT 0,
    currency    TEXT    NOT NULL DEFAULT 'RUB',
    status      TEXT    NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'in_progress', 'won', 'lost', 'cancelled')),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

DDL_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT,
    client_id   INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    deal_id     INTEGER REFERENCES deals(id) ON DELETE SET NULL,
    due_at      TEXT,
    is_done     INTEGER NOT NULL DEFAULT 0
                        CHECK (is_done IN (0, 1)),
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

DDL_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);",
    "CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name COLLATE NOCASE);",
    "CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status);",
    "CREATE INDEX IF NOT EXISTS idx_deals_client ON deals(client_id);",
    "CREATE INDEX IF NOT EXISTS idx_deals_title ON deals(title COLLATE NOCASE);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(is_done);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_client ON tasks(client_id);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_deal ON tasks(deal_id);",
)

ALL_DDL: tuple[str, ...] = (DDL_CLIENTS, DDL_DEALS, DDL_TASKS, *DDL_INDEXES)
