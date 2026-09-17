"""
Tkinter-клиент мини-CRM: таблицы + формы, все данные через локальный FastAPI.

Запуск (сначала поднимите API):
    python crm.py
    python ui/crm_app.py
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv(_ROOT / ".env")

from api_client import ApiError, CrmApiClient  # noqa: E402
from google_settings import GoogleSettingsDialog, apply_google_settings  # noqa: E402
from report_export import collect_tree_rows, export_table_report  # noqa: E402

API_URL = os.environ.get("CRM_API_URL", "http://127.0.0.1:8000").strip()

CLIENT_STATUSES = ("active", "archived")
DEAL_STATUSES = ("new", "in_progress", "won", "lost", "cancelled")

apply_google_settings()


def show_export_success(master: tk.Misc, meta: dict) -> None:
    """Окно успеха: ссылка на таблицу + кнопка «Открыть» в браузере."""
    import webbrowser

    sheet_id = str(meta.get("id") or "").strip()
    link = (meta.get("webViewLink") or "").strip()
    if not link and sheet_id:
        link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    if link and not link.startswith("http") and sheet_id:
        link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    dlg = tk.Toplevel(master)
    dlg.title("Отчёт выгружен")
    dlg.minsize(520, 220)
    dlg.resizable(True, False)
    dlg.transient(master)
    dlg.grab_set()

    body = ttk.Frame(dlg, padding=14)
    body.pack(fill="both", expand=True)

    ttk.Label(body, text="Таблица создана", font=("Segoe UI", 11, "bold")).pack(anchor="w")
    ttk.Label(body, text=f"Имя: {meta.get('name') or '—'}").pack(anchor="w", pady=(8, 0))
    ttk.Label(body, text=f"Записей: {meta.get('count', 0)}").pack(anchor="w", pady=(2, 0))
    ttk.Label(body, text="Ссылка:").pack(anchor="w", pady=(10, 2))

    # Перенос строки — длинный URL всегда виден (Entry часто «прячет» хвост)
    ttk.Label(
        body,
        text=link or "(ссылка не получена)",
        foreground="#0F766E" if link else "#94A3B8",
        wraplength=480,
        justify="left",
    ).pack(anchor="w", fill="x")

    link_var = tk.StringVar(value=link)
    entry = ttk.Entry(body, textvariable=link_var)
    entry.pack(fill="x", pady=(8, 0))
    entry.icursor(0)
    entry.xview_moveto(0)

    def open_link() -> None:
        if link:
            webbrowser.open(link)

    def copy_link() -> None:
        if not link:
            return
        dlg.clipboard_clear()
        dlg.clipboard_append(link)
        dlg.update()

    btns = ttk.Frame(body)
    btns.pack(fill="x", pady=(14, 0))
    ttk.Button(btns, text="Закрыть", command=dlg.destroy).pack(side="right")
    ttk.Button(btns, text="Копировать ссылку", command=copy_link).pack(side="right", padx=(0, 8))
    open_btn = ttk.Button(btns, text="Открыть", command=open_link)
    open_btn.pack(side="right", padx=(0, 8))
    if not link:
        open_btn.state(["disabled"])

    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    dlg.update_idletasks()
    try:
        dlg.geometry(f"+{master.winfo_rootx() + 40}+{master.winfo_rooty() + 40}")
    except tk.TclError:
        pass
    dlg.wait_visibility()
    dlg.focus_force()


# ---------------------------------------------------------------------------
# Диалоги форм
# ---------------------------------------------------------------------------


class FormDialog(tk.Toplevel):
    """Простая форма: список (label, widget_factory) → dict значений."""

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        fields: list[tuple[str, str, Any]],
        initial: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        fields: (key, label, kind)
          kind: 'str' | 'text' | ('choice', [...]) | 'int' | 'float' | 'bool'
        """
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: Optional[dict[str, Any]] = None
        self._vars: dict[str, Any] = {}
        initial = initial or {}

        body = ttk.Frame(self, padding=12)
        body.grid(sticky="nsew")

        for row, (key, label, kind) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=4)
            init_val = initial.get(key, "")
            if kind == "text":
                widget = tk.Text(body, width=40, height=4)
                if init_val:
                    widget.insert("1.0", str(init_val))
                widget.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
                self._vars[key] = ("text", widget)
            elif isinstance(kind, tuple) and kind[0] == "choice":
                var = tk.StringVar(value=str(init_val if init_val != "" else kind[1][0]))
                cb = ttk.Combobox(
                    body, textvariable=var, values=list(kind[1]), state="readonly", width=37
                )
                cb.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
                self._vars[key] = ("var", var)
            elif kind == "bool":
                var = tk.BooleanVar(value=bool(init_val))
                ttk.Checkbutton(body, variable=var).grid(
                    row=row, column=1, sticky="w", pady=4, padx=(8, 0)
                )
                self._vars[key] = ("bool", var)
            else:
                var = tk.StringVar(
                    value="" if init_val is None else str(init_val)
                )
                ttk.Entry(body, textvariable=var, width=40).grid(
                    row=row, column=1, sticky="ew", pady=4, padx=(8, 0)
                )
                self._vars[key] = (kind, var)

        btns = ttk.Frame(body)
        btns.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Сохранить", command=self._ok).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_visibility()
        self.focus_force()

    def _ok(self) -> None:
        data: dict[str, Any] = {}
        for key, (kind, widget) in self._vars.items():
            if kind == "text":
                data[key] = widget.get("1.0", "end").strip()
            elif kind == "bool":
                data[key] = bool(widget.get())
            elif kind == "int":
                raw = widget.get().strip()
                data[key] = int(raw) if raw else None
            elif kind == "float":
                raw = widget.get().strip().replace(",", ".")
                data[key] = float(raw) if raw else 0.0
            else:
                data[key] = widget.get().strip()
        self.result = data
        self.destroy()


