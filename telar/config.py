"""Configuration, vault settings, and Obsidian settings import."""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from datetime import datetime
from typing import Any, TypeGuard

BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
CONFIG_DIR = (
    pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config")
    / "telar"
)
WEB_DIR = BASE_DIR / "web"
DIST_DIR = WEB_DIR / "dist"
HELP_DIR = BASE_DIR / "help"
HELP_VAULT_NAME = "Telar Notes Help"

DEFAULT_CONFIG: dict[str, Any] = {
    "vaults": [],
    "default_vault": None,
    "lang": "en",
    "theme_override": None,
    "font_size": 14,
    "diagrams": {"default": "mermaid"},
    "settings_version": 1,
    "preferences": {
        "theme": "dark",
        "aesthetic": "ink",
        "font_size": 16,
        "ui_font_size": 14,
        "persistent_live_preview": True,
    },
    "vault_settings": {},
}
DEFAULT_PREFERENCES: dict[str, Any] = {
    "theme": "dark",
    "aesthetic": "ink",
    "font_size": 16,
    "ui_font_size": 14,
    "persistent_live_preview": True,
}
DEFAULT_TASKS_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "next_status_symbol": "x",
    "set_done_date": True,
    "set_cancelled_date": True,
    "set_created_date": True,
}
DEFAULT_PERIODIC_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "folder": "diario",
    "format": "YYYY/MM/YYYY-MM-DD",
    "template": "templates/daily.md",
}
DEFAULT_RECENT_FILES_SETTINGS: dict[str, Any] = {"enabled": True, "limit": 20}
DEFAULT_EXCALIDRAW_SETTINGS: dict[str, Any] = {"enabled": True, "embed_width": 400}
DEFAULT_FOLDER_NOTES_SETTINGS: dict[str, Any] = {"enabled": False}
DEFAULT_FILES_SETTINGS: dict[str, Any] = {
    "attachment_folder": "/"
}  # Obsidian's default: vault root
EXCALIDRAW_EMBED_WIDTH_RANGE = (100, 2000)
RECENT_FILES_LIMIT_RANGE = (1, 200)


