"""
Переиспользуемый клиент Google Drive.

Два режима авторизации:
  1) service_account — JSON service account (GOOGLE_CREDENTIALS_PATH)
  2) oauth — личный аккаунт пользователя через OAuth2
     (GOOGLE_OAUTH_CLIENT_SECRET_PATH + token-файл)

Настройки из `.env` (см. `.env.example`):
    GOOGLE_CREDENTIALS_PATH
    GOOGLE_SERVICE_ACCOUNT_EMAIL
    GOOGLE_DRIVE_FOLDER_ID
    GOOGLE_OAUTH_CLIENT_SECRET_PATH
    GOOGLE_OAUTH_TOKEN_PATH

Использование (от имени пользователя):
    from google_drive_client import GoogleDriveClient

    client = GoogleDriveClient(auth="oauth", folder_id="FOLDER_ID")
    doc = client.create_google_document("Отчёт")
    sheet = client.create_google_spreadsheet("Данные")
"""

from __future__ import annotations

import argparse
import mimetypes
import os
from pathlib import Path
from typing import Any, Literal, Optional, Union

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

_PROJECT_DIR = Path(__file__).resolve().parent.parent  # корень репозитория
load_dotenv(_PROJECT_DIR / ".env")

AuthMode = Literal["service_account", "oauth"]
PathLike = Union[str, Path]

# Drive + Sheets в одном OAuth-токене (создание файла и запись значений).
SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
)

_FOLDER_MIME = "application/vnd.google-apps.folder"
_DOC_MIME = "application/vnd.google-apps.document"
_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
_PLACEHOLDER_IDS = frozenset({"", "YOUR_FOLDER_ID", "ВОТ_ЭТОТ_ID"})


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _resolve_path(env_name: str, cli_value: Optional[str] = None) -> Path:
    """CLI → .env (обязательно). Без захардкоженных путей к ключам."""
    if cli_value and str(cli_value).strip():
        path = Path(str(cli_value).strip()).expanduser()
    else:
        env_path = _env(env_name)
        if not env_path:
            raise ValueError(
                f"Не задан {env_name}. Укажите путь в .env "
                "или в настройках Google в CRM."
            )
        path = Path(env_path).expanduser()
    if not path.is_absolute():
        path = _PROJECT_DIR / path
    return path


def _resolve_credentials_path(cli_value: Optional[str] = None) -> Path:
    return _resolve_path("GOOGLE_CREDENTIALS_PATH", cli_value)


def _resolve_oauth_client_path(cli_value: Optional[str] = None) -> Path:
    return _resolve_path("GOOGLE_OAUTH_CLIENT_SECRET_PATH", cli_value)


def _resolve_oauth_token_path(cli_value: Optional[str] = None) -> Path:
    return _resolve_path("GOOGLE_OAUTH_TOKEN_PATH", cli_value)


def _try_env_path(env_name: str) -> Optional[Path]:
    try:
        return _resolve_path(env_name)
    except ValueError:
        return None


DEFAULT_CREDENTIALS_PATH = _try_env_path("GOOGLE_CREDENTIALS_PATH")
DEFAULT_OAUTH_CLIENT_PATH = _try_env_path("GOOGLE_OAUTH_CLIENT_SECRET_PATH")
DEFAULT_OAUTH_TOKEN_PATH = _try_env_path("GOOGLE_OAUTH_TOKEN_PATH")
SERVICE_ACCOUNT_EMAIL = _env("GOOGLE_SERVICE_ACCOUNT_EMAIL")
DEFAULT_FOLDER_ID = _env("GOOGLE_DRIVE_FOLDER_ID")


def _scopes_ok(creds: Optional[UserCredentials]) -> bool:
    """Проверить, что в токене есть все нужные scope (Drive + Sheets)."""
    if not creds:
        return False
    granted = {s.rstrip("/") for s in (creds.scopes or [])}
    needed = {s.rstrip("/") for s in SCOPES}
    return needed.issubset(granted)


def _load_oauth_credentials(
    client_secret_path: Path,
    token_path: Path,
) -> UserCredentials:
    """OAuth2 Installed App: браузер при первом входе, далее refresh через token.json."""
    from google.auth.exceptions import RefreshError

    if not client_secret_path.is_file():
        raise FileNotFoundError(
            f"OAuth client secret не найден: {client_secret_path}. "
            "Задайте GOOGLE_OAUTH_CLIENT_SECRET_PATH в .env."
        )

    creds: Optional[UserCredentials] = None
    if token_path.is_file():
        creds = UserCredentials.from_authorized_user_file(str(token_path), list(SCOPES))

    # Старый token без Sheets-scope → нужен повторный вход в браузере
    if creds and creds.valid and _scopes_ok(creds):
        return creds

    if creds and creds.expired and creds.refresh_token and _scopes_ok(creds):
        try:
            creds.refresh(Request())
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except RefreshError:
            creds = None

    if token_path.is_file():
        try:
            token_path.unlink()
        except OSError:
            pass

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_path),
        scopes=list(SCOPES),
    )
    # Локальный сервер на свободном порту — стандартный Desktop OAuth flow.
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