# ---------------------------------------------------------------------------
# Вкладки
# ---------------------------------------------------------------------------


class ClientsTab(ttk.Frame):
    COLS = ("id", "name", "phone", "email", "company", "status")
    HEADINGS = {
        "id": "ID",
        "name": "Имя",
        "phone": "Телефон",
        "email": "Email",
        "company": "Компания",
        "status": "Статус",
    }

    def __init__(
        self,
        master: tk.Misc,
        api: CrmApiClient,
        on_error: Callable[[str], None],
        on_status: Callable[[str], None],
    ) -> None:
        super().__init__(master, padding=8)
        self.api = api
        self.on_error = on_error
        self.on_status = on_status
        self._build()

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.search_var, width=28).pack(side="left")
        ttk.Button(bar, text="Найти", command=self.reload).pack(side="left", padx=4)
        ttk.Button(bar, text="Сброс", command=self._reset).pack(side="left")
        ttk.Button(bar, text="Выгрузить отчёт", command=self.export_report).pack(side="left", padx=(12, 0))
        ttk.Button(bar, text="Создать", command=self.create).pack(side="right")
        ttk.Button(bar, text="Изменить", command=self.edit).pack(side="right", padx=4)
        ttk.Button(bar, text="Архив", command=self.archive).pack(side="right")
        ttk.Button(bar, text="Восстановить", command=self.restore).pack(side="right", padx=4)
        ttk.Button(bar, text="Удалить", command=self.delete).pack(side="right")

        self.tree = ttk.Treeview(self, columns=self.COLS, show="headings", height=18)
        widths = {"id": 50, "name": 160, "phone": 110, "email": 160, "company": 140, "status": 90}
        for col in self.COLS:
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=widths[col], anchor="w")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.edit())

    def export_report(self) -> None:
        rows = collect_tree_rows(self.tree, self.COLS)
        if not rows:
            messagebox.showinfo("Отчёт", "Таблица пуста — нечего выгружать")
            return
        self.on_status("Выгрузка отчёта клиентов в Google Sheets…")

        def worker() -> None:
            try:
                meta = export_table_report(
                    report_title="CRM — Клиенты",
                    columns=self.COLS,
                    headings=self.HEADINGS,
                    rows=rows,
                )
                self.after(0, lambda: self._export_done(meta))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self.on_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _export_done(self, meta: dict) -> None:
        self.on_status(f"Отчёт создан: {meta.get('name')} ({meta.get('count')} строк)")
        show_export_success(self.winfo_toplevel(), meta)

    def _selected_id(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def _reset(self) -> None:
        self.search_var.set("")
        self.reload()

    def reload(self) -> None:
        try:
            q = self.search_var.get().strip()
            rows = self.api.search_clients(q) if q else self.api.list_clients()
        except ApiError as exc:
            self.on_error(str(exc))
            return
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row.get("name") or "",
                    row.get("phone") or "",
                    row.get("email") or "",
                    row.get("company") or "",
                    row.get("status") or "",
                ),
            )

    def create(self) -> None:
        dlg = FormDialog(
            self,
            "Новый клиент",
            [
                ("name", "Имя *", "str"),
                ("phone", "Телефон", "str"),
                ("email", "Email", "str"),
                ("company", "Компания", "str"),
                ("notes", "Заметки", "text"),
                ("status", "Статус", ("choice", CLIENT_STATUSES)),
            ],
        )
        self.wait_window(dlg)
        if not dlg.result or not dlg.result.get("name"):
            return
        try:
            self.api.create_client(dlg.result)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def edit(self) -> None:
        cid = self._selected_id()
        if cid is None:
            messagebox.showinfo("Клиенты", "Выберите клиента в таблице")
            return
        values = self.tree.item(self.tree.selection()[0], "values")
        dlg = FormDialog(
            self,
            f"Клиент #{cid}",
            [
                ("name", "Имя *", "str"),
                ("phone", "Телефон", "str"),
                ("email", "Email", "str"),
                ("company", "Компания", "str"),
                ("notes", "Заметки", "text"),
                ("status", "Статус", ("choice", CLIENT_STATUSES)),
            ],
            initial={
                "name": values[1],
                "phone": values[2],
                "email": values[3],
                "company": values[4],
                "status": values[5],
            },
        )
        self.wait_window(dlg)
        if not dlg.result:
            return
        try:
            self.api.update_client(cid, dlg.result)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def archive(self) -> None:
        cid = self._selected_id()
        if cid is None:
            return
        try:
            self.api.archive_client(cid)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def restore(self) -> None:
        cid = self._selected_id()
        if cid is None:
            return
        try:
            self.api.restore_client(cid)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def delete(self) -> None:
        cid = self._selected_id()
        if cid is None:
            return
        if not messagebox.askyesno("Удалить", f"Удалить клиента #{cid} безвозвратно?"):
            return
        try:
            self.api.delete_client(cid)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))