def atomic_write_text(path: pathlib.Path, content: str) -> None:
    """Write text atomically, keeping a valid previous version on interruption.

    The replacement is a new inode, so the original creation time is carried over.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        carry_birthtime(path, temporary)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def carry_birthtime(source: pathlib.Path, target: pathlib.Path) -> None:
    """Give ``target`` the birth time of ``source`` where the filesystem records one.

    APFS/HFS+ lower the birth time when mtime is set before it, so setting mtime to
    the old birth time and then restoring it leaves only the birth time changed.
    """
    try:
        birth = os.stat(source).st_birthtime  # type: ignore[attr-defined]
    except (FileNotFoundError, AttributeError):
        return  # new file, or no birth time on this platform
    current = os.stat(target)
    os.utime(target, (current.st_atime, birth))
    os.utime(target, ns=(current.st_atime_ns, current.st_mtime_ns))


def valid_attachment_folder(value: object) -> TypeGuard[str]:
    """Return True if value is a safe vault-relative attachment folder spec."""
    if not isinstance(value, str) or len(value) > 200 or "\\" in value:
        return False
    return ".." not in pathlib.PurePosixPath(value.strip()).parts


def vault_settings(cfg: dict[str, Any], vault: pathlib.Path) -> dict[str, Any]:
    """Get validated, defaulted plugin settings for one canonical vault path."""
    key = str(vault.resolve())
    all_settings = cfg.get("vault_settings")
    entry = all_settings.get(key, {}) if isinstance(all_settings, dict) else {}
    plugins = entry.get("plugins", {}) if isinstance(entry, dict) else {}
    tasks = dict(DEFAULT_TASKS_SETTINGS)
    periodic = dict(DEFAULT_PERIODIC_SETTINGS)
    if isinstance(plugins.get("tasks"), dict):
        tasks.update({k: v for k, v in plugins["tasks"].items() if k in tasks})
    if isinstance(plugins.get("periodic-notes"), dict):
        periodic.update(
            {k: v for k, v in plugins["periodic-notes"].items() if k in periodic}
        )
    recent = dict(DEFAULT_RECENT_FILES_SETTINGS)
    raw_recent = plugins.get("recent-files")
    if isinstance(raw_recent, dict):
        if isinstance(raw_recent.get("enabled"), bool):
            recent["enabled"] = raw_recent["enabled"]
        limit = raw_recent.get("limit")
        low, high = RECENT_FILES_LIMIT_RANGE
        if type(limit) is int and low <= limit <= high:
            recent["limit"] = limit
    excalidraw = dict(DEFAULT_EXCALIDRAW_SETTINGS)
    raw_excalidraw = plugins.get("excalidraw")
    if isinstance(raw_excalidraw, dict):
        if isinstance(raw_excalidraw.get("enabled"), bool):
            excalidraw["enabled"] = raw_excalidraw["enabled"]
        width = raw_excalidraw.get("embed_width")
        low, high = EXCALIDRAW_EMBED_WIDTH_RANGE
        if type(width) is int and low <= width <= high:
            excalidraw["embed_width"] = width
    folder_notes = dict(DEFAULT_FOLDER_NOTES_SETTINGS)
    raw_folder_notes = plugins.get("folder-notes")
    if isinstance(raw_folder_notes, dict) and isinstance(
        raw_folder_notes.get("enabled"), bool
    ):
        folder_notes["enabled"] = raw_folder_notes["enabled"]
    files = dict(DEFAULT_FILES_SETTINGS)
    raw_files = entry.get("files") if isinstance(entry, dict) else None
    if isinstance(raw_files, dict) and valid_attachment_folder(
        raw_files.get("attachment_folder")
    ):
        files["attachment_folder"] = raw_files["attachment_folder"].strip()
    return {
        "files": files,
        "plugins": {
            "tasks": tasks,
            "periodic-notes": periodic,
            "recent-files": recent,
            "excalidraw": excalidraw,
            "folder-notes": folder_notes,
        },
    }


def validate_preferences(raw_preferences: dict[str, Any]) -> dict[str, Any]:
    """Validate and clamp user preferences against defaults."""
    valid = dict(DEFAULT_PREFERENCES)
    for key, value in raw_preferences.items():
        if key == "font_size" and isinstance(value, (int, float)) and 10 <= value <= 32:
            valid[key] = int(value)
        elif (
            key == "ui_font_size"
            and isinstance(value, (int, float))
            and 10 <= value <= 24
        ):
            valid[key] = int(value)
        elif (
            key in {"theme", "aesthetic"}
            and isinstance(value, str)
            and len(value) <= 20
        ):
            valid[key] = value
        elif key == "persistent_live_preview" and isinstance(value, bool):
            valid[key] = value
    return valid


def settings_payload(cfg: dict[str, Any], vault: pathlib.Path) -> dict[str, Any]:
    """Expose only Telar Notes settings plus the active vault settings."""
    preferences = dict(DEFAULT_PREFERENCES)
    raw = cfg.get("preferences")
    if isinstance(raw, dict):
        preferences.update({k: v for k, v in raw.items() if k in preferences})
    return {
        "preferences": preferences,
        "vault": str(vault.resolve()),
        "vault_settings": vault_settings(cfg, vault),
        "settings_version": 1,
    }


def import_obsidian_settings(
    cfg: dict[str, Any], vault: pathlib.Path
) -> dict[str, Any]:
    """Import supported plugin and attachment settings from ``.obsidian/``."""
    imported = vault_settings(cfg, vault)
    imported_at = datetime.now().isoformat(timespec="seconds")
    sources = {
        "tasks": vault
        / ".obsidian"
        / "plugins"
        / "obsidian-tasks-plugin"
        / "data.json",
        "periodic-notes": vault
        / ".obsidian"
        / "plugins"
        / "periodic-notes"
        / "data.json",
        "recent-files": vault
        / ".obsidian"
        / "plugins"
        / "recent-files-obsidian"
        / "data.json",
        "excalidraw": vault
        / ".obsidian"
        / "plugins"
        / "obsidian-excalidraw-plugin"
        / "data.json",
    }
    for plugin, source in sources.items():
        if not source.is_file():
            continue
        try:
            external = json.loads(source.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        target = imported["plugins"][plugin]
        if plugin == "periodic-notes":
            daily = (
                external.get("daily")
                if isinstance(external.get("daily"), dict)
                else external
            )
            mapping = {
                "folder": "folder",
                "format": "format",
                "template": "template",
                "enabled": "enabled",
            }
        elif plugin == "recent-files":
            mapping = {"maxLength": "limit"}
            daily = external
        elif plugin == "excalidraw":
            # Obsidian stores the default embed width as a string ("400").
            width = str(external.get("width", "")).strip()
            if width.isdigit():
                external = {"embed_width": int(width)}
            mapping = {"embed_width": "embed_width"}
            daily = external
        else:
            mapping = {
                "nextStatusSymbol": "next_status_symbol",
                "setDoneDate": "set_done_date",
                "setCancelledDate": "set_cancelled_date",
                "setCreatedDate": "set_created_date",
                "enabled": "enabled",
            }
            daily = external
        for source_key, target_key in mapping.items():
            value = daily.get(source_key) if isinstance(daily, dict) else None
            if isinstance(value, type(target[target_key])):
                target[target_key] = value

    community = vault / ".obsidian" / "community-plugins.json"
    if community.is_file():
        try:
            installed = json.loads(community.read_text())
        except (OSError, json.JSONDecodeError):
            installed = []
        if isinstance(installed, list) and "folder-notes" in installed:
            imported["plugins"]["folder-notes"]["enabled"] = True

    app_json = vault / ".obsidian" / "app.json"
    if app_json.is_file():
        try:
            folder = json.loads(app_json.read_text()).get("attachmentFolderPath")
        except (OSError, json.JSONDecodeError):
            folder = None
        if valid_attachment_folder(folder):
            imported["files"]["attachment_folder"] = folder.strip()

    entries = cfg.setdefault("vault_settings", {})
    existing = entries.get(str(vault.resolve()), {})
    entries[str(vault.resolve())] = {
        **(existing if isinstance(existing, dict) else {}),
        **imported,
        "imported_from_obsidian": {"at": imported_at, "version": 1},
    }
    return cfg


class TelarConfig:
    """Persistent configuration store for registered vaults and preferences."""

    def __init__(self, config_path: str | pathlib.Path | None = None):
        self.config_path = (
            pathlib.Path(config_path) if config_path else (CONFIG_DIR / "config.json")
        )

    def load(self) -> dict[str, Any]:
        """Load configuration from disk, merging missing defaults."""
        if not self.config_path.exists():
            return json.loads(json.dumps(DEFAULT_CONFIG))
        with open(self.config_path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        result = json.loads(json.dumps(DEFAULT_CONFIG))
        result.update(data)
        result.pop("deps", None)
        raw_diagrams = result.get("diagrams")
        diagrams = raw_diagrams.copy() if isinstance(raw_diagrams, dict) else {}
        diagrams.pop("excalidraw_authenticated", None)
        result["diagrams"] = diagrams
        return result

    def save(self, data: dict[str, Any]) -> None:
        """Persist configuration atomically to disk."""
        atomic_write_text(self.config_path, json.dumps(data, indent=2) + "\n")

    def get_active_vault(self, session_path: str) -> dict[str, Any]:
        """Return the active vault entry from session override, default, or first."""
        cfg = self.load()
        vaults = {v["name"]: v for v in cfg.get("vaults", [])}
        if not vaults:
            return {}
        try:
            session = json.loads(pathlib.Path(session_path).read_text())
            name = session.get("active_vault")
            if name and name in vaults:
                return vaults[name]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        default = cfg.get("default_vault")
        if default and default in vaults:
            return vaults[default]
        return next(iter(vaults.values()))
