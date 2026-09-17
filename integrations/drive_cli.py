"""
Интерактивное CLI-меню для создания папок и файлов на Google Drive.

Запуск:
    python drive_cli.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from google_drive_client import (
    DEFAULT_FOLDER_ID,
    GoogleDriveClient,
    _print_created,
    _print_files,
)


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _ask_yes(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"{prompt} ({hint}): ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "д", "да"}


def _pause() -> None:
    input("\nНажмите Enter, чтобы вернуться в меню…")


def _choose_auth() -> str:
    print("\nРежим авторизации")
    print("  1) oauth            — от имени вашего Google-аккаунта (рекомендуется)")
    print("  2) service_account  — от имени service account")
    choice = _ask("Выбор", "1")
    return "service_account" if choice == "2" else "oauth"


def _build_client(auth: str, folder_id: str) -> GoogleDriveClient:
    print("\nПодключение к Google Drive…")
    if auth == "oauth":
        print("(При первом входе откроется браузер для разрешения доступа)")
    return GoogleDriveClient(auth=auth, folder_id=folder_id or None)  # type: ignore[arg-type]


def _show_status(client: GoogleDriveClient) -> None:
    print("\n" + "=" * 60)
    print("  Google Drive — меню создания")
    print("=" * 60)
    print(f"  Auth:   {client.auth}")
    print(
        f"  Папка:  {client.folder_id or '(не задана — корень / всё доступное)'}"
    )
    print("=" * 60)


def _print_menu() -> None:
    print(
        """
  1. Создать папку
  2. Создать Google Документ
  3. Создать Google Таблицу
  4. Загрузить локальный файл
  5. Показать файлы в текущей папке
  6. Сменить рабочую папку
  7. Сменить режим авторизации
  0. Выход
"""
    )


def _resolve_parent(client: GoogleDriveClient, *, required: bool) -> Optional[str]:
    """Спросить parent_id, если рабочая папка не задана."""
    if client.folder_id:
        use_current = _ask_yes("Создать в текущей рабочей папке?", True)
        if use_current:
            return client.folder_id
    parent = _ask("ID папки-родителя (пусто = корень Drive)" if not required else "ID папки-родителя")
    if required and not parent:
        print("Ошибка: для этого действия нужна папка (ID или GOOGLE_DRIVE_FOLDER_ID).")
        return None
    return parent or None


def _action_create_folder(client: GoogleDriveClient) -> None:
    name = _ask("Имя новой папки")
    if not name:
        print("Имя не задано.")
        return
    parent = _resolve_parent(client, required=False)
    meta = client.create_folder(name, parent_id=parent)
    print()
    _print_created("Папка", meta)


def _action_create_doc(client: GoogleDriveClient) -> None:
    name = _ask("Имя документа")
    if not name:
        print("Имя не задано.")
        return
    parent = _resolve_parent(client, required=True)
    if parent is None:
        return
    meta = client.create_google_document(name, parent_id=parent, require_folder=True)
    print()
    _print_created("Документ", meta)


def _action_create_sheet(client: GoogleDriveClient) -> None:
    name = _ask("Имя таблицы")
    if not name:
        print("Имя не задано.")
        return
    parent = _resolve_parent(client, required=True)
    if parent is None:
        return
    meta = client.create_google_spreadsheet(name, parent_id=parent, require_folder=True)
    print()
    _print_created("Таблица", meta)


def _action_upload(client: GoogleDriveClient) -> None:
    path_str = _ask("Путь к локальному файлу")
    if not path_str:
        print("Путь не задан.")
        return
    path = Path(path_str).expanduser()
    if not path.is_file():
        print(f"Файл не найден: {path}")
        return
    name = _ask("Имя на Drive", path.name)
    parent = _resolve_parent(client, required=False)
    meta = client.create_file(name, local_path=path, parent_id=parent)
    print()
    _print_created("Файл", meta)


def _action_list(client: GoogleDriveClient) -> None:
    print()
    _print_files(client.read_all())


def _action_change_folder(client: GoogleDriveClient) -> GoogleDriveClient:
    print(f"Текущая папка: {client.folder_id or '(не задана)'}")
    print("Подсказка: ID из URL https://drive.google.com/drive/folders/ВОТ_ЭТОТ_ID")
    new_id = _ask("Новый ID папки (пусто = сбросить фильтр)")
    return GoogleDriveClient(auth=client.auth, folder_id=new_id or None)  # type: ignore[arg-type]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    auth = _choose_auth()
    folder_id = DEFAULT_FOLDER_ID or _ask(
        "Рабочая папка GOOGLE_DRIVE_FOLDER_ID (можно оставить пустым)",
        DEFAULT_FOLDER_ID,
    )

    try:
        client = _build_client(auth, folder_id)
    except Exception as exc:
        print(f"\nНе удалось подключиться: {exc}")
        sys.exit(1)

    actions = {
        "1": _action_create_folder,
        "2": _action_create_doc,
        "3": _action_create_sheet,
        "4": _action_upload,
        "5": _action_list,
    }

    while True:
        _show_status(client)
        _print_menu()
        choice = _ask("Пункт меню", "5")

        if choice == "0":
            print("Выход.")
            break

        try:
            if choice in actions:
                actions[choice](client)
                _pause()
            elif choice == "6":
                client = _action_change_folder(client)
            elif choice == "7":
                auth = _choose_auth()
                client = _build_client(auth, client.folder_id)
            else:
                print("Неизвестный пункт.")
                _pause()
        except KeyboardInterrupt:
            print("\nПрервано.")
            break
        except Exception as exc:
            print(f"\nОшибка: {exc}")
            _pause()


if __name__ == "__main__":
    main()
