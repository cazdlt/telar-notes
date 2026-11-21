"""Tests for configuration, plugin settings, Obsidian import, and vault registry."""

import json
import shutil
import subprocess

from telar.config import TelarConfig


def test_config_round_trip_and_active_vault_selection(tmp_path):
    work = tmp_path / "work"
    personal = tmp_path / "personal"
    work.mkdir()
    personal.mkdir()
    config = TelarConfig(tmp_path / "config.json")
    config.save(
        {
            "vaults": [
                {"name": "work", "path": str(work)},
                {"name": "personal", "path": str(personal)},
            ],
            "default_vault": "work",
            "font_size": 16,
            "deps": {"rg": True},
            "diagrams": {
                "default": "mermaid",
                "excalidraw_authenticated": True,
            },
        }
    )

    loaded = config.load()
    assert loaded["font_size"] == 16
    assert loaded["lang"] == "en"
    assert "deps" not in loaded
    assert "excalidraw_authenticated" not in loaded["diagrams"]
    assert config.get_active_vault(str(tmp_path / "missing-session"))["name"] == "work"
    session = tmp_path / ".session"
    session.write_text(json.dumps({"active_vault": "personal"}))
    assert config.get_active_vault(str(session))["name"] == "personal"


def test_folder_notes_plugin_setting_defaults_and_validates(api):
    _, settings = api.request("GET", "/api/settings")
    assert settings["vault_settings"]["plugins"]["folder-notes"] == {"enabled": True}
    plugins = {**settings["vault_settings"]["plugins"]}
    for value, expected in ((False, False), ("on", True)):
        plugins["folder-notes"] = {"enabled": value}
        _, saved = api.request(
            "POST",
            "/api/settings",
            {
                "preferences": settings["preferences"],
                "vault_settings": {"plugins": plugins},
            },
        )
        assert saved["vault_settings"]["plugins"]["folder-notes"]["enabled"] is expected


def test_settings_and_periodic_note_template(api):
    (api.work / "templates").mkdir()
    (api.work / "templates" / "daily.md").write_text(
        "# {{title}}\n{{date:YYYY/MM/DD}} {{query.file.filenameWithoutExtension}}\n"
    )
    status, settings = api.request("GET", "/api/settings")
    assert status == 200
    status, settings = api.request(
        "POST",
        "/api/settings",
        {
            "preferences": settings["preferences"],
            "vault_settings": settings["vault_settings"],
        },
    )
    assert status == 200
    status, created = api.request("POST", "/api/periodic/today", {"date": "2026-08-12"})
    assert status == 200
    assert created["path"] == "diario/2026/08/2026-08-12.md"
    assert "2026/08/12 {{query.file.filenameWithoutExtension}}" in created["content"]


def test_recent_files_plugin_settings_default_and_validate(api):
    status, settings = api.request("GET", "/api/settings")
    assert status == 200
    assert settings["vault_settings"]["plugins"]["recent-files"] == {
        "enabled": True,
        "limit": 20,
    }

    def save(recent):
        vault_settings = {"plugins": {**settings["vault_settings"]["plugins"]}}
        vault_settings["plugins"]["recent-files"] = recent
        _, saved = api.request(
            "POST",
            "/api/settings",
            {"preferences": settings["preferences"], "vault_settings": vault_settings},
        )
        return saved["vault_settings"]["plugins"]["recent-files"]

    assert save({"enabled": False, "limit": 35}) == {"enabled": False, "limit": 35}
    for invalid in (0, 201, True, "30", 20.5):
        assert save({"enabled": True, "limit": invalid})["limit"] == 20
    assert save({"enabled": "no", "limit": 20})["enabled"] is True


def test_excalidraw_plugin_setting_defaults_and_validates(api):
    _, settings = api.request("GET", "/api/settings")
    assert settings["vault_settings"]["plugins"]["excalidraw"] == {
        "enabled": True,
        "embed_width": 400,
    }
    plugins = {**settings["vault_settings"]["plugins"]}
    for value, expected in ((False, False), ("off", True)):
        plugins["excalidraw"] = {"enabled": value}
        _, saved = api.request(
            "POST",
            "/api/settings",
            {
                "preferences": settings["preferences"],
                "vault_settings": {"plugins": plugins},
            },
        )
        assert saved["vault_settings"]["plugins"]["excalidraw"]["enabled"] is expected


