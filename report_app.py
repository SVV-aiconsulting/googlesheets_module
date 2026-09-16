"""
Простое Tkinter-приложение: форма отчёта → случайные данные → Google Sheets.

Запуск:
    python report_app.py
"""

from __future__ import annotations

import random
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import Any

from google_sheets_client import (
    DEFAULT_SPREADSHEET_ID,
    SERVICE_ACCOUNT_EMAIL,
    GoogleSheetsClient,
)

# ---------------------------------------------------------------------------
# Генерация «рандомного» отчёта
# ---------------------------------------------------------------------------

PRODUCTS = (
    "Ноутбук Pro 14",
    "Монитор 27\" IPS",
    "Клавиатура механическая",
    "Мышь беспроводная",
    "Док-станция USB-C",
    "Наушники Studio",
    "SSD 1 ТБ",
    "Веб-камера 4K",
    "Рюкзак офисный",
    "Зарядка GaN 65W",
)

REGIONS = ("Центр", "Северо-Запад", "Юг", "Урал", "Сибирь", "Дальний Восток")


def _parse_date(text: str) -> date:
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {text!r}. Ожидается ДД.ММ.ГГГГ")


def generate_report(
    date_from: date,
    date_to: date,
    department: str,
    author: str,
    report_type: str,
) -> dict[str, Any]:
    """Собрать структуру отчёта со случайными строками и итогами."""
    if date_to < date_from:
        raise ValueError("Дата «по» не может быть раньше даты «с».")

    days = max(1, (date_to - date_from).days + 1)
    n_rows = random.randint(8, 14)
    rows: list[dict[str, Any]] = []

    for _ in range(n_rows):
        qty = random.randint(1, 25)
        price = round(random.uniform(990, 89_900), 2)
        amount = round(qty * price, 2)
        offset = random.randint(0, days - 1)
        rows.append(
            {
                "date": date_from + timedelta(days=offset),
                "product": random.choice(PRODUCTS),
                "region": random.choice(REGIONS),
                "qty": qty,
                "price": price,
                "amount": amount,
            }
        )

    rows.sort(key=lambda r: r["date"])

    total_qty = sum(r["qty"] for r in rows)
    total_amount = round(sum(r["amount"] for r in rows), 2)
    avg_check = round(total_amount / n_rows, 2) if n_rows else 0.0
    top_region = max(
        REGIONS,
        key=lambda reg: sum(r["amount"] for r in rows if r["region"] == reg),
    )

    return {
        "title": f"ОТЧЁТ: {report_type.upper()}",
        "date_from": date_from,
        "date_to": date_to,
        "department": department.strip() or "—",
        "author": author.strip() or "—",
        "report_type": report_type.strip() or "—",
        "generated_at": date.today(),
        "rows": rows,
        "kpi": {
            "orders": n_rows,
            "qty": total_qty,
            "amount": total_amount,
            "avg_check": avg_check,
            "top_region": top_region,
        },
    }


# ---------------------------------------------------------------------------
# Запись «документного» отчёта в Google Sheets
# ---------------------------------------------------------------------------

def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


# Google Sheets / Excel: серийный номер даты (дни с 1899-12-30).
_SHEETS_EPOCH = datetime(1899, 12, 30)


