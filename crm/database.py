"""
SQLite 3 CRUD-слой мини-CRM.

При инициализации создаёт таблицы из crm.models, если их ещё нет.
Поиск без учёта регистра: LIKE … COLLATE NOCASE (аналог ILIKE в Postgres).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from crm.models import (
    ALL_DDL,
    CLIENT_STATUSES,
    DEAL_STATUSES,
    Client,
    Deal,
    Task,
)

PathLike = Union[str, Path]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_client(row: sqlite3.Row) -> Client:
    return Client(**dict(row))


def _row_to_deal(row: sqlite3.Row) -> Deal:
    return Deal(**dict(row))


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(**dict(row))


class CRMDatabase:
    """CRUD-операции над клиентами, сделками и задачами."""

    def __init__(self, db_path: PathLike = "data/crm.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        # SQLite COLLATE NOCASE не умеет кириллицу — свой LOWER через Python.
        conn.create_function(
            "ULOWER", 1, lambda value: value.lower() if isinstance(value, str) else value
        )
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            for statement in ALL_DDL:
                conn.execute(statement)
            conn.commit()

    # ================================================================== clients

    def create_client(
        self,
        name: str,
        *,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None,
        notes: Optional[str] = None,
        status: str = "active",
    ) -> Client:
        if status not in CLIENT_STATUSES:
            raise ValueError(f"Неверный status клиента: {status!r}")
        ts = _now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO clients (name, email, phone, company, notes, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name.strip(), email, phone, company, notes, status, ts, ts),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM clients WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return _row_to_client(row)

    def get_client(self, client_id: int) -> Optional[Client]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM clients WHERE id = ?", (client_id,)
            ).fetchone()
        return _row_to_client(row) if row else None

    def list_clients(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Client]:
        sql = "SELECT * FROM clients"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_client(r) for r in rows]

    def search_clients(self, query: str, *, limit: int = 50) -> list[Client]:
        """Поиск по name/email/phone/company (без учёта регистра, в т.ч. кириллица)."""
        q = f"%{query.strip()}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM clients
                WHERE ULOWER(COALESCE(name, ''))    LIKE ULOWER(?)
                   OR ULOWER(COALESCE(email, ''))   LIKE ULOWER(?)
                   OR ULOWER(COALESCE(phone, ''))   LIKE ULOWER(?)
                   OR ULOWER(COALESCE(company, '')) LIKE ULOWER(?)
                ORDER BY name COLLATE NOCASE
                LIMIT ?
                """,
                (q, q, q, q, limit),
            ).fetchall()
        return [_row_to_client(r) for r in rows]

    def update_client(self, client_id: int, **fields: Any) -> Optional[Client]:
        allowed = {"name", "email", "phone", "company", "notes", "status"}
        data = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "status" in data and data["status"] not in CLIENT_STATUSES:
            raise ValueError(f"Неверный status клиента: {data['status']!r}")
        if "name" in data:
            data["name"] = str(data["name"]).strip()
        if not data:
            return self.get_client(client_id)
        data["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in data)
        values = list(data.values()) + [client_id]
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE clients SET {cols} WHERE id = ?", values
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self.get_client(client_id)

    def archive_client(self, client_id: int) -> Optional[Client]:
        return self.update_client(client_id, status="archived")

    def restore_client(self, client_id: int) -> Optional[Client]:
        return self.update_client(client_id, status="active")

    def delete_client(self, client_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            conn.commit()
            return cur.rowcount > 0

    # ================================================================== deals

    def create_deal(
        self,
        title: str,
        *,
        description: Optional[str] = None,
        client_id: Optional[int] = None,
        amount: float = 0.0,
        currency: str = "RUB",
        status: str = "new",
    ) -> Deal:
        if status not in DEAL_STATUSES:
            raise ValueError(f"Неверный status сделки: {status!r}")
        if client_id is not None and self.get_client(client_id) is None:
            raise ValueError(f"Клиент id={client_id} не найден")
        ts = _now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO deals
                    (title, description, client_id, amount, currency, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    description,
                    client_id,
                    float(amount),
                    currency,
                    status,
                    ts,
                    ts,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM deals WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return _row_to_deal(row)

    def get_deal(self, deal_id: int) -> Optional[Deal]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM deals WHERE id = ?", (deal_id,)
            ).fetchone()
        return _row_to_deal(row) if row else None

    def list_deals(
        self,
        *,
        status: Optional[str] = None,
        client_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Deal]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if client_id is not None:
            clauses.append("client_id = ?")
            params.append(client_id)
        sql = "SELECT * FROM deals"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_deal(r) for r in rows]

    def search_deals(self, query: str, *, limit: int = 50) -> list[Deal]:
        q = f"%{query.strip()}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM deals
                WHERE ULOWER(COALESCE(title, ''))       LIKE ULOWER(?)
                   OR ULOWER(COALESCE(description, '')) LIKE ULOWER(?)
                ORDER BY title COLLATE NOCASE
                LIMIT ?
                """,
                (q, q, limit),
            ).fetchall()
        return [_row_to_deal(r) for r in rows]

    def update_deal(self, deal_id: int, **fields: Any) -> Optional[Deal]:
        allowed = {
            "title",
            "description",
            "client_id",
            "amount",
            "currency",
            "status",
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        # Явно разрешаем сброс client_id в NULL
        if "client_id" in fields and fields["client_id"] is None:
            data["client_id"] = None
        elif "client_id" in data and data["client_id"] is not None:
            if self.get_client(int(data["client_id"])) is None:
                raise ValueError(f"Клиент id={data['client_id']} не найден")
        if "status" in data and data["status"] not in DEAL_STATUSES:
            raise ValueError(f"Неверный status сделки: {data['status']!r}")
        if "title" in data and data["title"] is not None:
            data["title"] = str(data["title"]).strip()
        if "amount" in data and data["amount"] is not None:
            data["amount"] = float(data["amount"])
        # убрать ключи со значением ... только если не client_id null
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if k == "client_id" or v is not None:
                cleaned[k] = v
        if not cleaned:
            return self.get_deal(deal_id)
        cleaned["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in cleaned)
        values = list(cleaned.values()) + [deal_id]
        with self.connect() as conn:
            cur = conn.execute(f"UPDATE deals SET {cols} WHERE id = ?", values)
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self.get_deal(deal_id)

    def attach_client_to_deal(
        self, deal_id: int, client_id: Optional[int]
    ) -> Optional[Deal]:
        return self.update_deal(deal_id, client_id=client_id)

    def delete_deal(self, deal_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
            conn.commit()
            return cur.rowcount > 0

    # ================================================================== tasks

    def create_task(
        self,
        title: str,
        *,
        description: Optional[str] = None,
        client_id: Optional[int] = None,
        deal_id: Optional[int] = None,
        due_at: Optional[str] = None,
        is_done: bool = False,
    ) -> Task:
        if client_id is not None and self.get_client(client_id) is None:
            raise ValueError(f"Клиент id={client_id} не найден")
        if deal_id is not None and self.get_deal(deal_id) is None:
            raise ValueError(f"Сделка id={deal_id} не найдена")
        ts = _now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks
                    (title, description, client_id, deal_id, due_at, is_done, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    description,
                    client_id,
                    deal_id,
                    due_at,
                    1 if is_done else 0,
                    ts,
                    ts,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return _row_to_task(row)

    def get_task(self, task_id: int) -> Optional[Task]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        is_done: Optional[bool] = None,
        client_id: Optional[int] = None,
        deal_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        clauses: list[str] = []
        params: list[Any] = []
        if is_done is not None:
            clauses.append("is_done = ?")
            params.append(1 if is_done else 0)
        if client_id is not None:
            clauses.append("client_id = ?")
            params.append(client_id)
        if deal_id is not None:
            clauses.append("deal_id = ?")
            params.append(deal_id)
        sql = "SELECT * FROM tasks"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY is_done ASC, due_at IS NULL, due_at ASC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_task(r) for r in rows]

    def update_task(self, task_id: int, **fields: Any) -> Optional[Task]:
        allowed = {
            "title",
            "description",
            "client_id",
            "deal_id",
            "due_at",
            "is_done",
        }
        data: dict[str, Any] = {}
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k in {"client_id", "deal_id", "due_at"}:
                data[k] = v  # допускаем NULL
            elif v is not None:
                data[k] = v
        if "is_done" in data:
            data["is_done"] = 1 if data["is_done"] in (True, 1, "1", "true") else 0
        if "title" in data and data["title"] is not None:
            data["title"] = str(data["title"]).strip()
        if "client_id" in data and data["client_id"] is not None:
            if self.get_client(int(data["client_id"])) is None:
                raise ValueError(f"Клиент id={data['client_id']} не найден")
        if "deal_id" in data and data["deal_id"] is not None:
            if self.get_deal(int(data["deal_id"])) is None:
                raise ValueError(f"Сделка id={data['deal_id']} не найдена")
        if not data:
            return self.get_task(task_id)
        data["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in data)
        values = list(data.values()) + [task_id]
        with self.connect() as conn:
            cur = conn.execute(f"UPDATE tasks SET {cols} WHERE id = ?", values)
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self.get_task(task_id)

    def set_task_done(self, task_id: int, is_done: bool = True) -> Optional[Task]:
        return self.update_task(task_id, is_done=is_done)

    def delete_task(self, task_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cur.rowcount > 0
