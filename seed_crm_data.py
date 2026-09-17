"""
Тестовое наполнение CRM через HTTP API (~1000 клиентов, сделок, задач).

Требует запущенный API (Docker Compose или python crm.py):
    python seed_crm_data.py
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

API_URL = os.environ.get("CRM_API_URL", "http://127.0.0.1:8000").rstrip("/")
COUNT = 1000

FIRST_NAMES = (
    "Александр", "Анна", "Дмитрий", "Елена", "Сергей", "Ольга", "Андрей", "Наталья",
    "Иван", "Мария", "Максим", "Екатерина", "Алексей", "Татьяна", "Владимир", "Ирина",
    "Николай", "Юлия", "Павел", "Светлана", "Роман", "Виктория", "Кирилл", "Дарья",
    "Михаил", "Полина", "Артём", "Алина", "Егор", "Ксения",
)
LAST_NAMES = (
    "Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Васильев",
    "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов",
    "Егоров", "Павлов", "Козлов", "Степанов", "Николаев", "Орлов", "Андреев",
    "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев",
)
COMPANIES = (
    "ООО «СеверТорг»", "АО «ТехноЛайн»", "ИП Ковалёв", "ООО «ДатаСофт»",
    "ООО «СтройМост»", "ЗАО «АгроПром»", "ООО «МедСервис»", "ООО «Логистик Плюс»",
    "ООО «ФинКонсалт»", "АО «ЭнергоСбыт»", "ООО «Ритейл Хаб»", "ООО «КликМаркет»",
    "ООО «Облако 24»", "ООО «ПрофСервис»", "ИП Смирнова", "ООО «Вектор»",
    "ООО «Партнёр СК»", "ООО «ИнфоГрад»", "ООО «МастерПак»", "ООО «БизнесОфис»",
)
DEAL_TITLES = (
    "Поставка оборудования", "Внедрение CRM", "Абонентское обслуживание",
    "Разработка сайта", "Аудит процессов", "Лицензии ПО", "Обучение сотрудников",
    "Маркетинговая кампания", "Аренда склада", "Поставка расходников",
    "Интеграция 1С", "Техподдержка 12 мес.", "Пилотный проект", "Доработка модуля",
    "Консалтинг по продажам", "Обновление инфраструктуры",
)
TASK_TITLES = (
    "Позвонить клиенту", "Отправить коммерческое предложение", "Согласовать договор",
    "Назначить встречу", "Собрать требования", "Проверить оплату", "Подготовить акт",
    "Напомнить о продлении", "Уточнить сроки поставки", "Передать в бухгалтерию",
    "Запросить реквизиты", "Провести демо", "Закрыть возражения", "Обновить карточку",
)
DEAL_STATUSES = ("new", "in_progress", "won", "lost", "cancelled")
CLIENT_STATUSES = ("active", "archived")


def _phone() -> str:
    return f"+7 ({random.randint(900, 999)}) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}"


def _email(first: str, last: str, i: int) -> str:
    domains = ("mail.ru", "yandex.ru", "gmail.com", "outlook.com", "company.ru")
    slug = f"{first[0].lower()}.{last.lower()}{i % 97}"
    # упростить кириллицу в латиницу грубо для email
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = []
    for ch in slug:
        out.append(translit.get(ch, ch if ch.isascii() else "x"))
    return f"{''.join(out)}@{random.choice(domains)}"


def _due_at() -> str:
    base = datetime.now() + timedelta(days=random.randint(-20, 45))
    return base.strftime("%Y-%m-%d %H:%M")


def main() -> None:
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    try:
        health = session.get(f"{API_URL}/health", timeout=10)
        health.raise_for_status()
    except requests.RequestException as exc:
        print(f"API недоступен ({API_URL}). Запустите Docker Compose или python crm.py\n{exc}")
        sys.exit(1)

    print(f"API OK: {health.json()}")
    print(f"Генерация по {COUNT} записей в clients / deals / tasks…")

    client_ids: list[int] = []
    for i in range(1, COUNT + 1):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        # женские фамилии грубо
        if first[-1] in "ая" and not last.endswith("а"):
            last = last + "а" if not last.endswith(("ой", "ий", "ый")) else last[:-2] + "ая"
        name = f"{last} {first}"
        payload = {
            "name": name,
            "phone": _phone(),
            "email": _email(first, last, i),
            "company": random.choice(COMPANIES),
            "notes": random.choice(
                (
                    "Постоянный клиент",
                    "Пришёл с рекомендации",
                    "Интерес к годовому контракту",
                    "Нужна рассрочка",
                    "Контакт только по email",
                    "",
                )
            ),
            "status": random.choices(CLIENT_STATUSES, weights=[85, 15])[0],
        }
        resp = session.post(f"{API_URL}/clients", json=payload, timeout=30)
        if resp.status_code >= 400:
            print(f"client #{i} error: {resp.status_code} {resp.text}")
            sys.exit(1)
        client_ids.append(resp.json()["id"])
        if i % 100 == 0:
            print(f"  clients: {i}/{COUNT}")

    deal_ids: list[int] = []
    for i in range(1, COUNT + 1):
        with_client = random.random() < 0.85
        payload = {
            "title": f"{random.choice(DEAL_TITLES)} #{i}",
            "description": random.choice(
                (
                    "Срок поставки 14 дней",
                    "Нужно согласование юристов",
                    "Клиент сравнивает с конкурентами",
                    "Повторная продажа",
                    "Крупный заказ, скидка 7%",
                    "",
                )
            ),
            "client_id": random.choice(client_ids) if with_client else None,
            "amount": round(random.uniform(5_000, 2_500_000), 2),
            "currency": "RUB",
            "status": random.choices(
                DEAL_STATUSES, weights=[25, 30, 25, 12, 8]
            )[0],
        }
        resp = session.post(f"{API_URL}/deals", json=payload, timeout=30)
        if resp.status_code >= 400:
            print(f"deal #{i} error: {resp.status_code} {resp.text}")
            sys.exit(1)
        deal_ids.append(resp.json()["id"])
        if i % 100 == 0:
            print(f"  deals: {i}/{COUNT}")

    for i in range(1, COUNT + 1):
        link_client = random.random() < 0.7
        link_deal = random.random() < 0.55
        payload = {
            "title": f"{random.choice(TASK_TITLES)} #{i}",
            "description": random.choice(
                (
                    "Связаться до конца недели",
                    "Подготовить документы",
                    "Повторить попытку связи",
                    "Внутреннее согласование",
                    "",
                )
            ),
            "client_id": random.choice(client_ids) if link_client else None,
            "deal_id": random.choice(deal_ids) if link_deal else None,
            "due_at": _due_at() if random.random() < 0.8 else None,
            "is_done": random.random() < 0.35,
        }
        resp = session.post(f"{API_URL}/tasks", json=payload, timeout=30)
        if resp.status_code >= 400:
            print(f"task #{i} error: {resp.status_code} {resp.text}")
            sys.exit(1)
        if i % 100 == 0:
            print(f"  tasks: {i}/{COUNT}")

    print("Готово.")
    print(f"  clients: {COUNT} (ids {client_ids[0]}…{client_ids[-1]})")
    print(f"  deals:   {COUNT} (ids {deal_ids[0]}…{deal_ids[-1]})")
    print(f"  tasks:   {COUNT}")
    print("Обновите таблицы в UI (кнопка «Обновить всё»).")


if __name__ == "__main__":
    main()
