# Google Sheets Module

Переиспользуемый Python-клиент для Google Sheets (service account) и простое Tkinter-приложение, которое формирует демо-отчёт и записывает его в таблицу с оформлением «как документ».

## Возможности

- CRUD по значениям листа: чтение, запись, append, clear, удаление строк
- Форматирование через `batchUpdate` (merge, стили, ширины колонок, новые листы)
- Настройки из `.env` (`GOOGLE_SPREADSHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_EMAIL`)
- GUI `report_app.py`: даты, подразделение, автор, тип отчёта → случайные данные → новый лист в таблице

## Структура

| Файл | Назначение |
|------|------------|
| `google_sheets_client.py` | Клиент Google Sheets API |
| `report_app.py` | Tkinter-приложение генерации отчётов |
| `.env.example` | Шаблон переменных окружения |
| `requirements.txt` | Зависимости |

## Быстрый старт

### 1. Окружение

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Service Account

1. Создайте service account в Google Cloud и скачайте JSON-ключ.
2. Положите файл в корень проекта (по умолчанию клиент ищет `vibecode-*.json` рядом с модулем — при необходимости поправьте путь `DEFAULT_CREDENTIALS_PATH` в `google_sheets_client.py`).
3. Создайте Google-таблицу и **расшарьте** её на email service account с правом редактора.

### 3. Настройки `.env`

```bash
copy .env.example .env
```

Заполните:

```env
GOOGLE_SPREADSHEET_ID=ваш_id_из_url_таблицы
GOOGLE_SERVICE_ACCOUNT_EMAIL=ваш-sa@project.iam.gserviceaccount.com
```

ID таблицы — фрагмент из URL:

`https://docs.google.com/spreadsheets/d/ВОТ_ЭТОТ_ID/edit`

### 4. Проверка доступа

```bash
python google_sheets_client.py
```

### 5. Генератор отчётов

```bash
python report_app.py
```

Укажите период и поля → «Сформировать и записать в Google Sheets».  
Будет создан новый лист с заголовком, метаданными, KPI и таблицей; даты пишутся как значения Sheets в формате `дд.мм.гггг`.

## Использование клиента в коде

```python
from google_sheets_client import GoogleSheetsClient, DEFAULT_SPREADSHEET_ID

client = GoogleSheetsClient()  # ID из .env
# или явно:
# client = GoogleSheetsClient(spreadsheet_id="...")

rows = client.read_all()
client.write_values([["A", "B"], [1, 2]], range_a1="A1")
client.append_rows([[3, 4]])
client.clear_range("A1:B10")

# Новый лист + форматирование
sheet_id = client.create_sheet("Отчёт")
client.batch_update([
    {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": 3,
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True},
                }
            },
            "fields": "userEnteredFormat.textFormat.bold",
        }
    }
])
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `GOOGLE_SPREADSHEET_ID` | ID целевой Google-таблицы |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` | Email service account (для справки / шаринга) |

Приоритет ID: аргумент конструктора / CLI → `.env` / окружение.

## Безопасность

В репозиторий **не** коммитьте:

- `.env`
- JSON-ключ service account
- `.venv/`

См. `.gitignore`.
