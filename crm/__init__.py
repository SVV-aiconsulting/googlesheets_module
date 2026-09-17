"""Пакет мини-CRM (SQLite + FastAPI)."""

from crm.database import CRMDatabase
from crm.models import Client, Deal, Task

__all__ = ["CRMDatabase", "Client", "Deal", "Task"]
