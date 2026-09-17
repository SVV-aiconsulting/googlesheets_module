"""
FastAPI backend мини-CRM.

Запуск:
    python crm.py
    # или
    uvicorn crm.api:app --reload
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

from crm.database import CRMDatabase
from crm.schemas import (
    ClientCreate,
    ClientOut,
    ClientUpdate,
    DealAttachClient,
    DealCreate,
    DealOut,
    DealUpdate,
    TaskCreate,
    TaskDoneBody,
    TaskOut,
    TaskUpdate,
)

_PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_DIR / ".env")

DB_PATH = Path(
    os.environ.get("CRM_DB_PATH", str(_PROJECT_DIR / "data" / "crm.db"))
)

db = CRMDatabase(DB_PATH)

app = FastAPI(
    title="Exelio Mini-CRM",
    description="MVP CRM: клиенты, сделки, задачи (SQLite + FastAPI)",
    version="0.1.0",
)


def _not_found(entity: str, entity_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} id={entity_id} не найден(а)")


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "db": str(DB_PATH)}


# ===================================================================== clients

@app.post("/clients", response_model=ClientOut, status_code=201)
def create_client(body: ClientCreate) -> ClientOut:
    try:
        return ClientOut.model_validate(
            db.create_client(**body.model_dump()).__dict__
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/clients", response_model=list[ClientOut])
def list_clients(
    status: Optional[str] = Query(None, description="active | archived"),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> list[ClientOut]:
    rows = db.list_clients(status=status, limit=limit, offset=offset)
    return [ClientOut.model_validate(r.__dict__) for r in rows]


@app.get("/clients/search", response_model=list[ClientOut])
def search_clients(
    q: str = Query(..., min_length=1, description="Подстрока (без учёта регистра)"),
    limit: int = Query(50, ge=1, le=5000),
) -> list[ClientOut]:
    rows = db.search_clients(q, limit=limit)
    return [ClientOut.model_validate(r.__dict__) for r in rows]


@app.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int) -> ClientOut:
    row = db.get_client(client_id)
    if not row:
        raise _not_found("Клиент", client_id)
    return ClientOut.model_validate(row.__dict__)


@app.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, body: ClientUpdate) -> ClientOut:
    try:
        row = db.update_client(
            client_id, **body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if not row:
        raise _not_found("Клиент", client_id)
    return ClientOut.model_validate(row.__dict__)


@app.post("/clients/{client_id}/archive", response_model=ClientOut)
def archive_client(client_id: int) -> ClientOut:
    row = db.archive_client(client_id)
    if not row:
        raise _not_found("Клиент", client_id)
    return ClientOut.model_validate(row.__dict__)


@app.post("/clients/{client_id}/restore", response_model=ClientOut)
def restore_client(client_id: int) -> ClientOut:
    row = db.restore_client(client_id)
    if not row:
        raise _not_found("Клиент", client_id)
    return ClientOut.model_validate(row.__dict__)


@app.delete("/clients/{client_id}", status_code=204)
def delete_client(client_id: int) -> None:
    if not db.delete_client(client_id):
        raise _not_found("Клиент", client_id)


# ======================================================================= deals

@app.post("/deals", response_model=DealOut, status_code=201)
def create_deal(body: DealCreate) -> DealOut:
    try:
        return DealOut.model_validate(db.create_deal(**body.model_dump()).__dict__)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/deals", response_model=list[DealOut])
def list_deals(
    status: Optional[str] = Query(None),
    client_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> list[DealOut]:
    rows = db.list_deals(
        status=status, client_id=client_id, limit=limit, offset=offset
    )
    return [DealOut.model_validate(r.__dict__) for r in rows]


@app.get("/deals/search", response_model=list[DealOut])
def search_deals(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=5000),
) -> list[DealOut]:
    rows = db.search_deals(q, limit=limit)
    return [DealOut.model_validate(r.__dict__) for r in rows]


@app.get("/deals/{deal_id}", response_model=DealOut)
def get_deal(deal_id: int) -> DealOut:
    row = db.get_deal(deal_id)
    if not row:
        raise _not_found("Сделка", deal_id)
    return DealOut.model_validate(row.__dict__)


@app.patch("/deals/{deal_id}", response_model=DealOut)
def update_deal(deal_id: int, body: DealUpdate) -> DealOut:
    try:
        row = db.update_deal(deal_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if not row:
        raise _not_found("Сделка", deal_id)
    return DealOut.model_validate(row.__dict__)


@app.post("/deals/{deal_id}/attach-client", response_model=DealOut)
def attach_client(deal_id: int, body: DealAttachClient) -> DealOut:
    try:
        row = db.attach_client_to_deal(deal_id, body.client_id)
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if not row:
        raise _not_found("Сделка", deal_id)
    return DealOut.model_validate(row.__dict__)


@app.delete("/deals/{deal_id}", status_code=204)
def delete_deal(deal_id: int) -> None:
    if not db.delete_deal(deal_id):
        raise _not_found("Сделка", deal_id)


# ======================================================================= tasks

@app.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate) -> TaskOut:
    try:
        return TaskOut.model_validate(db.create_task(**body.model_dump()).__dict__)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    is_done: Optional[bool] = Query(None),
    client_id: Optional[int] = Query(None),
    deal_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> list[TaskOut]:
    rows = db.list_tasks(
        is_done=is_done,
        client_id=client_id,
        deal_id=deal_id,
        limit=limit,
        offset=offset,
    )
    return [TaskOut.model_validate(r.__dict__) for r in rows]


@app.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int) -> TaskOut:
    row = db.get_task(task_id)
    if not row:
        raise _not_found("Задача", task_id)
    return TaskOut.model_validate(row.__dict__)


@app.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskUpdate) -> TaskOut:
    try:
        row = db.update_task(task_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if not row:
        raise _not_found("Задача", task_id)
    return TaskOut.model_validate(row.__dict__)


@app.post("/tasks/{task_id}/done", response_model=TaskOut)
def set_task_done(task_id: int, body: TaskDoneBody) -> TaskOut:
    row = db.set_task_done(task_id, is_done=body.is_done)
    if not row:
        raise _not_found("Задача", task_id)
    return TaskOut.model_validate(row.__dict__)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int) -> None:
    if not db.delete_task(task_id):
        raise _not_found("Задача", task_id)