class DealsTab(ttk.Frame):
    COLS = ("id", "title", "client_id", "amount", "currency", "status")
    HEADINGS = {
        "id": "ID",
        "title": "Название",
        "client_id": "Клиент ID",
        "amount": "Сумма",
        "currency": "Валюта",
        "status": "Статус",
    }

    def __init__(
        self,
        master: tk.Misc,
        api: CrmApiClient,
        on_error: Callable[[str], None],
        on_status: Callable[[str], None],
    ) -> None:
        super().__init__(master, padding=8)
        self.api = api
        self.on_error = on_error
        self.on_status = on_status
        self._build()

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.search_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.search_var, width=28).pack(side="left")
        ttk.Button(bar, text="Найти", command=self.reload).pack(side="left", padx=4)
        ttk.Button(bar, text="Сброс", command=self._reset).pack(side="left")
        ttk.Button(bar, text="Выгрузить отчёт", command=self.export_report).pack(side="left", padx=(12, 0))
        ttk.Button(bar, text="Создать", command=self.create).pack(side="right")
        ttk.Button(bar, text="Изменить", command=self.edit).pack(side="right", padx=4)
        ttk.Button(bar, text="Клиент…", command=self.attach).pack(side="right")
        ttk.Button(bar, text="Удалить", command=self.delete).pack(side="right", padx=4)

        self.tree = ttk.Treeview(self, columns=self.COLS, show="headings", height=18)
        widths = {"id": 50, "title": 200, "client_id": 80, "amount": 90, "currency": 70, "status": 100}
        for col in self.COLS:
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=widths[col], anchor="w")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.edit())

    def export_report(self) -> None:
        rows = collect_tree_rows(self.tree, self.COLS)
        if not rows:
            messagebox.showinfo("Отчёт", "Таблица пуста — нечего выгружать")
            return
        self.on_status("Выгрузка отчёта сделок в Google Sheets…")

        def worker() -> None:
            try:
                meta = export_table_report(
                    report_title="CRM — Сделки",
                    columns=self.COLS,
                    headings=self.HEADINGS,
                    rows=rows,
                )
                self.after(0, lambda: self._export_done(meta))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self.on_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _export_done(self, meta: dict) -> None:
        self.on_status(f"Отчёт создан: {meta.get('name')} ({meta.get('count')} строк)")
        show_export_success(self.winfo_toplevel(), meta)

    def _selected_id(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def _reset(self) -> None:
        self.search_var.set("")
        self.reload()

    def reload(self) -> None:
        try:
            q = self.search_var.get().strip()
            rows = self.api.search_deals(q) if q else self.api.list_deals()
        except ApiError as exc:
            self.on_error(str(exc))
            return
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row.get("title") or "",
                    row.get("client_id") if row.get("client_id") is not None else "",
                    row.get("amount") if row.get("amount") is not None else "",
                    row.get("currency") or "",
                    row.get("status") or "",
                ),
            )

    def create(self) -> None:
        dlg = FormDialog(
            self,
            "Новая сделка",
            [
                ("title", "Название *", "str"),
                ("description", "Описание", "text"),
                ("client_id", "ID клиента", "int"),
                ("amount", "Сумма", "float"),
                ("currency", "Валюта", "str"),
                ("status", "Статус", ("choice", DEAL_STATUSES)),
            ],
            initial={"currency": "RUB", "status": "new", "amount": "0"},
        )
        self.wait_window(dlg)
        if not dlg.result or not dlg.result.get("title"):
            return
        try:
            self.api.create_deal(dlg.result)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def edit(self) -> None:
        did = self._selected_id()
        if did is None:
            messagebox.showinfo("Сделки", "Выберите сделку")
            return
        values = self.tree.item(self.tree.selection()[0], "values")
        dlg = FormDialog(
            self,
            f"Сделка #{did}",
            [
                ("title", "Название *", "str"),
                ("description", "Описание", "text"),
                ("client_id", "ID клиента", "int"),
                ("amount", "Сумма", "float"),
                ("currency", "Валюта", "str"),
                ("status", "Статус", ("choice", DEAL_STATUSES)),
            ],
            initial={
                "title": values[1],
                "client_id": values[2],
                "amount": values[3],
                "currency": values[4],
                "status": values[5],
            },
        )
        self.wait_window(dlg)
        if not dlg.result:
            return
        try:
            self.api.update_deal(did, dlg.result)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def attach(self) -> None:
        did = self._selected_id()
        if did is None:
            return
        dlg = FormDialog(
            self,
            f"Прикрепить клиента к сделке #{did}",
            [("client_id", "ID клиента (пусто = отвязать)", "int")],
        )
        self.wait_window(dlg)
        if dlg.result is None:
            return
        try:
            self.api.attach_client(did, dlg.result.get("client_id"))
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def delete(self) -> None:
        did = self._selected_id()
        if did is None:
            return
        if not messagebox.askyesno("Удалить", f"Удалить сделку #{did}?"):
            return
        try:
            self.api.delete_deal(did)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))


