"""
Точка входа мини-CRM API.

Запуск:
    python crm.py
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "crm.api:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
