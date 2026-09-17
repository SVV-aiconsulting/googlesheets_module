"""
Сохранение настроек Google для Tkinter-GUI в текстовый файл.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
PREFS_PATH = _ROOT / "data" / "google_gui_settings.txt"


@dataclass
class GoogleGuiPrefs:
    oauth_client_secret: str = ""
    oauth_token: str = ""
    folder_id: str = ""

    def resolve(self, key: str) -> Path:
        raw = getattr(self, key)
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = _ROOT / path
        return path


def load_prefs(path: Path = PREFS_PATH) -> GoogleGuiPrefs:
    # Стартовые значения — из .env, затем перекрываются файлом настроек GUI
    prefs = GoogleGuiPrefs(
        oauth_client_secret=os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET_PATH", "").strip(),
        oauth_token=os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "").strip()
        or "credentials/token.json",
        folder_id=os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip(),
    )
    if not path.is_file():
        return prefs
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return GoogleGuiPrefs(
        oauth_client_secret=data.get("oauth_client_secret", prefs.oauth_client_secret),
        oauth_token=data.get("oauth_token", prefs.oauth_token),
        folder_id=data.get("folder_id", prefs.folder_id),
    )


def save_prefs(prefs: GoogleGuiPrefs, path: Path = PREFS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Настройки Google для Exelio CRM GUI",
        "# Файл перезаписывается из окна «Google»",
        f"oauth_client_secret={prefs.oauth_client_secret}",
        f"oauth_token={prefs.oauth_token}",
        f"folder_id={prefs.folder_id}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
