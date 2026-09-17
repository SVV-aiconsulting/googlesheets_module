# CRM API image — код монтируется томом в compose (hot-reload / debug).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRM_DB_PATH=/app/data/crm.db

# Зависимости API (включая watchdog для uvicorn --reload)
COPY crm/requirements.txt /app/crm/requirements.txt
RUN pip install --no-cache-dir -r /app/crm/requirements.txt

# Каркас каталогов; исходники перезаписываются bind-mount'ом
RUN mkdir -p /app/crm /app/data
COPY crm/ /app/crm/

EXPOSE 8000

# --reload + --reload-dir: watchdog следит за файлами в смонтированном /app/crm
CMD ["uvicorn", "crm.api:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/crm"]
