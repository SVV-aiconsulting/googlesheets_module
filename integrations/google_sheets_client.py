"""
Переиспользуемый клиент Google Sheets (авторизация через service account и Google API).

Настройки берутся из файла `.env` (см. `.env.example`):
    GOOGLE_SPREADSHEET_ID
    GOOGLE_SERVICE_ACCOUNT_EMAIL

Использование из других приложений:
    from google_sheets_client import GoogleSheetsClient, DEFAULT_SPREADSHEET_ID

    client = GoogleSheetsClient(spreadsheet_id=DEFAULT_SPREADSHEET_ID)
    rows = client.read_all()
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Literal, Optional, Sequence, Union

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

_PROJECT_DIR = Path(__file__).resolve().parent.parent  # корень репозитория
load_dotenv(_PROJECT_DIR / ".env")

AuthMode = Literal["service_account", "oauth"]
PathLike = Union[str, Path]

# Те же scope, что у Drive — один OAuth-токен на создание + запись.
SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
)

Values = Sequence[Sequence[Any]]
_PLACEHOLDER_IDS = frozenset({"", "YOUR_SPREADSHEET_ID", "ВОТ_ЭТОТ_ID"})


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _resolve_path(env_name: str, cli_value: Optional[str] = None) -> Path:
    """CLI → .env (обязательно). Без захардкоженных путей."""
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


def _resolve_spreadsheet_id(cli_value: Optional[str] = None) -> str:
    """Вернуть ID таблицы: env/.env → CLI."""
    env_id = _env("GOOGLE_SPREADSHEET_ID")
    if env_id:
        return env_id
    if cli_value and cli_value.strip():
        return cli_value.strip()
    return ""


DEFAULT_SPREADSHEET_ID = _resolve_spreadsheet_id()
SERVICE_ACCOUNT_EMAIL = _env("GOOGLE_SERVICE_ACCOUNT_EMAIL")


def _scopes_ok(creds: Optional[UserCredentials]) -> bool:
    if not creds:
        return False
    granted = {s.rstrip("/") for s in (creds.scopes or [])}
    needed = {s.rstrip("/") for s in SCOPES}
    return needed.issubset(granted)


def _load_oauth_credentials(
    client_secret_path: Path,
    token_path: Path,
) -> UserCredentials:
    from google.auth.exceptions import RefreshError

    if not client_secret_path.is_file():
        raise FileNotFoundError(
            f"OAuth client secret не найден: {client_secret_path}. "
            "Задайте GOOGLE_OAUTH_CLIENT_SECRET_PATH в .env."
        )

    creds: Optional[UserCredentials] = None
    if token_path.is_file():
        creds = UserCredentials.from_authorized_user_file(str(token_path), list(SCOPES))

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
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


class GoogleSheetsClient:
    """CRUD-помощник для одной Google-таблицы (service account или OAuth)."""

    def __init__(
        self,
        spreadsheet_id: Optional[str] = None,
        *,
        auth: AuthMode = "service_account",
        credentials_path: Optional[PathLike] = None,
        oauth_client_secret_path: Optional[PathLike] = None,
        oauth_token_path: Optional[PathLike] = None,
        sheet_name: Optional[str] = None,
    ) -> None:
        """
        Args:
            spreadsheet_id: ID целевой таблицы. Если не указан — из .env.
            auth: ``service_account`` или ``oauth``.
            credentials_path: JSON service account (режим SA).
            oauth_client_secret_path / oauth_token_path: OAuth (режим oauth).
            sheet_name: Название листа. Если не указано — первый лист.
        """
        sid = (spreadsheet_id or "").strip() or DEFAULT_SPREADSHEET_ID
        if not sid or sid in _PLACEHOLDER_IDS:
            raise ValueError(
                "Не указан ID таблицы. Задайте GOOGLE_SPREADSHEET_ID в файле .env "
                "или передайте spreadsheet_id."
            )

        self.auth: AuthMode = auth
        self.spreadsheet_id = sid
        self._sheet_name = sheet_name

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

        if self.credentials_path and not self.credentials_path.is_absolute():
            self.credentials_path = _PROJECT_DIR / self.credentials_path
        if self.oauth_client_secret_path and not self.oauth_client_secret_path.is_absolute():
            self.oauth_client_secret_path = _PROJECT_DIR / self.oauth_client_secret_path
        if self.oauth_token_path and not self.oauth_token_path.is_absolute():
            self.oauth_token_path = _PROJECT_DIR / self.oauth_token_path

        self._service = self._build_service()
        if self._sheet_name is None:
            self._sheet_name = self._first_sheet_title()

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
                    f"Файл учётных данных не найден: {self.credentials_path}"
                )
            creds = ServiceAccountCredentials.from_service_account_file(
                str(self.credentials_path),
                scopes=SCOPES,
            )
        else:
            raise ValueError(f"Неизвестный auth={self.auth!r}")
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    def _first_sheet_title(self) -> str:
        meta = (
            self._service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id, fields="sheets.properties.title")
            .execute()
        )
        sheets = meta.get("sheets") or []
        if not sheets:
            raise RuntimeError("В таблице нет ни одного листа.")
        return sheets[0]["properties"]["title"]

    @property
    def sheet_name(self) -> str:
        return self._sheet_name  # type: ignore[return-value]

    def _a1(self, range_a1: Optional[str] = None) -> str:
        """Собрать A1-диапазон в контексте активного листа."""
        if range_a1 is None or range_a1 == "":
            return self.sheet_name
        if "!" in range_a1:
            return range_a1
        return f"{self.sheet_name}!{range_a1}"

    def _sheet_id(self, title: Optional[str] = None) -> int:
        target = title or self.sheet_name
        meta = (
            self._service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id, fields="sheets.properties")
            .execute()
        )
        for sheet in meta.get("sheets") or []:
            props = sheet.get("properties") or {}
            if props.get("title") == target:
                return int(props["sheetId"])
        raise ValueError(f"Лист не найден: {target!r}")

    # ------------------------------------------------------------------ create

    def write_values(
        self,
        values: Values,
        range_a1: str = "A1",
        value_input_option: str = "USER_ENTERED",
    ) -> dict:
        """Создать/перезаписать значения начиная с range_a1 (семантика PUT для диапазона)."""
        body = {"values": [list(row) for row in values]}
        return (
            self._service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.spreadsheet_id,
                range=self._a1(range_a1),
                valueInputOption=value_input_option,
                body=body,
            )
            .execute()
        )

    def append_rows(
        self,
        values: Values,
        range_a1: str = "A1",
        value_input_option: str = "USER_ENTERED",
        insert_data_option: str = "INSERT_ROWS",
    ) -> dict:
        """Добавить строки после последней непустой строки в указанном диапазоне/таблице."""
        body = {"values": [list(row) for row in values]}
        return (
            self._service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.spreadsheet_id,
                range=self._a1(range_a1),
                valueInputOption=value_input_option,
                insertDataOption=insert_data_option,
                body=body,
            )
            .execute()
        )

    # ------------------------------------------------------------------ read

    def read_range(
        self,
        range_a1: Optional[str] = None,
        major_dimension: str = "ROWS",
    ) -> list[list[Any]]:
        """Прочитать значения из диапазона. None / пусто → весь активный лист."""
        result = (
            self._service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=self._a1(range_a1),
                majorDimension=major_dimension,
            )
            .execute()
        )
        return result.get("values") or []

    def read_all(self, major_dimension: str = "ROWS") -> list[list[Any]]:
        """Прочитать все заполненные ячейки активного листа."""
        return self.read_range(None, major_dimension=major_dimension)

    # ------------------------------------------------------------------ update

    def update_range(
        self,
        values: Values,
        range_a1: str,
        value_input_option: str = "USER_ENTERED",
    ) -> dict:
        """Обновить (перезаписать) существующий диапазон новыми значениями."""
        return self.write_values(values, range_a1=range_a1, value_input_option=value_input_option)

    def batch_update_values(
        self,
        data: Sequence[dict],
        value_input_option: str = "USER_ENTERED",
    ) -> dict:
        """
        Пакетное обновление нескольких диапазонов.

        Каждый элемент: {"range": "A1:B2", "values": [[...], ...]}
        Диапазоны без '!' привязываются к активному листу.
        """
        body = {
            "valueInputOption": value_input_option,
            "data": [
                {
                    "range": self._a1(item["range"]),
                    "values": [list(row) for row in item["values"]],
                }
                for item in data
            ],
        }
        return (
            self._service.spreadsheets()
            .values()
            .batchUpdate(spreadsheetId=self.spreadsheet_id, body=body)
            .execute()
        )

    # ------------------------------------------------------------------ delete

    def clear_range(self, range_a1: Optional[str] = None) -> dict:
        """Очистить значения ячеек в диапазоне (форматирование сохраняется). None → весь лист."""
        return (
            self._service.spreadsheets()
            .values()
            .clear(
                spreadsheetId=self.spreadsheet_id,
                range=self._a1(range_a1),
                body={},
            )
            .execute()
        )

    def delete_rows(
        self,
        start_row_index: int,
        end_row_index: int,
        sheet_title: Optional[str] = None,
    ) -> dict:
        """
        Удалить строки по 0-базовым индексам [start_row_index, end_row_index).

        Пример: delete_rows(1, 3) удаляет строки 2 и 3 (как в Excel/Sheets).
        """
        if start_row_index < 0 or end_row_index <= start_row_index:
            raise ValueError("Нужно: 0 <= start_row_index < end_row_index.")

        request = {
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": self._sheet_id(sheet_title),
                            "dimension": "ROWS",
                            "startIndex": start_row_index,
                            "endIndex": end_row_index,
                        }
                    }
                }
            ]
        }
        return (
            self._service.spreadsheets()
            .batchUpdate(spreadsheetId=self.spreadsheet_id, body=request)
            .execute()
        )

    # ------------------------------------------------------------------ format / sheets

    def batch_update(self, requests: Sequence[dict]) -> dict:
        """Выполнить batchUpdate (merge, стили, размеры колонок, addSheet и т.п.)."""
        return (
            self._service.spreadsheets()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": list(requests)},
            )
            .execute()
        )

    def create_sheet(self, title: str) -> int:
        """Создать новый лист и сделать его активным. Возвращает sheetId."""
        result = self.batch_update(
            [{"addSheet": {"properties": {"title": title}}}]
        )
        props = result["replies"][0]["addSheet"]["properties"]
        self._sheet_name = props["title"]
        return int(props["sheetId"])

    def ensure_sheet(self, title: str) -> int:
        """Вернуть sheetId листа title; создать лист, если его ещё нет."""
        try:
            sheet_id = self._sheet_id(title)
            self._sheet_name = title
            return sheet_id
        except ValueError:
            return self.create_sheet(title)


def _print_rows(rows: list[list[Any]]) -> None:
    if not rows:
        print("(пустой лист)")
        return
    for i, row in enumerate(rows, start=1):
        print(f"{i}: {row}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Проверить доступ на чтение к Google Sheets."
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=None,
        help=(
            "ID таблицы. Если не задан — берётся GOOGLE_SPREADSHEET_ID "
            "из файла .env / окружения."
        ),
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="Путь к JSON-ключу service account (иначе GOOGLE_CREDENTIALS_PATH).",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Название листа (по умолчанию — первый лист).",
    )
    args = parser.parse_args()

    spreadsheet_id = _resolve_spreadsheet_id(args.spreadsheet_id)

    client = GoogleSheetsClient(
        spreadsheet_id=spreadsheet_id,
        credentials_path=args.credentials,
        sheet_name=args.sheet,
    )
    print(f"Таблица: {client.spreadsheet_id}")
    print(f"Лист:    {client.sheet_name}")
    print("--- все ячейки ---")
    _print_rows(client.read_all())


if __name__ == "__main__":
    main()