def test_excalidraw_embed_width_validates_and_imports_from_obsidian(api):
    _, settings = api.request("GET", "/api/settings")

    def save(width):
        plugins = {**settings["vault_settings"]["plugins"]}
        plugins["excalidraw"] = {"enabled": True, "embed_width": width}
        _, saved = api.request(
            "POST",
            "/api/settings",
            {
                "preferences": settings["preferences"],
                "vault_settings": {"plugins": plugins},
            },
        )
        return saved["vault_settings"]["plugins"]["excalidraw"]["embed_width"]

    assert save(600) == 600
    for invalid in (99, 2001, "500", True):
        assert save(invalid) == 400
    plugin = api.work / ".obsidian" / "plugins" / "obsidian-excalidraw-plugin"
    plugin.mkdir(parents=True)
    (plugin / "data.json").write_text(json.dumps({"width": "320"}))
    _, imported = api.request("POST", "/api/settings/import-obsidian", {})
    assert imported["vault_settings"]["plugins"]["excalidraw"]["embed_width"] == 320


def test_recent_files_limit_imports_from_obsidian_plugin(api):
    plugin = api.work / ".obsidian" / "plugins" / "recent-files-obsidian"
    plugin.mkdir(parents=True)
    (plugin / "data.json").write_text(json.dumps({"maxLength": 10, "recentFiles": []}))
    status, settings = api.request("POST", "/api/settings/import-obsidian", {})
    assert status == 200
    assert settings["vault_settings"]["plugins"]["recent-files"]["limit"] == 10


def test_font_size_preferences_validate_ranges(api):
    _, settings = api.request("GET", "/api/settings")
    assert settings["preferences"]["ui_font_size"] == 14
    for sent, expected in (
        ({"font_size": 20, "ui_font_size": 18}, (20, 18)),
        ({"font_size": 99, "ui_font_size": 5}, (16, 14)),
    ):
        _, saved = api.request(
            "POST",
            "/api/settings",
            {
                "preferences": {**settings["preferences"], **sent},
                "vault_settings": settings["vault_settings"],
            },
        )
        prefs = saved["preferences"]
        assert (prefs["font_size"], prefs["ui_font_size"]) == expected


def test_import_obsidian_imports_plugins_and_ignores_invalid_data(api):
    obsidian = api.work / ".obsidian"
    plugins = obsidian / "plugins"
    for folder, data in (
        (
            "periodic-notes",
            {
                "daily": {
                    "folder": "journal",
                    "format": "YYYY-MM-DD",
                    "template": "tpl/daily.md",
                    "enabled": False,
                }
            },
        ),
        (
            "obsidian-tasks-plugin",
            {
                "nextStatusSymbol": "/",
                "setDoneDate": False,
                "setCancelledDate": "invalid",
                "setCreatedDate": False,
                "enabled": False,
            },
        ),
    ):
        (plugins / folder).mkdir(parents=True)
        (plugins / folder / "data.json").write_text(json.dumps(data))
    (plugins / "recent-files-obsidian").mkdir(parents=True)
    (plugins / "recent-files-obsidian" / "data.json").write_text("{broken json")
    (obsidian / "community-plugins.json").write_text(json.dumps(["folder-notes"]))
    (obsidian / "app.json").write_text(
        json.dumps({"attachmentFolderPath": "../outside"})
    )

    status, imported = api.request("POST", "/api/settings/import-obsidian", {})
    assert status == 200
    vault_settings = imported["vault_settings"]
    assert vault_settings["plugins"]["periodic-notes"] == {
        "folder": "journal",
        "format": "YYYY-MM-DD",
        "template": "tpl/daily.md",
        "enabled": False,
    }
    assert vault_settings["plugins"]["tasks"] == {
        "enabled": False,
        "next_status_symbol": "/",
        "set_done_date": False,
        "set_cancelled_date": True,
        "set_created_date": False,
    }
    assert vault_settings["plugins"]["folder-notes"] == {"enabled": True}
    assert vault_settings["plugins"]["recent-files"]["limit"] == 20
    assert vault_settings["files"]["attachment_folder"] == "/"
    saved_entry = api.config.load()["vault_settings"][str(api.work.resolve())]
    assert saved_entry["imported_from_obsidian"]["version"] == 1
    assert saved_entry["imported_from_obsidian"]["at"]

    # Flat periodic-notes format and malformed community/app JSON also work safely.
    (plugins / "periodic-notes" / "data.json").write_text(
        json.dumps({"folder": "notes", "enabled": True})
    )
    (obsidian / "community-plugins.json").write_text("{bad")
    (obsidian / "app.json").write_text("{bad")
    status, second = api.request("POST", "/api/settings/import-obsidian", {})
    assert status == 200
    assert second["vault_settings"]["plugins"]["periodic-notes"]["folder"] == "notes"
    assert second["vault_settings"]["plugins"]["periodic-notes"]["enabled"] is True


def test_switching_vault_changes_files_served(api):
    status, _ = api.request("POST", "/api/session/vault", {"vault": "personal"})
    assert status == 200
    status, body = api.request("GET", "/api/files")
    assert status == 200
    assert [entry["path"] for entry in body["tree"]] == ["private.md"]


