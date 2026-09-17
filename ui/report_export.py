"""
Выгрузка таблицы CRM в новую Google Sheets через интеграции.

Поток:
  1) массив строк + простой анализ
  2) GoogleDriveClient.create_google_spreadsheet (OAuth)
  3) GoogleSheetsClient(spreadsheet_id=...) + write_values / batch_update
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

_ROOT = Path(__file__).resolve().parent.parent
_INTEGRATIONS = _ROOT / "integrations"
if str(_INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(_INTEGRATIONS))

from google_drive_client import GoogleDriveClient  # noqa: E402
from google_sheets_client import GoogleSheetsClient  # noqa: E402

from google_settings import apply_google_settings  # noqa: E402


def _rgb(hex_color: str) -> dict[str, float]:
    h = hex_color.lstrip("#")
    return {
        "red": int(h[0:2], 16) / 255,
        "green": int(h[2:4], 16) / 255,
        "blue": int(h[4:6], 16) / 255,
    }


def collect_tree_rows(tree, columns: Sequence[str]) -> list[dict[str, Any]]:
    """Снять текущие строки Treeview в список словарей."""
    rows: list[dict[str, Any]] = []
    for item_id in tree.get_children():
        values = tree.item(item_id, "values")
        row = {col: values[i] if i < len(values) else "" for i, col in enumerate(columns)}
        rows.append(row)
    return rows


def analyze_rows(title: str, columns: Sequence[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Минимальный анализ для шапки отчёта."""
    status_col = next((c for c in columns if c in ("status", "is_done")), None)
    by_status: dict[str, int] = {}
    if status_col:
        for row in rows:
            key = str(row.get(status_col) or "—")
            by_status[key] = by_status.get(key, 0) + 1

    amount_total = 0.0
    if "amount" in columns:
        for row in rows:
            raw = str(row.get("amount") or "").replace(" ", "").replace(",", ".")
            try:
                amount_total += float(raw)
            except ValueError:
                pass

    return {
        "title": title,
        "generated_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "count": len(rows),
        "by_status": by_status,
        "amount_total": amount_total,
        "columns": list(columns),
        "rows": rows,
    }


def _build_values(report: dict[str, Any], headings: dict[str, str]) -> list[list[Any]]:
    columns: list[str] = report["columns"]
    rows: list[dict[str, Any]] = report["rows"]
    col_count = max(len(columns), 4)

    def pad(cells: list[Any]) -> list[Any]:
        out = list(cells)
        while len(out) < col_count:
            out.append("")
        return out[:col_count]

    values: list[list[Any]] = [
        pad([report["title"]]),
        pad([f"Сформирован: {report['generated_at']}"]),
        pad([f"Записей: {report['count']}"]),
    ]

    if report["by_status"]:
        parts = ", ".join(f"{k}: {v}" for k, v in report["by_status"].items())
        values.append(pad([f"По статусам: {parts}"]))
    if report["amount_total"]:
        values.append(pad([f"Сумма amount: {report['amount_total']:,.2f}".replace(",", " ")]))

    values.append(pad([""]))
    values.append(pad(["ДАННЫЕ"]))
    values.append(pad([headings.get(c, c) for c in columns]))
    for row in rows:
        values.append(pad([row.get(c, "") for c in columns]))
    values.append(pad([""]))
    values.append(pad(["Отчёт выгружен из Exelio CRM"]))
    return values


def _format_requests(sheet_id: int, col_count: int, header_row_index: int, data_rows: int) -> list[dict]:
    """Оформление через GoogleSheetsClient.batch_update."""
    last_col = max(col_count, 1)
    requests: list[dict] = [
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": last_col,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": last_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": _rgb("1E3A5F"),
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {
                            "foregroundColor": _rgb("FFFFFF"),
                            "fontSize": 16,
                            "bold": True,
                        },
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row_index,
                    "endRowIndex": header_row_index + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": last_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": _rgb("0F766E"),
                        "horizontalAlignment": "CENTER",
                        "textFormat": {
                            "foregroundColor": _rgb("FFFFFF"),
                            "bold": True,
                            "fontSize": 10,
                        },
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": last_col,
                },
                "properties": {"pixelSize": 130},
                "fields": "pixelSize",
            }
        },
    ]
    if data_rows > 0:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": header_row_index + 1,
                        "endRowIndex": header_row_index + 1 + data_rows,
                        "startColumnIndex": 0,
                        "endColumnIndex": last_col,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "borders": {
                                "top": {"style": "SOLID", "color": _rgb("E5E7EB")},
                                "bottom": {"style": "SOLID", "color": _rgb("E5E7EB")},
                                "left": {"style": "SOLID", "color": _rgb("E5E7EB")},
                                "right": {"style": "SOLID", "color": _rgb("E5E7EB")},
                            }
                        }
                    },
                    "fields": "userEnteredFormat.borders",
                }
            }
        )
    return requests


def export_table_report(
    *,
    report_title: str,
    columns: Sequence[str],
    headings: dict[str, str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Создать Google Sheet через Drive (OAuth) и записать отчёт через Sheets API.
    Возвращает meta созданного файла (id, name, webViewLink, ...).
    """
    import time

    settings = apply_google_settings()
    folder_id = settings.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        raise ValueError(
            "Не задан GOOGLE_DRIVE_FOLDER_ID. Откройте «Настройки Google» в CRM."
        )

    report = analyze_rows(report_title, columns, rows)
    stamp = datetime.now().strftime("%d.%m.%Y %H-%M")
    # Имя без символов, которые иногда ломают Drive UI
    safe_title = report_title.replace("—", "-").replace("–", "-")
    file_name = f"{safe_title} - {stamp}"

    drive = GoogleDriveClient(auth="oauth", folder_id=folder_id)
    created = drive.create_google_spreadsheet(file_name, parent_id=folder_id)
    spreadsheet_id = created["id"]

    # Новой таблице иногда нужно мгновение, прежде чем Sheets API её видит
    sheets = None
    last_err: Exception | None = None
    for attempt in range(1, 6):
        try:
            time.sleep(0.6 * attempt)
            sheets = GoogleSheetsClient(spreadsheet_id=spreadsheet_id, auth="oauth")
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    if sheets is None:
        raise RuntimeError(
            f"Таблица создана (id={spreadsheet_id}), но Sheets API пока недоступен: {last_err}"
        )

    values = _build_values(report, headings)
    sheets.clear_range()

    # Пишем чанками — надёжнее на 1000+ строк
    chunk = 400
    start_row = 1
    for i in range(0, len(values), chunk):
        part = values[i : i + chunk]
        sheets.write_values(
            part, range_a1=f"A{start_row}", value_input_option="RAW"
        )
        start_row += len(part)

    header_row_index = 0
    for i, row in enumerate(values):
        if row and row[0] == "ДАННЫЕ":
            header_row_index = i + 1
            break

    sheet_id = sheets.ensure_sheet(sheets.sheet_name)
    # Для больших отчётов не красим каждую строку рамкой — только шапка
    data_rows_fmt = len(rows) if len(rows) <= 300 else 0
    sheets.batch_update(
        _format_requests(
            sheet_id=sheet_id,
            col_count=len(columns),
            header_row_index=header_row_index,
            data_rows=data_rows_fmt,
        )
    )

    return {
        "id": spreadsheet_id,
        "name": created.get("name") or file_name,
        "webViewLink": created.get("webViewLink")
        or f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        "count": report["count"],
        "analysis": report,
    }
