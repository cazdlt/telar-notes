"""Configuration, vault settings, and Obsidian settings import."""

from __future__ import annotations

import json
import math
import os
import pathlib
import tempfile
from datetime import datetime
from typing import Any, TypeGuard

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
CONFIG_DIR = (
    pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config")
    / "telar"
)
WEB_DIR = BASE_DIR / "web"
DIST_DIR = WEB_DIR / "dist"
HELP_DIR = BASE_DIR / "help"
HELP_VAULT_NAME = "Telar Notes Help"

EXCALIDRAW_EMBED_WIDTH_RANGE = (100, 2000)
RECENT_FILES_LIMIT_RANGE = (1, 200)


class _FallbackModel(BaseModel):
    """Base model that coerces non-dict inputs and falls back per-field on errors."""

    model_config = ConfigDict(extra="ignore", strict=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce_non_dict(cls, data: Any) -> Any:
        return data if isinstance(data, dict) else {}

    @field_validator("*", mode="wrap")
    @classmethod
    def _fallback_on_error(
        cls,
        value: Any,
        handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> Any:
        try:
            return handler(value)
        except ValidationError:
            assert info.field_name is not None
            field = cls.model_fields[info.field_name]
            if field.default_factory is not None:
                factory: Any = field.default_factory
                return factory()
            return field.default


class Preferences(_FallbackModel):
    """Validated user UI and editor preferences."""

    theme: str = Field(default="dark", max_length=20)
    aesthetic: str = Field(default="ink", max_length=20)
    font_size: int = Field(default=16, ge=10, le=32)
    ui_font_size: int = Field(default=14, ge=10, le=24)
    persistent_live_preview: bool = True

    @field_validator("font_size", "ui_font_size", mode="before")
    @classmethod
    def _truncate_finite_float(cls, value: Any) -> Any:
        if isinstance(value, float) and math.isfinite(value):
            return int(value)
        return value


class TasksSettings(_FallbackModel):
    """Settings for the Tasks plugin."""

    enabled: bool = True
    next_status_symbol: str = "x"
    set_done_date: bool = True
    set_cancelled_date: bool = True
    set_created_date: bool = True


class PeriodicNotesSettings(_FallbackModel):
    """Settings for the Periodic Notes plugin."""

    enabled: bool = True
    folder: str = "diario"
    format: str = "YYYY/MM/YYYY-MM-DD"
    template: str = "templates/daily.md"


class RecentFilesSettings(_FallbackModel):
    """Settings for the Recent Files plugin."""

    enabled: bool = True
    limit: int = Field(
        default=20, ge=RECENT_FILES_LIMIT_RANGE[0], le=RECENT_FILES_LIMIT_RANGE[1]
    )


class ExcalidrawSettings(_FallbackModel):
    """Settings for the Excalidraw plugin."""

    enabled: bool = True
    embed_width: int = Field(
        default=400,
        ge=EXCALIDRAW_EMBED_WIDTH_RANGE[0],
        le=EXCALIDRAW_EMBED_WIDTH_RANGE[1],
    )


class FolderNotesSettings(_FallbackModel):
    """Settings for the Folder Notes plugin."""

    enabled: bool = True


class FilesSettings(_FallbackModel):
    """Vault file and attachment settings."""

    attachment_folder: str = "/"  # Obsidian's default: vault root

    @field_validator("attachment_folder", mode="before")
    @classmethod
    def _validate_attachment_folder(cls, value: Any) -> str:
        if not valid_attachment_folder(value):
            raise ValueError("invalid attachment folder")
        return value.strip()


class PluginsSettings(_FallbackModel):
    """Container for per-vault plugin settings."""

    tasks: TasksSettings = Field(default_factory=TasksSettings)
    periodic_notes: PeriodicNotesSettings = Field(
        default_factory=PeriodicNotesSettings, alias="periodic-notes"
    )
    recent_files: RecentFilesSettings = Field(
        default_factory=RecentFilesSettings, alias="recent-files"
    )
    excalidraw: ExcalidrawSettings = Field(default_factory=ExcalidrawSettings)
    folder_notes: FolderNotesSettings = Field(
        default_factory=FolderNotesSettings, alias="folder-notes"
    )


class VaultSettings(_FallbackModel):
    """Validated per-vault settings payload."""

    files: FilesSettings = Field(default_factory=FilesSettings)
    plugins: PluginsSettings = Field(default_factory=PluginsSettings)


DEFAULT_PREFERENCES: dict[str, Any] = Preferences().model_dump()
DEFAULT_TASKS_SETTINGS: dict[str, Any] = TasksSettings().model_dump()
DEFAULT_PERIODIC_SETTINGS: dict[str, Any] = PeriodicNotesSettings().model_dump()
DEFAULT_RECENT_FILES_SETTINGS: dict[str, Any] = RecentFilesSettings().model_dump()
DEFAULT_EXCALIDRAW_SETTINGS: dict[str, Any] = ExcalidrawSettings().model_dump()
DEFAULT_FOLDER_NOTES_SETTINGS: dict[str, Any] = FolderNotesSettings().model_dump()
DEFAULT_FILES_SETTINGS: dict[str, Any] = FilesSettings().model_dump()
DEFAULT_CONFIG: dict[str, Any] = {
    "vaults": [],
    "default_vault": None,
    "lang": "en",
    "theme_override": None,
    "font_size": 14,
    "diagrams": {"default": "mermaid"},
    "settings_version": 1,
    "preferences": dict(DEFAULT_PREFERENCES),
    "vault_settings": {},
}


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
    return VaultSettings.model_validate(entry).model_dump(by_alias=True)


def validate_preferences(raw_preferences: dict[str, Any]) -> dict[str, Any]:
    """Validate and clamp user preferences against defaults."""
    return Preferences.model_validate(raw_preferences).model_dump()


def settings_payload(cfg: dict[str, Any], vault: pathlib.Path) -> dict[str, Any]:
    """Expose only Telar Notes settings plus the active vault settings."""
    raw = cfg.get("preferences")
    return {
        "preferences": validate_preferences(raw if isinstance(raw, dict) else {}),
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
