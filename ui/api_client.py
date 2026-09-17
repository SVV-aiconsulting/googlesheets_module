"""
HTTP-клиент к локальному FastAPI CRM (без сторонних зависимостей).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class ApiError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class CrmApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    # ----- clients -----

    def list_clients(self, status: Optional[str] = None) -> list[dict]:
        return self._request("GET", "/clients", params={"status": status, "limit": 5000})

    def search_clients(self, q: str) -> list[dict]:
        return self._request("GET", "/clients/search", params={"q": q, "limit": 5000})

    def create_client(self, payload: dict) -> dict:
        return self._request("POST", "/clients", data=payload)

    def update_client(self, client_id: int, payload: dict) -> dict:
        return self._request("PATCH", f"/clients/{client_id}", data=payload)

    def archive_client(self, client_id: int) -> dict:
        return self._request("POST", f"/clients/{client_id}/archive")

    def restore_client(self, client_id: int) -> dict:
        return self._request("POST", f"/clients/{client_id}/restore")

    def delete_client(self, client_id: int) -> None:
        self._request("DELETE", f"/clients/{client_id}")

    # ----- deals -----

    def list_deals(
        self, status: Optional[str] = None, client_id: Optional[int] = None
    ) -> list[dict]:
        return self._request(
            "GET",
            "/deals",
            params={"status": status, "client_id": client_id, "limit": 5000},
        )

    def search_deals(self, q: str) -> list[dict]:
        return self._request("GET", "/deals/search", params={"q": q, "limit": 5000})

    def create_deal(self, payload: dict) -> dict:
        return self._request("POST", "/deals", data=payload)

    def update_deal(self, deal_id: int, payload: dict) -> dict:
        return self._request("PATCH", f"/deals/{deal_id}", data=payload)

    def attach_client(self, deal_id: int, client_id: Optional[int]) -> dict:
        return self._request(
            "POST", f"/deals/{deal_id}/attach-client", data={"client_id": client_id}
        )

    def delete_deal(self, deal_id: int) -> None:
        self._request("DELETE", f"/deals/{deal_id}")

    # ----- tasks -----

    def list_tasks(
        self,
        is_done: Optional[bool] = None,
        client_id: Optional[int] = None,
        deal_id: Optional[int] = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": 5000}
        if is_done is not None:
            params["is_done"] = str(is_done).lower()
        if client_id is not None:
            params["client_id"] = client_id
        if deal_id is not None:
            params["deal_id"] = deal_id
        return self._request("GET", "/tasks", params=params)

    def create_task(self, payload: dict) -> dict:
        return self._request("POST", "/tasks", data=payload)

    def update_task(self, task_id: int, payload: dict) -> dict:
        return self._request("PATCH", f"/tasks/{task_id}", data=payload)

    def set_task_done(self, task_id: int, is_done: bool = True) -> dict:
        return self._request(
            "POST", f"/tasks/{task_id}/done", data={"is_done": is_done}
        )

    def delete_task(self, task_id: int) -> None:
        self._request("DELETE", f"/tasks/{task_id}")

    # ----- transport -----

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Any = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean:
                url = f"{url}?{urllib.parse.urlencode(clean)}"

        body: Optional[bytes] = None
        headers = {"Accept": "application/json"}
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                detail = parsed.get("detail", detail)
            except Exception:
                pass
            raise ApiError(f"HTTP {exc.code}: {detail}", status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise ApiError(
                f"Сервер недоступен ({self.base_url}). "
                f"Запустите API: python crm.py\n{exc.reason}"
            ) from exc