class TasksTab(ttk.Frame):
    COLS = ("id", "title", "client_id", "deal_id", "due_at", "is_done")
    HEADINGS = {
        "id": "ID",
        "title": "Задача",
        "client_id": "Клиент",
        "deal_id": "Сделка",
        "due_at": "Срок",
        "is_done": "Готово",
    }

    def __init__(
        self,
        master: tk.Misc,
        api: CrmApiClient,
        on_error: Callable[[str], None],
        on_status: Callable[[str], None],
    ) -> None:
        super().__init__(master, padding=8)
        self.api = api
        self.on_error = on_error
        self.on_status = on_status
        self._build()

    def _build(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.filter_var = tk.StringVar(value="all")
        ttk.Label(bar, text="Фильтр:").pack(side="left")
        ttk.Combobox(
            bar,
            textvariable=self.filter_var,
            values=("all", "open", "done"),
            state="readonly",
            width=10,
        ).pack(side="left", padx=4)
        ttk.Button(bar, text="Обновить", command=self.reload).pack(side="left")
        ttk.Button(bar, text="Выгрузить отчёт", command=self.export_report).pack(side="left", padx=(12, 0))
        ttk.Button(bar, text="Создать", command=self.create).pack(side="right")
        ttk.Button(bar, text="Изменить", command=self.edit).pack(side="right", padx=4)
        ttk.Button(bar, text="Выполнено", command=lambda: self.set_done(True)).pack(side="right")
        ttk.Button(bar, text="Не выполнено", command=lambda: self.set_done(False)).pack(
            side="right", padx=4
        )
        ttk.Button(bar, text="Удалить", command=self.delete).pack(side="right")

        self.tree = ttk.Treeview(self, columns=self.COLS, show="headings", height=18)
        widths = {"id": 50, "title": 220, "client_id": 70, "deal_id": 70, "due_at": 130, "is_done": 70}
        for col in self.COLS:
            self.tree.heading(col, text=self.HEADINGS[col])
            self.tree.column(col, width=widths[col], anchor="w")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.edit())

    def export_report(self) -> None:
        rows = collect_tree_rows(self.tree, self.COLS)
        if not rows:
            messagebox.showinfo("Отчёт", "Таблица пуста — нечего выгружать")
            return
        self.on_status("Выгрузка отчёта задач в Google Sheets…")

        def worker() -> None:
            try:
                meta = export_table_report(
                    report_title="CRM — Задачи",
                    columns=self.COLS,
                    headings=self.HEADINGS,
                    rows=rows,
                )
                self.after(0, lambda: self._export_done(meta))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self.on_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _export_done(self, meta: dict) -> None:
        self.on_status(f"Отчёт создан: {meta.get('name')} ({meta.get('count')} строк)")
        show_export_success(self.winfo_toplevel(), meta)

    def _selected_id(self) -> Optional[int]:
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def reload(self) -> None:
        filt = self.filter_var.get()
        is_done: Optional[bool]
        if filt == "open":
            is_done = False
        elif filt == "done":
            is_done = True
        else:
            is_done = None
        try:
            rows = self.api.list_tasks(is_done=is_done)
        except ApiError as exc:
            self.on_error(str(exc))
            return
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row.get("title") or "",
                    row.get("client_id") if row.get("client_id") is not None else "",
                    row.get("deal_id") if row.get("deal_id") is not None else "",
                    row.get("due_at") or "",
                    "да" if row.get("is_done") else "нет",
                ),
            )

    def create(self) -> None:
        dlg = FormDialog(
            self,
            "Новая задача",
            [
                ("title", "Название *", "str"),
                ("description", "Описание", "text"),
                ("client_id", "ID клиента", "int"),
                ("deal_id", "ID сделки", "int"),
                ("due_at", "Срок (YYYY-MM-DD HH:MM)", "str"),
                ("is_done", "Выполнено", "bool"),
            ],
        )
        self.wait_window(dlg)
        if not dlg.result or not dlg.result.get("title"):
            return
        try:
            self.api.create_task(dlg.result)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def edit(self) -> None:
        tid = self._selected_id()
        if tid is None:
            messagebox.showinfo("Задачи", "Выберите задачу")
            return
        values = self.tree.item(self.tree.selection()[0], "values")
        dlg = FormDialog(
            self,
            f"Задача #{tid}",
            [
                ("title", "Название *", "str"),
                ("description", "Описание", "text"),
                ("client_id", "ID клиента", "int"),
                ("deal_id", "ID сделки", "int"),
                ("due_at", "Срок (YYYY-MM-DD HH:MM)", "str"),
                ("is_done", "Выполнено", "bool"),
            ],
            initial={
                "title": values[1],
                "client_id": values[2],
                "deal_id": values[3],
                "due_at": values[4],
                "is_done": values[5] == "да",
            },
        )
        self.wait_window(dlg)
        if not dlg.result:
            return
        try:
            self.api.update_task(tid, dlg.result)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def set_done(self, done: bool) -> None:
        tid = self._selected_id()
        if tid is None:
            return
        try:
            self.api.set_task_done(tid, done)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))

    def delete(self) -> None:
        tid = self._selected_id()
        if tid is None:
            return
        if not messagebox.askyesno("Удалить", f"Удалить задачу #{tid}?"):
            return
        try:
            self.api.delete_task(tid)
            self.reload()
        except ApiError as exc:
            self.on_error(str(exc))


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------


class CrmApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Exelio Mini-CRM")
        self.geometry("980x560")
        self.minsize(820, 480)

        self.api = CrmApiClient(API_URL)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Exelio CRM", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(top, text="Обновить всё", command=self.reload_all).pack(side="right")
        ttk.Button(top, text="Проверить API", command=self.check_api).pack(side="right", padx=6)
        ttk.Button(top, text="Настройки Google", command=self.open_google_settings).pack(
            side="right", padx=6
        )

        self.status = tk.StringVar(value=f"API: {API_URL}")
        ttk.Label(self, textvariable=self.status, foreground="#475569", padding=(10, 0)).pack(
            fill="x"
        )

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.clients = ClientsTab(notebook, self.api, self._error, self._set_status)
        self.deals = DealsTab(notebook, self.api, self._error, self._set_status)
        self.tasks = TasksTab(notebook, self.api, self._error, self._set_status)
        notebook.add(self.clients, text="Клиенты")
        notebook.add(self.deals, text="Сделки")
        notebook.add(self.tasks, text="Задачи")

        self.after(200, self.bootstrap)

    def _set_status(self, message: str) -> None:
        self.status.set(message[:160])

    def open_google_settings(self) -> None:
        GoogleSettingsDialog(self)

    def _error(self, message: str) -> None:
        self.status.set(message.split("\n")[0][:120])
        messagebox.showerror("Ошибка", message)

    def check_api(self) -> None:
        try:
            info = self.api.health()
            self.status.set(f"OK · {info.get('status')} · db={info.get('db')}")
            messagebox.showinfo("API", f"Сервер доступен\n{info}")
        except ApiError as exc:
            self._error(str(exc))

    def reload_all(self) -> None:
        self.clients.reload()
        self.deals.reload()
        self.tasks.reload()
        self.status.set(f"Данные обновлены · {API_URL}")

    def bootstrap(self) -> None:
        try:
            self.api.health()
            self.reload_all()
            self.status.set(f"Подключено · {API_URL}")
        except ApiError as exc:
            self.status.set("API недоступен — запустите: python crm.py")
            messagebox.showwarning(
                "Нет соединения",
                f"{exc}\n\nСначала запустите бэкенд:\n  python crm.py",
            )


def main() -> None:
    app = CrmApp()
    app.mainloop()


if __name__ == "__main__":
    main()
