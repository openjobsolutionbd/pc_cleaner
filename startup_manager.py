"""
startup_manager.py
-------------------
Lists programs that launch automatically at Windows startup, and lets
the user disable/re-enable them.

SAFETY DESIGN: nothing here is ever permanently deleted.
  - Registry "Run" entries are moved to a backup key
    (HKCU\\Software\\PCCleanerBackup\\DisabledRun) when disabled,
    and moved back when re-enabled.
  - Startup-folder shortcuts are moved into a "Disabled (PCCleaner)"
    subfolder when disabled, and moved back when re-enabled.
This means a mistake is always reversible from inside the app itself.

Only works on Windows (winreg is a Windows-only stdlib module).
"""

import os

try:
    import winreg
    _HAS_WINREG = True
except ImportError:
    _HAS_WINREG = False

BACKUP_KEY_PATH = r"Software\PCCleanerBackup\DisabledRun"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_windows() -> bool:
    return os.name == "nt" and _HAS_WINREG


def _startup_folders():
    folders = {}
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", "")
    if appdata:
        folders["user"] = os.path.join(
            appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
    if programdata:
        folders["common"] = os.path.join(
            programdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
    return folders


def _disabled_subfolder(startup_folder: str) -> str:
    return os.path.join(startup_folder, "Disabled (PCCleaner)")


def list_startup_items() -> list:
    """Returns [{id, name, command, source, enabled}] for every item found
    in the Run registry keys and the Startup folders (including ones
    already disabled by this app, marked enabled=False).
    """
    items = []
    if not is_windows():
        return items

    # Registry: HKCU and HKLM Run keys
    for hive, hive_name in ((winreg.HKEY_CURRENT_USER, "hkcu"), (winreg.HKEY_LOCAL_MACHINE, "hklm")):
        items.extend(_read_run_key(hive, RUN_KEY_PATH, f"registry-{hive_name}", enabled=True))
        items.extend(_read_run_key(hive, BACKUP_KEY_PATH, f"registry-{hive_name}", enabled=False))

    # Startup folders
    for scope, folder in _startup_folders().items():
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                full = os.path.join(folder, name)
                if os.path.isfile(full):
                    items.append({
                        "id": f"folder-{scope}:{name}",
                        "name": name,
                        "command": full,
                        "source": f"startup-folder-{scope}",
                        "enabled": True,
                    })
        disabled_folder = _disabled_subfolder(folder)
        if os.path.isdir(disabled_folder):
            for name in os.listdir(disabled_folder):
                full = os.path.join(disabled_folder, name)
                if os.path.isfile(full):
                    items.append({
                        "id": f"folder-{scope}:{name}",
                        "name": name,
                        "command": full,
                        "source": f"startup-folder-{scope}",
                        "enabled": False,
                    })

    return items


def _read_run_key(hive, key_path, source_label, enabled):
    results = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
    except OSError:
        return results
    try:
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            results.append({
                "id": f"{source_label}:{name}",
                "name": name,
                "command": value,
                "source": source_label,
                "enabled": enabled,
            })
            i += 1
    finally:
        winreg.CloseKey(key)
    return results


def disable_startup_item(item: dict, log=None) -> bool:
    """Moves the item to the backup location. Reversible via enable_startup_item."""
    if log is None:
        log = lambda msg: None
    if not is_windows():
        return False

    if item["source"].startswith("registry-"):
        hive = winreg.HKEY_CURRENT_USER if item["source"] == "registry-hkcu" else winreg.HKEY_LOCAL_MACHINE
        return _move_registry_value(hive, RUN_KEY_PATH, BACKUP_KEY_PATH, item["name"], log)

    if item["source"].startswith("startup-folder-"):
        scope = item["source"].replace("startup-folder-", "")
        folder = _startup_folders().get(scope)
        if not folder:
            return False
        return _move_file(
            os.path.join(folder, item["name"]),
            _disabled_subfolder(folder),
            log,
        )

    return False


def enable_startup_item(item: dict, log=None) -> bool:
    """Moves the item back from the backup location to its original spot."""
    if log is None:
        log = lambda msg: None
    if not is_windows():
        return False

    if item["source"].startswith("registry-"):
        hive = winreg.HKEY_CURRENT_USER if item["source"] == "registry-hkcu" else winreg.HKEY_LOCAL_MACHINE
        return _move_registry_value(hive, BACKUP_KEY_PATH, RUN_KEY_PATH, item["name"], log)

    if item["source"].startswith("startup-folder-"):
        scope = item["source"].replace("startup-folder-", "")
        folder = _startup_folders().get(scope)
        if not folder:
            return False
        return _move_file(
            os.path.join(_disabled_subfolder(folder), item["name"]),
            folder,
            log,
        )

    return False


def _move_registry_value(hive, from_path, to_path, value_name, log):
    """Moves a single registry value from one key to another.

    winreg has no atomic "move a value between two keys" call — this has
    to be a write to the destination followed by a delete from the
    source, as two separate registry operations. If the write succeeds
    but the delete fails (most commonly: this key needs Administrator
    and the write happened to land on a more permissive key than the
    delete did), the value would otherwise exist in both places at
    once and the item would show up twice (Enabled and Disabled). To
    avoid that, a failed delete triggers an immediate rollback of the
    write, and the log message says plainly what happened either way.
    """
    try:
        src_key = winreg.OpenKey(hive, from_path, 0, winreg.KEY_ALL_ACCESS)
    except OSError as e:
        log(f"Could not open registry key: {e}")
        return False

    try:
        try:
            value, value_type = winreg.QueryValueEx(src_key, value_name)
        except OSError as e:
            log(f"Could not read startup entry: {e}")
            return False

        # Step 1: copy the value into the destination key.
        try:
            dst_key = winreg.CreateKeyEx(hive, to_path, 0, winreg.KEY_ALL_ACCESS)
            try:
                winreg.SetValueEx(dst_key, value_name, 0, value_type, value)
            finally:
                winreg.CloseKey(dst_key)
        except OSError as e:
            log(f"Could not move startup entry: {e}")
            return False

        # Step 2: remove it from the source now that the copy exists.
        try:
            winreg.DeleteValue(src_key, value_name)
            return True
        except OSError as e:
            # The copy succeeded but the delete didn't — undo the copy so
            # the entry doesn't end up listed twice.
            try:
                undo_key = winreg.OpenKey(hive, to_path, 0, winreg.KEY_ALL_ACCESS)
                try:
                    winreg.DeleteValue(undo_key, value_name)
                finally:
                    winreg.CloseKey(undo_key)
                log(
                    f"Could not complete the change — still in its original location ({e}). "
                    "That spot usually needs Administrator. Nothing was duplicated."
                )
            except OSError:
                # Even the rollback failed (rare). Say so explicitly rather
                # than leaving a silent duplicate.
                log(
                    f"Copied the entry but could not remove the original ({e}). "
                    "It may now show up twice in the list (Enabled and Disabled) — "
                    "try again as Administrator, or remove the extra copy manually."
                )
            return False
    finally:
        winreg.CloseKey(src_key)


def _move_file(src, dst_folder, log):
    if not os.path.exists(src):
        log(f"Startup item not found: {src}")
        return False
    try:
        os.makedirs(dst_folder, exist_ok=True)
        dst = os.path.join(dst_folder, os.path.basename(src))
        os.replace(src, dst)
        return True
    except OSError as e:
        log(f"Could not move startup item: {e}")
        return False
