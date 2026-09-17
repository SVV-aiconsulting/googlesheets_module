"""
Настройки Google для CRM GUI.

Пути к JSON и ID папки хранятся в текстовом файле
``data/google_gui_settings.txt`` и подставляются в os.environ
перед вызовом Drive/Sheets клиентов.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = _ROOT / "data" / "google_gui_settings.txt"

KEYS = (
    "GOOGLE_OAUTH_CLIENT_SECRET_PATH",
    "GOOGLE_OAUTH_TOKEN_PATH",
    "GOOGLE_DRIVE_FOLDER_ID",
)


def load_google_settings() -> dict[str, str]:
    data = {k: (os.environ.get(k) or "").strip() for k in KEYS}
    if not SETTINGS_PATH.is_file():
        return data
    for line in SETTINGS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in KEYS:
            data[key] = value.strip()
    return data


def save_google_settings(values: dict[str, str]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Настройки Google CRM GUI — не коммитьте секреты при необходимости",
        f"GOOGLE_OAUTH_CLIENT_SECRET_PATH={values.get('GOOGLE_OAUTH_CLIENT_SECRET_PATH', '')}",
        f"GOOGLE_OAUTH_TOKEN_PATH={values.get('GOOGLE_OAUTH_TOKEN_PATH', '')}",
        f"GOOGLE_DRIVE_FOLDER_ID={values.get('GOOGLE_DRIVE_FOLDER_ID', '')}",
        "",
    ]
    SETTINGS_PATH.write_text("\n".join(lines), encoding="utf-8")
    apply_google_settings(values)


def apply_google_settings(values: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Прописать настройки в os.environ для клиентов integrations/."""
    data = values if values is not None else load_google_settings()
    for key in KEYS:
        val = (data.get(key) or "").strip()
        if val:
            os.environ[key] = val
    return data


class GoogleSettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("Настройки Google")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        current = load_google_settings()
        body = ttk.Frame(self, padding=12)
        body.grid(sticky="nsew")

        self.oauth_var = tk.StringVar(value=current.get("GOOGLE_OAUTH_CLIENT_SECRET_PATH", ""))
        self.token_var = tk.StringVar(value=current.get("GOOGLE_OAUTH_TOKEN_PATH", ""))
        self.folder_var = tk.StringVar(value=current.get("GOOGLE_DRIVE_FOLDER_ID", ""))

        ttk.Label(body, text="OAuth client_secret JSON").grid(row=0, column=0, sticky="w", pady=4)
        row0 = ttk.Frame(body)
        row0.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)
        ttk.Entry(row0, textvariable=self.oauth_var, width=48).pack(side="left", fill="x", expand=True)
        ttk.Button(row0, text="Обзор…", command=self._browse_oauth).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="OAuth token.json").grid(row=1, column=0, sticky="w", pady=4)
        row1 = ttk.Frame(body)
        row1.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=4)
        ttk.Entry(row1, textvariable=self.token_var, width=48).pack(side="left", fill="x", expand=True)
        ttk.Button(row1, text="Обзор…", command=self._browse_token).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="ID папки Drive").grid(row=2, column=0, sticky="w", pady=4)
        row2 = ttk.Frame(body)
        row2.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=4)
        self.folder_entry = ttk.Entry(row2, textvariable=self.folder_var, width=48)
        self.folder_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Вставить", command=self._paste_folder).pack(side="left", padx=(6, 0))

        hint = (
            "ID папки — хвост URL после /folders/\n"
            "При первом экспорте откроется браузер OAuth (личный аккаунт)."
        )
        ttk.Label(body, text=hint, foreground="#64748B").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        btns = ttk.Frame(body)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="right", padx=(0, 8))

        self.wait_visibility()
        self.focus_force()

    def _browse_oauth(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="OAuth client_secret JSON",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
            initialdir=str(_ROOT / "credentials"),
        )
        if path:
            self.oauth_var.set(self._rel_or_abs(path))

    def _browse_token(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Файл token.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
            initialdir=str(_ROOT / "credentials"),
            initialfile="token.json",
        )
        if path:
            self.token_var.set(self._rel_or_abs(path))

    def _paste_folder(self) -> None:
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            messagebox.showwarning("Буфер", "Буфер обмена пуст", parent=self)
            return
        # Если вставили полный URL — вытащить ID
        if "/folders/" in text:
            text = text.split("/folders/", 1)[1].split("?", 1)[0].split("/", 1)[0]
        self.folder_var.set(text)
        self.folder_entry.focus_set()

    @staticmethod
    def _rel_or_abs(path: str) -> str:
        p = Path(path)
        try:
            return str(p.resolve().relative_to(_ROOT.resolve())).replace("\\", "/")
        except ValueError:
            return str(p)

    def _save(self) -> None:
        values = {
            "GOOGLE_OAUTH_CLIENT_SECRET_PATH": self.oauth_var.get().strip(),
            "GOOGLE_OAUTH_TOKEN_PATH": self.token_var.get().strip(),
            "GOOGLE_DRIVE_FOLDER_ID": self.folder_var.get().strip(),
        }
        if not values["GOOGLE_OAUTH_CLIENT_SECRET_PATH"]:
            messagebox.showerror("Ошибка", "Укажите client_secret JSON", parent=self)
            return
        if not values["GOOGLE_OAUTH_TOKEN_PATH"]:
            values["GOOGLE_OAUTH_TOKEN_PATH"] = "credentials/token.json"
        if not values["GOOGLE_DRIVE_FOLDER_ID"]:
            messagebox.showerror("Ошибка", "Укажите ID рабочей папки Drive", parent=self)
            return
        save_google_settings(values)
        messagebox.showinfo(
            "Сохранено",
            f"Настройки записаны в:\n{SETTINGS_PATH}",
            parent=self,
        )
        self.destroy()
