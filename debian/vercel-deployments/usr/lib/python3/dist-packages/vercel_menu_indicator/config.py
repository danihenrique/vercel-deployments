from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict


CONFIG_DIRNAME = "vercel-deployments"
CONFIG_FILENAME = "config.json"


@dataclass
class AppConfig:
    """Serializable application configuration.

    - token: Vercel API token
    - team_id: optional team slug/ID when token is team-scoped
    - refresh_interval: seconds between polls
    - max_items: number of deployments to display
    """

    token: str = ""
    team_id: str = ""
    refresh_interval: int = 30
    max_items: int = 10
    notify_prod_events: bool = True


def _config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    d = base / CONFIG_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _config_path() -> Path:
    return _config_dir() / CONFIG_FILENAME


def load_config() -> Dict[str, object]:
    p = _config_path()
    if not p.exists():
        return asdict(AppConfig())
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Provide defaults for any missing keys
        defaults = asdict(AppConfig())
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    except Exception:
        # Corrupted file: return defaults
        return asdict(AppConfig())


def save_config(data: Dict[str, object]) -> None:
    # Enforce expected keys and simple types
    cfg = AppConfig(
        token=str(data.get("token") or ""),
        team_id=str(data.get("team_id") or ""),
        refresh_interval=int(data.get("refresh_interval") or 30),
        max_items=int(data.get("max_items") or 10),
        # Default to True when key is absent
        notify_prod_events=bool(data.get("notify_prod_events")) if data.get("notify_prod_events") is not None else True,
    )
    p = _config_path()
    txt = json.dumps(asdict(cfg), ensure_ascii=False, indent=2)
    p.write_text(txt, encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except Exception:
        # Non-fatal on platforms without chmod
        pass


