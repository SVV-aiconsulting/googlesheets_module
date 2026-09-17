# Exelio — Google Sheets/Drive + Mini-CRM

Монорепозиторий: клиенты Google Sheets/Drive, мини-CRM (SQLite + FastAPI + Docker) и Tkinter UI с выгрузкой отчётов в Google Sheets от имени пользователя (OAuth).

## Возможности

**Google Sheets** (`integrations/google_sheets_client.py`)
- CRUD значений, форматирование (`batchUpdate`), листы
- Авторизация: service account или OAuth

**Google Drive** (`integrations/google_drive_client.py`)
- Список / создание / удаление файлов и папок
- Создание Google Docs и Google Sheets в рабочей папке
- Service account или OAuth (личный аккаунт)
- CLI-меню: `integrations/drive_cli.py`

**Mini-CRM**
- Таблицы: клиенты, сделки, задачи (SQLite)
- FastAPI REST API + Swagger
- Docker Compose с hot-reload (`watchdog` / `uvicorn --reload`)
- Tkinter UI: таблицы, поиск, CRUD, настройки Google, выгрузка отчёта в новую Google-таблицу

## Структура

```text
Exelio/
  credentials/           # секреты (НЕ в git): SA JSON, client_secret, token
  integrations/          # Google Sheets / Drive / drive_cli / report_app
  crm/                   # модели, SQLite CRUD, FastAPI, Dockerfile
  ui/                    # Tkinter CRM-клиент + выгрузка отчётов
  data/                  # crm.db, google_gui_settings.txt (НЕ в git)
  crm.py                 # локальный запуск API
  docker-compose.yml
  seed_crm_data.py       # тестовое наполнение API (~1000 записей × 3)
  .env.example
```

## Быстрый старт

### 1. Окружение

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
copy .env.example .env
```

Положите ключи в `credentials/` и пропишите пути в `.env` (см. `.env.example`).

### 2. CRM API (Docker, рекомендуется)

```bash
docker compose up --build
```

- Docs: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/health  
- Код `crm/` смонтирован в контейнер — правки подхватываются без пересборки

Локально без Docker:

```bash
python crm.py
```

### 3. Tkinter UI

```bash
python ui/crm_app.py
```

В UI:
1. **Настройки Google** — OAuth `client_secret`, `token.json`, ID папки Drive (+ кнопка «Вставить»)
2. Настройки сохраняются в `data/google_gui_settings.txt`
3. На вкладках **Клиенты / Сделки / Задачи** — кнопка **Выгрузить отчёт**
4. Создаётся Google Sheet в вашей папке (OAuth), данные пишутся через Sheets API, в конце — ссылка и кнопка **Открыть**

### 4. Тестовые данные

API должен быть запущен:

```bash
python seed_crm_data.py
```

~1000 реалистичных клиентов, сделок и задач через HTTP. Затем в UI — **Обновить всё**.

## Google: важные нюансы

### `GOOGLE_DRIVE_FOLDER_ID`

**Не обязателен** для списка файлов Drive.  
**Нужен**, чтобы:
- фильтровать список по одной папке;
- создавать Docs/Sheets и CRM-отчёты именно в эту папку.

ID — хвост URL: `https://drive.google.com/drive/folders/ВОТ_ЭТОТ_ID`

### OAuth (личный аккаунт)

Выгрузка отчётов из GUI идёт через **OAuth в desktop-приложении**, не на сервере — файлы создаются от вашего Google-аккаунта.

1. Google Cloud Console → OAuth Client (Desktop) → скачать `client_secret*.json` в `credentials/`
2. Добавьте себя в **Test users**, если приложение в статусе Testing
3. При первом экспорте откроется браузер; токен сохранится в `credentials/token.json`
4. Нужны scope Drive **и** Sheets; при смене scope старый token сбрасывается автоматически

### Service account

Для фоновых сценариев Sheets/Drive (SA): расшарьте таблицу/папку на email из `GOOGLE_SERVICE_ACCOUNT_EMAIL`.

Пути к ключам **только из `.env` / настроек GUI** — в коде нет захардкоженных путей к JSON.

## API CRM (кратко)

| Метод | Путь | Назначение |
|-------|------|------------|
| GET/POST | `/clients` | список / создать |
| GET | `/clients/search?q=` | поиск (без учёта регистра, кириллица) |
| PATCH/DELETE | `/clients/{id}` | обновить / удалить |
| POST | `/clients/{id}/archive` \| `/restore` | архив |
| GET/POST | `/deals`, `/tasks` | аналогично |
| POST | `/deals/{id}/attach-client` | привязать клиента |
| POST | `/tasks/{id}/done` | отметить задачу |

## Переменные окружения

| Переменная | Обязательно? | Описание |
|------------|--------------|----------|
| `GOOGLE_CREDENTIALS_PATH` | для SA | путь к JSON service account |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL` | нет | email SA |
| `GOOGLE_SPREADSHEET_ID` | для Sheets SA | ID таблицы |
| `GOOGLE_DRIVE_FOLDER_ID` | для создания в папке | ID рабочей папки |
| `GOOGLE_OAUTH_CLIENT_SECRET_PATH` | для OAuth | `client_secret*.json` |
| `GOOGLE_OAUTH_TOKEN_PATH` | нет | `token.json` (по умолчанию в credentials/) |
| `CRM_DB_PATH` | нет | путь к SQLite (`data/crm.db`) |
| `CRM_API_URL` | нет | URL API для UI (`http://127.0.0.1:8000`) |

## Безопасность — не коммитить

В `.gitignore` уже исключено:

- `.env`
- `credentials/`
- `*.json` ключи / `token.json`
- `data/` (БД и GUI-настройки Google)
- `.venv/`

В git попадает только `.env.example` с плейсхолдерами.

## Полезные команды

```bash
# Drive: список файлов
python integrations/google_drive_client.py

# Drive: интерактивное меню
python integrations/drive_cli.py

# Sheets demo-отчёт (Tkinter)
python integrations/report_app.py

# CRM API + UI
docker compose up --build
python ui/crm_app.py
```