def _to_sheets_date(value: date | datetime) -> float:
    """Число даты для Sheets; отображение задаётся numberFormat dd.mm.yyyy."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime(value.year, value.month, value.day)
    return (dt - _SHEETS_EPOCH).total_seconds() / 86400.0


def _number_format(pattern: str, fmt_type: str = "DATE") -> dict:
    return {"numberFormat": {"type": fmt_type, "pattern": pattern}}


def _rgb(hex_color: str) -> dict[str, float]:
    h = hex_color.lstrip("#")
    return {
        "red": int(h[0:2], 16) / 255,
        "green": int(h[2:4], 16) / 255,
        "blue": int(h[4:6], 16) / 255,
    }


def _text_format(
    bold: bool = False,
    size: int = 10,
    color: str = "1F2937",
    font: str = "Calibri",
) -> dict:
    return {
        "foregroundColor": _rgb(color),
        "fontFamily": font,
        "fontSize": size,
        "bold": bold,
    }


def _cell(
    bg: str | None = None,
    bold: bool = False,
    size: int = 10,
    color: str = "1F2937",
    h: str = "LEFT",
    v: str = "MIDDLE",
    wrap: bool = False,
) -> dict:
    style: dict[str, Any] = {
        "textFormat": _text_format(bold=bold, size=size, color=color),
        "horizontalAlignment": h,
        "verticalAlignment": v,
        "wrapStrategy": "WRAP" if wrap else "OVERFLOW_CELL",
    }
    if bg:
        style["backgroundColor"] = _rgb(bg)
    return style


def _border(color: str = "D1D5DB", style: str = "SOLID") -> dict:
    return {"style": style, "color": _rgb(color)}


def _borders_box(color: str = "D1D5DB") -> dict:
    b = _border(color)
    return {"top": b, "bottom": b, "left": b, "right": b}


def write_report_to_sheet(client: GoogleSheetsClient, report: dict[str, Any]) -> str:
    """
    Очистить/создать лист и выложить отчёт в виде документа.
    Возвращает имя листа.
    """
    stamp = datetime.now().strftime("%d.%m %H-%M")
    sheet_title = f"Отчёт {stamp}"
    # Google Sheets: имя листа ≤ 100 символов
    sheet_id = client.ensure_sheet(sheet_title)

    rows_data: list[dict[str, Any]] = report["rows"]
    kpi = report["kpi"]
    n = len(rows_data)

    # Строки документа (1-based mentally; values start at A1)
    # 1 title, 2 period, 3 blank, 4-7 meta, 8 blank, 9 kpi header,
    # 10 kpi labels, 11 kpi values, 12 blank, 13 detail header,
    # 14 table header, 15.. table, then totals + footer
    meta_start = 4
    kpi_header_row = 9
    kpi_label_row = 10
    kpi_value_row = 11
    detail_header_row = 13
    table_header_row = 14
    table_start_row = 15
    table_end_row = table_start_row + n - 1
    totals_row = table_end_row + 1
    footer_row = totals_row + 2

    values: list[list[Any]] = [
        [report["title"], "", "", "", "", "", ""],
        [
            (
                f"Период: {report['date_from'].strftime('%d.%m.%Y')} — "
                f"{report['date_to'].strftime('%d.%m.%Y')}"
            ),
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        ["", "", "", "", "", "", ""],
        ["Подразделение", report["department"], "", "Автор", report["author"], "", ""],
        [
            "Тип отчёта",
            report["report_type"],
            "",
            "Сформирован",
            _to_sheets_date(report["generated_at"]),
            "",
            "",
        ],
        ["Статус", "Симуляция (демо-данные)", "", "Лист", sheet_title, "", ""],
        ["", "", "", "", "", "", ""],
        ["", "", "", "", "", "", ""],
        ["СВОДНЫЕ ПОКАЗАТЕЛИ", "", "", "", "", "", ""],
        ["Заказов", "Единиц", "Выручка, ₽", "Средний чек, ₽", "Топ-регион", "", ""],
        [
            kpi["orders"],
            kpi["qty"],
            _money(kpi["amount"]),
            _money(kpi["avg_check"]),
            kpi["top_region"],
            "",
            "",
        ],
        ["", "", "", "", "", "", ""],
        ["ДЕТАЛИЗАЦИЯ ОПЕРАЦИЙ", "", "", "", "", "", ""],
        ["№", "Дата", "Товар", "Регион", "Кол-во", "Цена, ₽", "Сумма, ₽"],
    ]

    for i, item in enumerate(rows_data, start=1):
        values.append(
            [
                i,
                _to_sheets_date(item["date"]),
                item["product"],
                item["region"],
                item["qty"],
                _money(item["price"]),
                _money(item["amount"]),
            ]
        )

    values.append(
        ["", "", "", "ИТОГО", kpi["qty"], "", _money(kpi["amount"])]
    )
    values.append(["", "", "", "", "", "", ""])
    values.append(
        [
            "Документ сформирован автоматически. Данные носят демонстрационный характер.",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    )

    # RAW: числа дат пишем как серийные; формат dd.mm.yyyy задаём отдельно.
    client.clear_range()
    client.write_values(values, range_a1="A1", value_input_option="RAW")

    requests: list[dict] = [
        # Ширины колонок
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 48},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 1,
                    "endIndex": 2,
                },
                "properties": {"pixelSize": 110},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 2,
                    "endIndex": 3,
                },
                "properties": {"pixelSize": 200},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 3,
                    "endIndex": 4,
                },
                "properties": {"pixelSize": 130},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 4,
                    "endIndex": 7,
                },
                "properties": {"pixelSize": 120},
                "fields": "pixelSize",
            }
        },
        # Высота шапки
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 42},
                "fields": "pixelSize",
            }
        },
        # Merge: заголовок, период, секции, футер
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": kpi_header_row - 1,
                    "endRowIndex": kpi_header_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": detail_header_row - 1,
                    "endRowIndex": detail_header_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": footer_row - 1,
                    "endRowIndex": footer_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        # Title
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": _cell(
                        bg="1E3A5F",
                        bold=True,
                        size=18,
                        color="FFFFFF",
                        h="CENTER",
                    )
                },
                "fields": "userEnteredFormat",
            }
        },
        # Period
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": _cell(
                        bg="E8EEF5",
                        bold=False,
                        size=11,
                        color="334155",
                        h="CENTER",
                    )
                },
                "fields": "userEnteredFormat",
            }
        },
        # Meta labels (A4:A6, D4:D6)
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": meta_start - 1,
                    "endRowIndex": meta_start + 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": _cell(
                        bg="F1F5F9", bold=True, size=10, color="475569"
                    )
                },
                "fields": "userEnteredFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": meta_start - 1,
                    "endRowIndex": meta_start + 2,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4,
                },
                "cell": {
                    "userEnteredFormat": _cell(
                        bg="F1F5F9", bold=True, size=10, color="475569"
                    )
                },
                "fields": "userEnteredFormat",
            }
        },
        # Meta values
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": meta_start - 1,
                    "endRowIndex": meta_start + 2,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2,
                },
                "cell": {"userEnteredFormat": _cell(size=10, color="0F172A")},
                "fields": "userEnteredFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": meta_start - 1,
                    "endRowIndex": meta_start + 2,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5,
                },
                "cell": {"userEnteredFormat": _cell(size=10, color="0F172A")},
                "fields": "userEnteredFormat",
            }
        },
        # Section headers
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": kpi_header_row - 1,
                    "endRowIndex": kpi_header_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": _cell(
                        bg="0F766E",
                        bold=True,
                        size=12,
                        color="FFFFFF",
                        h="LEFT",
                    )
                },
                "fields": "userEnteredFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": detail_header_row - 1,
                    "endRowIndex": detail_header_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": _cell(
                        bg="0F766E",
                        bold=True,
                        size=12,
                        color="FFFFFF",
                        h="LEFT",
                    )
                },
                "fields": "userEnteredFormat",
            }
        },
        # KPI labels
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": kpi_label_row - 1,
                    "endRowIndex": kpi_label_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 5,
                },
                "cell": {
                    "userEnteredFormat": {
                        **_cell(
                            bg="CCFBF1",
                            bold=True,
                            size=9,
                            color="115E59",
                            h="CENTER",
                        ),
                        "borders": _borders_box("99F6E4"),
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        # KPI values
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": kpi_value_row - 1,
                    "endRowIndex": kpi_value_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 5,
                },
                "cell": {
                    "userEnteredFormat": {
                        **_cell(
                            bg="FFFFFF",
                            bold=True,
                            size=14,
                            color="134E4A",
                            h="CENTER",
                        ),
                        "borders": _borders_box("99F6E4"),
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        # Table header
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": table_header_row - 1,
                    "endRowIndex": table_header_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": {
                        **_cell(
                            bg="1E3A5F",
                            bold=True,
                            size=10,
                            color="FFFFFF",
                            h="CENTER",
                        ),
                        "borders": _borders_box("1E3A5F"),
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        # Table body
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": table_start_row - 1,
                    "endRowIndex": table_end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": {
                        **_cell(size=10, color="1F2937", h="CENTER", v="MIDDLE"),
                        "borders": _borders_box("E5E7EB"),
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        # Product column left-align
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": table_start_row - 1,
                    "endRowIndex": table_end_row,
                    "startColumnIndex": 2,
                    "endColumnIndex": 3,
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "LEFT",
                        "textFormat": _text_format(size=10),
                    }
                },
                "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.textFormat",
            }
        },
        # Даты в таблице снова — после стиля тела, чтобы формат даты не затёрся
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": table_start_row - 1,
                    "endRowIndex": table_end_row,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2,
                },
                "cell": {
                    "userEnteredFormat": {
                        **_cell(size=10, color="1F2937", h="CENTER", v="MIDDLE"),
                        **_number_format("dd.mm.yyyy"),
                        "borders": _borders_box("E5E7EB"),
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        # «Сформирован» — дата после стиля meta values
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 4,
                    "endRowIndex": 5,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5,
                },
                "cell": {
                    "userEnteredFormat": {
                        **_cell(size=10, color="0F172A"),
                        **_number_format("dd.mm.yyyy"),
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        # Totals row
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": totals_row - 1,
                    "endRowIndex": totals_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": {
                        **_cell(
                            bg="FEF3C7",
                            bold=True,
                            size=11,
                            color="92400E",
                            h="CENTER",
                        ),
                        "borders": _borders_box("F59E0B"),
                    }
                },
                "fields": "userEnteredFormat",
            }
        },
        # Footer
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": footer_row - 1,
                    "endRowIndex": footer_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": _cell(
                        size=9, color="64748B", h="LEFT", wrap=True
                    )
                },
                "fields": "userEnteredFormat",
            }
        },
        # Freeze title + period
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 2},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]

    # Чередование строк таблицы
    for row_idx in range(table_start_row - 1, table_end_row):
        if (row_idx - (table_start_row - 1)) % 2 == 1:
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_idx,
                            "endRowIndex": row_idx + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 7,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": _rgb("F8FAFC"),
                                "borders": _borders_box("E5E7EB"),
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.borders",
                    }
                }
            )

    client.batch_update(requests)
    return sheet_title


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

REPORT_TYPES = (
    "Продажи",
    "Складские остатки",
    "Клиентская активность",
    "Маркетинг",
)


class ReportApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Exelio — генератор отчётов")
        self.resizable(False, False)
        self.configure(padx=16, pady=16)

        today = date.today()
        month_ago = today - timedelta(days=30)

        frm = ttk.Frame(self)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="Параметры отчёта", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        self.date_from = tk.StringVar(value=month_ago.strftime("%d.%m.%Y"))
        self.date_to = tk.StringVar(value=today.strftime("%d.%m.%Y"))
        self.department = tk.StringVar(value="Отдел продаж")
        self.author = tk.StringVar(value="Иванов И.И.")
        self.report_type = tk.StringVar(value=REPORT_TYPES[0])

        fields = [
            (1, "Дата с (ДД.ММ.ГГГГ)", self.date_from),
            (2, "Дата по (ДД.ММ.ГГГГ)", self.date_to),
            (3, "Подразделение", self.department),
            (4, "Автор", self.author),
        ]
        for row, label, var in fields:
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(frm, textvariable=var, width=36).grid(
                row=row, column=1, sticky="ew", pady=4, padx=(12, 0)
            )

        ttk.Label(frm, text="Тип отчёта").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm,
            textvariable=self.report_type,
            values=REPORT_TYPES,
            state="readonly",
            width=34,
        ).grid(row=5, column=1, sticky="ew", pady=4, padx=(12, 0))

        self.status = tk.StringVar(value="Готово к формированию")
        ttk.Label(frm, textvariable=self.status, foreground="#475569").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(14, 6)
        )

        self.btn = ttk.Button(
            frm, text="Сформировать и записать в Google Sheets", command=self._on_submit
        )
        self.btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        sid_hint = (
            f"{DEFAULT_SPREADSHEET_ID[:12]}…"
            if DEFAULT_SPREADSHEET_ID
            else "не задан в .env"
        )
        email_hint = SERVICE_ACCOUNT_EMAIL or "не задан в .env"
        hint = (
            f"Будет создан новый лист с оформленным отчётом "
            f"(таблица: {sid_hint}; аккаунт: {email_hint})."
        )
        ttk.Label(frm, text=hint, wraplength=420, foreground="#94A3B8").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

    def _on_submit(self) -> None:
        try:
            d_from = _parse_date(self.date_from.get())
            d_to = _parse_date(self.date_to.get())
            report = generate_report(
                date_from=d_from,
                date_to=d_to,
                department=self.department.get(),
                author=self.author.get(),
                report_type=self.report_type.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Ошибка ввода", str(exc))
            return

        self.btn.configure(state="disabled")
        self.status.set("Запись в Google Sheets…")

        def worker() -> None:
            try:
                if not DEFAULT_SPREADSHEET_ID:
                    raise ValueError(
                        "Не задан GOOGLE_SPREADSHEET_ID. "
                        "Скопируйте .env.example в .env и укажите ID таблицы."
                    )
                client = GoogleSheetsClient()
                sheet_name = write_report_to_sheet(client, report)
                url = (
                    f"https://docs.google.com/spreadsheets/d/"
                    f"{client.spreadsheet_id}/edit"
                )
                self.after(0, lambda: self._on_success(sheet_name, url))
            except Exception as exc:  # noqa: BLE001 — показать пользователю любую ошибку API
                self.after(0, lambda: self._on_error(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, sheet_name: str, url: str) -> None:
        self.btn.configure(state="normal")
        self.status.set(f"Готово: лист «{sheet_name}»")
        messagebox.showinfo(
            "Отчёт записан",
            f"Создан лист «{sheet_name}».\n\nОткрыть таблицу:\n{url}",
        )

    def _on_error(self, exc: BaseException) -> None:
        self.btn.configure(state="normal")
        self.status.set("Ошибка при записи")
        messagebox.showerror("Не удалось записать отчёт", str(exc))


def main() -> None:
    app = ReportApp()
    app.mainloop()


if __name__ == "__main__":
    main()