class GoogleDriveClient:
    """CRUD-помощник для файлов Google Drive (service account или OAuth пользователя)."""

    def __init__(
        self,
        *,
        auth: AuthMode = "service_account",
        credentials_path: Optional[PathLike] = None,
        oauth_client_secret_path: Optional[PathLike] = None,
        oauth_token_path: Optional[PathLike] = None,
        folder_id: Optional[str] = None,
    ) -> None:
        """
        Args:
            auth: ``service_account`` или ``oauth`` (файлы от имени пользователя).
            credentials_path: JSON service account (режим SA).
            oauth_client_secret_path: client_secret*.json (режим OAuth).
            oauth_token_path: куда сохранять/читать user token.
            folder_id: ID рабочей папки (GOOGLE_DRIVE_FOLDER_ID по умолчанию).
        """
        self.auth: AuthMode = auth
        if credentials_path is not None:
            self.credentials_path = Path(credentials_path)
        elif auth == "service_account":
            self.credentials_path = _resolve_credentials_path()
        else:
            self.credentials_path = Path()

        if oauth_client_secret_path is not None:
            self.oauth_client_secret_path = Path(oauth_client_secret_path)
        elif auth == "oauth":
            self.oauth_client_secret_path = _resolve_oauth_client_path()
        else:
            self.oauth_client_secret_path = Path()

        if oauth_token_path is not None:
            self.oauth_token_path = Path(oauth_token_path)
        elif auth == "oauth":
            self.oauth_token_path = _resolve_oauth_token_path()
        else:
            self.oauth_token_path = Path()

        if self.oauth_client_secret_path and not self.oauth_client_secret_path.is_absolute():
            self.oauth_client_secret_path = _PROJECT_DIR / self.oauth_client_secret_path
        if self.oauth_token_path and not self.oauth_token_path.is_absolute():
            self.oauth_token_path = _PROJECT_DIR / self.oauth_token_path
        if self.credentials_path and not self.credentials_path.is_absolute():
            self.credentials_path = _PROJECT_DIR / self.credentials_path

        raw_folder = (folder_id if folder_id is not None else DEFAULT_FOLDER_ID) or ""
        self.folder_id = "" if raw_folder.strip() in _PLACEHOLDER_IDS else raw_folder.strip()
        self._service = self._build_service()

    # ------------------------------------------------------------------ auth

    def _build_service(self):
        if self.auth == "oauth":
            creds = _load_oauth_credentials(
                self.oauth_client_secret_path,
                self.oauth_token_path,
            )
        elif self.auth == "service_account":
            if not self.credentials_path.is_file():
                raise FileNotFoundError(
                    f"Файл service account не найден: {self.credentials_path}. "
                    "Задайте GOOGLE_CREDENTIALS_PATH в .env."
                )
            creds = ServiceAccountCredentials.from_service_account_file(
                str(self.credentials_path),
                scopes=SCOPES,
            )
        else:
            raise ValueError(f"Неизвестный auth={self.auth!r}. Используйте 'service_account' или 'oauth'.")

        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def _parents(self, parent_id: Optional[str] = None) -> list[str]:
        pid = (parent_id if parent_id is not None else self.folder_id) or ""
        return [pid] if pid else []

    def _require_folder(self, parent_id: Optional[str] = None) -> str:
        parents = self._parents(parent_id)
        if not parents:
            raise ValueError(
                "Не указана папка. Передайте parent_id / folder_id "
                "или задайте GOOGLE_DRIVE_FOLDER_ID в .env."
            )
        return parents[0]

    def _in_folder_query(self, folder_id: Optional[str] = None) -> str:
        pid = folder_id if folder_id is not None else self.folder_id
        if pid:
            return f"'{pid}' in parents and trashed = false"
        return "trashed = false"

    # ------------------------------------------------------------------ read

    def list_files(
        self,
        folder_id: Optional[str] = None,
        page_size: int = 100,
        query_extra: str = "",
        fields: str = "nextPageToken, files(id, name, mimeType, modifiedTime, size, parents, webViewLink)",
    ) -> list[dict[str, Any]]:
        """Прочитать список файлов в рабочей папке (или во всём доступном Drive)."""
        q = self._in_folder_query(folder_id)
        if query_extra.strip():
            q = f"({q}) and ({query_extra.strip()})"

        files: list[dict[str, Any]] = []
        token: Optional[str] = None
        while True:
            response = (
                self._service.files()
                .list(
                    q=q,
                    pageSize=min(page_size, 1000),
                    pageToken=token,
                    fields=fields,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    orderBy="folder,name",
                )
                .execute()
            )
            files.extend(response.get("files") or [])
            token = response.get("nextPageToken")
            if not token:
                break
        return files

    def read_all(self, folder_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Алиас list_files — все файлы в рабочей папке."""
        return self.list_files(folder_id=folder_id)

    def get_file(self, file_id: str, fields: str = "*") -> dict[str, Any]:
        """Прочитать метаданные одного файла по ID."""
        return (
            self._service.files()
            .get(
                fileId=file_id,
                fields=fields,
                supportsAllDrives=True,
            )
            .execute()
        )

    # ------------------------------------------------------------------ create

    def create_folder(
        self,
        name: str,
        parent_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Создать папку. parent_id по умолчанию — рабочая папка клиента."""
        body: dict[str, Any] = {
            "name": name,
            "mimeType": _FOLDER_MIME,
        }
        parents = self._parents(parent_id)
        if parents:
            body["parents"] = parents
        return (
            self._service.files()
            .create(
                body=body,
                fields="id, name, mimeType, parents, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

    def create_file(
        self,
        name: str,
        *,
        mime_type: str = "text/plain",
        parent_id: Optional[str] = None,
        local_path: Optional[PathLike] = None,
    ) -> dict[str, Any]:
        """
        Создать файл на Drive.

        - Без local_path: пустой файл указанного mime_type.
        - С local_path: загрузка локального файла.
        """
        body: dict[str, Any] = {"name": name}
        parents = self._parents(parent_id)
        if parents:
            body["parents"] = parents

        if local_path is None:
            body["mimeType"] = mime_type
            return (
                self._service.files()
                .create(
                    body=body,
                    fields="id, name, mimeType, parents, webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )

        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(f"Локальный файл не найден: {path}")

        guessed, _ = mimetypes.guess_type(str(path))
        media_mime = mime_type if mime_type != "text/plain" or not guessed else guessed
        media = MediaFileUpload(str(path), mimetype=media_mime, resumable=True)
        return (
            self._service.files()
            .create(
                body=body,
                media_body=media,
                fields="id, name, mimeType, parents, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

    def create_google_document(
        self,
        name: str,
        parent_id: Optional[str] = None,
        *,
        require_folder: bool = True,
    ) -> dict[str, Any]:
        """
        Создать Google Документ от имени текущего аккаунта (OAuth / SA).

        По умолчанию требует папку (parent_id или GOOGLE_DRIVE_FOLDER_ID).
        """
        folder = self._require_folder(parent_id) if require_folder else (
            (self._parents(parent_id) or [None])[0]
        )
        return self.create_file(
            name,
            mime_type=_DOC_MIME,
            parent_id=folder,
        )

    def create_google_spreadsheet(
        self,
        name: str,
        parent_id: Optional[str] = None,
        *,
        require_folder: bool = True,
    ) -> dict[str, Any]:
        """
        Создать Google Таблицу от имени текущего аккаунта (OAuth / SA).

        По умолчанию требует папку (parent_id или GOOGLE_DRIVE_FOLDER_ID).
        """
        folder = self._require_folder(parent_id) if require_folder else (
            (self._parents(parent_id) or [None])[0]
        )
        return self.create_file(
            name,
            mime_type=_SHEET_MIME,
            parent_id=folder,
        )

    # ------------------------------------------------------------------ delete

    def delete_file(self, file_id: str, *, permanent: bool = False) -> None:
        """
        Удалить файл/папку.

        permanent=False — в корзину (trash);
        permanent=True — удалить безвозвратно.
        """
        if permanent:
            self._service.files().delete(
                fileId=file_id,
                supportsAllDrives=True,
            ).execute()
            return
        self._service.files().update(
            fileId=file_id,
            body={"trashed": True},
            supportsAllDrives=True,
        ).execute()


_MIME_LABELS = {
    _FOLDER_MIME: "Папка",
    _DOC_MIME: "Документ",
    _SHEET_MIME: "Таблица",
    "application/vnd.google-apps.form": "Форма",
    "application/vnd.google-apps.presentation": "Презентация",
    "application/pdf": "PDF",
}


def _mime_label(mime: Optional[str]) -> str:
    if not mime:
        return "—"
    return _MIME_LABELS.get(mime, mime.replace("application/", "").replace("vnd.google-apps.", ""))


def _fmt_size(size: Any) -> str:
    if size in (None, "", "—"):
        return "—"
    try:
        n = int(size)
    except (TypeError, ValueError):
        return str(size)
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


def _fmt_modified(value: Optional[str]) -> str:
    if not value:
        return "—"
    # 2026-09-17T13:08:59.125Z → 17.09.2026 13:08
    try:
        return (
            f"{value[8:10]}.{value[5:7]}.{value[0:4]} "
            f"{value[11:16]}"
        )
    except Exception:  # noqa: BLE001
        return value


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    sep = "-+-".join("-" * w for w in widths)
    print(fmt_row(headers))
    print(sep)
    for row in rows:
        print(fmt_row(row))


def _print_files(files: list[dict[str, Any]]) -> None:
    if not files:
        print("(пусто — файлов не найдено)")
        return

    rows: list[list[str]] = []
    for i, item in enumerate(files, start=1):
        rows.append(
            [
                str(i),
                _mime_label(item.get("mimeType")),
                str(item.get("name") or "—"),
                str(item.get("id") or "—"),
                _fmt_size(item.get("size")),
                _fmt_modified(item.get("modifiedTime")),
            ]
        )
    _print_table(
        ["№", "Тип", "Имя", "ID", "Размер", "Изменён"],
        rows,
    )
    print(f"\nВсего: {len(files)}")


def _print_created(label: str, meta: dict[str, Any]) -> None:
    _print_table(
        ["Тип", "Имя", "ID", "Ссылка"],
        [
            [
                label,
                str(meta.get("name") or "—"),
                str(meta.get("id") or "—"),
                str(meta.get("webViewLink") or "—"),
            ]
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Drive: список файлов и создание Docs/Sheets (SA или OAuth)."
    )
    parser.add_argument(
        "--auth",
        choices=("service_account", "oauth"),
        default="service_account",
        help="Режим авторизации. oauth = от имени пользователя.",
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="JSON service account (режим service_account).",
    )
    parser.add_argument(
        "--oauth-client",
        default=None,
        help="client_secret*.json (режим oauth).",
    )
    parser.add_argument(
        "--oauth-token",
        default=None,
        help="Путь к token.json (режим oauth).",
    )
    parser.add_argument(
        "--folder-id",
        default=None,
        help="ID рабочей папки (иначе GOOGLE_DRIVE_FOLDER_ID из .env).",
    )
    parser.add_argument(
        "--create-doc",
        default=None,
        metavar="NAME",
        help="Создать Google Документ с указанным именем в папке.",
    )
    parser.add_argument(
        "--create-sheet",
        default=None,
        metavar="NAME",
        help="Создать Google Таблицу с указанным именем в папке.",
    )
    args = parser.parse_args()

    client = GoogleDriveClient(
        auth=args.auth,
        credentials_path=_resolve_credentials_path(args.credentials) if args.auth == "service_account" else None,
        oauth_client_secret_path=_resolve_oauth_client_path(args.oauth_client) if args.auth == "oauth" else None,
        oauth_token_path=_resolve_oauth_token_path(args.oauth_token) if args.auth == "oauth" else None,
        folder_id=args.folder_id,
    )

    print(f"Auth:        {client.auth}")
    if client.auth == "oauth":
        print(f"OAuth client:{client.oauth_client_secret_path}")
        print(f"OAuth token: {client.oauth_token_path}")
    else:
        print(f"SA key:      {client.credentials_path}")
        print(f"SA email:    {SERVICE_ACCOUNT_EMAIL or '(не задан в .env)'}")
    print(
        f"Папка:       {client.folder_id or '(не задана — корень / всё доступное)'}"
    )

    if args.create_doc:
        _print_created("Document", client.create_google_document(args.create_doc))
    if args.create_sheet:
        _print_created("Spreadsheet", client.create_google_spreadsheet(args.create_sheet))

    if not args.create_doc and not args.create_sheet:
        print()
        _print_files(client.read_all())
        if not client.folder_id:
            print(
                "\nПодсказка: задайте GOOGLE_DRIVE_FOLDER_ID в .env, "
                "чтобы работать внутри одной папки.\n"
                "ID берётся из URL папки: "
                "https://drive.google.com/drive/folders/ВОТ_ЭТОТ_ID"
            )


if __name__ == "__main__":
    main()