def test_switching_to_unknown_vault_is_rejected(api):
    status, _ = api.request("POST", "/api/session/vault", {"vault": "missing"})
    assert status == 404


def test_vaults_payload_reports_active_and_default(api):
    status, body = api.request("GET", "/api/vaults")
    assert status == 200
    assert [v["name"] for v in body["vaults"]] == ["work", "personal"]
    assert body["active"] == "work"
    assert body["default"] == "work"


def test_add_vault_registers_folder_with_unique_name(api):
    extra = api.root / "nested" / "work"
    extra.mkdir(parents=True, exist_ok=True)
    status, body = api.request("POST", "/api/vaults/add", {"path": str(extra)})
    assert status == 200
    assert body["vaults"][-1] == {"name": "work 2", "path": str(extra.resolve())}
    status, _ = api.request("POST", "/api/session/vault", {"vault": "work 2"})
    assert status == 200


def test_open_help_registers_bundled_vault_once(api):
    status, body = api.request("POST", "/api/vaults/help", {})
    assert status == 200
    assert body["help"] == "Telar Notes Help"
    assert [v["name"] for v in body["vaults"]].count(body["help"]) == 1
    status, again = api.request("POST", "/api/vaults/help", {})
    assert status == 200 and len(again["vaults"]) == len(body["vaults"])
    status, _ = api.request("POST", "/api/session/vault", {"vault": body["help"]})
    assert status == 200


def test_x_vault_header_scopes_one_request_without_switching_session(api):
    (api.personal / "only-personal.md").write_text("x")
    _, files = api.request("GET", "/api/files", headers={"X-Vault": "personal"})
    assert "only-personal.md" in str(files)
    status, body = api.request("GET", "/api/vaults", headers={"X-Vault": "personal"})
    assert status == 200 and body["active"] == "personal"
    status, body = api.request("GET", "/api/vaults")
    assert body["active"] == "work"


def test_add_vault_rejects_invalid_targets(api):
    cases = [
        ({"path": "relative/dir"}, 400),
        ({"path": str(api.root / "missing")}, 404),
        ({"path": str(api.work / "project.md")}, 404),
        ({"path": "/"}, 400),
        ({"path": str(api.personal)}, 409),
        ({"path": str(api.root), "name": "personal"}, 409),
    ]
    for body, expected in cases:
        status, _ = api.request("POST", "/api/vaults/add", body)
        assert status == expected, body
    assert len(api.config.load()["vaults"]) == 2


def test_remove_vault_unregisters_without_touching_files(api):
    status, body = api.request("POST", "/api/vaults/default", {"vault": "personal"})
    assert status == 200
    assert body["default"] == "personal"
    status, body = api.request("POST", "/api/vaults/remove", {"vault": "personal"})
    assert status == 200
    assert [v["name"] for v in body["vaults"]] == ["work"]
    assert body["default"] == "work"
    assert (api.personal / "private.md").exists()


def test_remove_vault_guards_active_last_and_unknown(api):
    for name, expected in (("work", 409), ("missing", 404)):
        status, _ = api.request("POST", "/api/vaults/remove", {"vault": name})
        assert status == expected
    api.config.save({"vaults": [{"name": "work", "path": str(api.work)}]})
    status, body = api.request("POST", "/api/vaults/remove", {"vault": "work"})
    assert status == 409
    assert body["error"] == "cannot remove the last vault"


def test_first_vault_change_persists_launch_vault_as_default(api):
    api.config.save({"vaults": []})
    status, body = api.request("GET", "/api/vaults")
    assert body["vaults"] == [{"name": "work", "path": str(api.work)}]
    status, body = api.request("POST", "/api/vaults/add", {"path": str(api.personal)})
    assert status == 200
    saved = api.config.load()
    assert [v["name"] for v in saved["vaults"]] == ["work", "personal"]
    assert saved["default_vault"] == "work"


def test_pick_vault_folder_reports_path_cancel_and_platform(api, monkeypatch):
    outcomes = iter(
        [
            subprocess.CompletedProcess([], 0, "/Users/me/Notes/\n", ""),
            subprocess.CompletedProcess([], 1, "", "User canceled. (-128)"),
        ]
    )
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/osascript")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: next(outcomes))
    assert api.request("POST", "/api/vaults/pick", {}) == (
        200,
        {"path": "/Users/me/Notes"},
    )
    assert api.request("POST", "/api/vaults/pick", {}) == (200, {"cancelled": True})
    monkeypatch.setattr(shutil, "which", lambda _: None)
    status, _ = api.request("POST", "/api/vaults/pick", {})
    assert status == 501
