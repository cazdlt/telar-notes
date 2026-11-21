"""Pydantic v2 request schemas for Telar Notes HTTP routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NoteWriteRequest(BaseModel):
    """Request body for ``POST /api/note``."""

    path: str = Field(min_length=1)
    content: str = ""
    base_revision: str | None = None
    force: bool = False


class NotePatchRequest(BaseModel):
    """Request body for ``POST /api/note/patch``."""

    model_config = ConfigDict(extra="allow")

    path: str = Field(min_length=1)
    op: str = ""
    base_revision: str | None = None
    dry_run: bool = False
    old: str | None = None
    new: str | None = None
    content: str | None = None
    anchor: str | None = None
    heading: str | None = None


class PeriodicTodayRequest(BaseModel):
    """Request body for ``POST /api/periodic/today``."""

    date: str | None = None


class AttachRequest(BaseModel):
    """Request body for ``POST /api/attach``."""

    note: str | None = None
    dir: str | None = None
    filename: str
    data_b64: str

    @field_validator("filename")
    @classmethod
    def _validate_filename(cls, value: str) -> str:
        """Reject empty, dot, or path-separating attachment filenames."""
        if not value or value in (".", "..") or "/" in value or "\\" in value:
            raise ValueError("note or dir, plus safe filename and data_b64, required")
        return value

    @model_validator(mode="after")
    def _require_target(self) -> AttachRequest:
        """Require either ``note`` or ``dir`` to anchor the attachment."""
        if not (self.note or self.dir):
            raise ValueError("note or dir, plus safe filename and data_b64, required")
        return self


class PathRequest(BaseModel):
    """Request body carrying a single vault-relative path."""

    path: str = Field(min_length=1)


class RenameRequest(BaseModel):
    """Request body for ``POST /api/rename``."""

    model_config = ConfigDict(populate_by_name=True)

    src: str = Field(alias="from", min_length=1)
    dst: str = Field(alias="to", min_length=1)


class SettingsUpdateRequest(BaseModel):
    """Request body for ``POST /api/settings``."""

    preferences: dict[str, Any]
    vault_settings: dict[str, Any]


class VaultNameRequest(BaseModel):
    """Request body carrying a registered vault name."""

    vault: str = Field(min_length=1)


class VaultAddRequest(BaseModel):
    """Request body for ``POST /api/vaults/add``."""

    path: str
    name: str | None = None

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        """Require a non-blank vault path."""
        if not value.strip():
            raise ValueError("path required")
        return value.strip()

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        """Reject whitespace-only vault names when provided."""
        if value is not None and not value.strip():
            raise ValueError("invalid name")
        return value.strip()[:64] if value is not None else None


class TaskAddRequest(BaseModel):
    """Request body for ``POST /api/tasks/add``."""

    model_config = ConfigDict(extra="allow")

    path: str = Field(min_length=1)
    description: str = ""
    status: str | None = None
    priority: str | None = None
    dates: dict[str, Any] | None = None
    tags: list[str] | None = None
    block_id: str | None = None
    children: list[str] | None = None
    anchor: str | None = None
    heading: str | None = None
    dry_run: bool = False


class TaskUpdateRequest(BaseModel):
    """Request body for ``POST /api/tasks/update``."""

    location: dict[str, Any]
    patch: dict[str, Any]
    dry_run: bool = False


class TaskBlockIdRequest(BaseModel):
    """Request body for ``POST /api/tasks/block-id``."""

    location: dict[str, Any]
