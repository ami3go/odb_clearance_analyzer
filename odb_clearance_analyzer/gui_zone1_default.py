"""Runtime GUI extension for default Zone 1 voltage-assignment workflow."""

from __future__ import annotations

import builtins
import sys
from typing import Any, Callable


_PATCHED_ATTR = "_zone1_default_gui_patch_installed"
_IMPORT_HOOK_ATTR = "_odb_zone1_default_import_hook"


def main() -> None:
    """Launch the GUI after applying the Zone 1 default checkbox patch.

    This entry point is used by the console script and launchers so the
    checkbox does not depend only on import-hook timing.
    """

    from . import gui as gui_module

    _patch_gui_module(gui_module)
    gui_module.main()


def install_zone1_default_gui_patch() -> None:
    """Install a one-shot import hook that patches ``odb_clearance_analyzer.gui``."""

    module = sys.modules.get("odb_clearance_analyzer.gui")
    if module is not None:
        _patch_gui_module(module)
        return

    current_import = builtins.__import__
    if getattr(current_import, _IMPORT_HOOK_ATTR, False):
        return

    def import_hook(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[override]
        result = current_import(name, globals, locals, fromlist, level)
        module = sys.modules.get("odb_clearance_analyzer.gui")
        if module is not None:
            _patch_gui_module(module)
            if builtins.__import__ is import_hook:
                builtins.__import__ = current_import
        return result

    setattr(import_hook, _IMPORT_HOOK_ATTR, True)
    builtins.__import__ = import_hook


def _patch_gui_module(gui_module: Any) -> None:
    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None or getattr(cls, _PATCHED_ATTR, False):
        return

    def default_enabled(self: Any) -> bool:
        var = getattr(self, "voltage_default_all_nets_zone1", None)
        try:
            return bool(var.get())
        except Exception:
            return False

    def apply_default_zone1(self: Any) -> int:
        if not default_enabled(self):
            return 0
        store = getattr(self, "voltage_store", None)
        assignments = getattr(store, "assignments", {}) if store is not None else {}
        if not assignments:
            return 0
        normalize = getattr(gui_module, "normalize_galvanic_zone")
        zone_1 = getattr(gui_module, "GALVANIC_ZONE_1")
        blank_nets = [
            net
            for net, assignment in sorted(assignments.items())
            if not normalize(getattr(assignment, "galvanic_zone", ""))
        ]
        if not blank_nets:
            return 0
        return gui_module.review_service.apply_galvanic_zone_bulk(
            store, blank_nets, galvanic_zone=zone_1
        )

    def save_after_zone_change(self: Any) -> None:
        if hasattr(self, "_sync_voltage_settings_to_store"):
            self._sync_voltage_settings_to_store()
        assignments = getattr(getattr(self, "voltage_store", None), "assignments", {})
        if assignments and hasattr(self, "_save_voltage_store_safely"):
            self._save_voltage_store_safely()
        elif hasattr(self, "_save_voltage_settings_safely"):
            self._save_voltage_settings_safely()

    def apply_checkbox_setting(self: Any) -> None:
        changed = apply_default_zone1(self)
        save_after_zone_change(self)
        if hasattr(self, "_refresh_voltage_views"):
            self._refresh_voltage_views()
        elif hasattr(self, "_refresh_voltage_overview"):
            self._refresh_voltage_overview()
        if hasattr(self, "_append_log"):
            if default_enabled(self):
                self._append_log(
                    f"Voltage Guessing: default Zone 1 is enabled; assigned Zone 1 to {changed} net(s) with blank galvanic zone."
                )
            else:
                self._append_log(
                    "Voltage Guessing: default Zone 1 assignment is disabled; existing zones were not changed."
                )

    def coerce_bool(value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "y"}
        return bool(value)

    original_init = cls.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any):
        if not hasattr(self, "voltage_default_all_nets_zone1"):
            self.voltage_default_all_nets_zone1 = gui_module.BooleanVar(value=False)
        original_init(self, *args, **kwargs)

    cls.__init__ = patched_init
    cls._default_all_nets_zone1_enabled = default_enabled
    cls._apply_default_zone1_to_unassigned_assignments = apply_default_zone1
    cls._apply_default_all_nets_zone1_setting = apply_checkbox_setting

    original_settings = cls._current_voltage_guessing_settings

    def patched_settings(self: Any) -> dict[str, object]:
        settings = dict(original_settings(self))
        settings["default_all_nets_to_zone_1"] = default_enabled(self)
        return settings

    cls._current_voltage_guessing_settings = patched_settings

    original_apply_settings = cls._apply_voltage_guessing_settings

    def patched_apply_settings(
        self: Any, settings: dict[str, object] | None, *args: Any, **kwargs: Any
    ) -> None:
        original_apply_settings(self, settings, *args, **kwargs)
        settings = dict(settings or {})
        raw = settings.get(
            "default_all_nets_to_zone_1", settings.get("assign_all_nets_to_zone_1", None)
        )
        if raw is not None and hasattr(self, "voltage_default_all_nets_zone1"):
            self.voltage_default_all_nets_zone1.set(coerce_bool(raw))

    cls._apply_voltage_guessing_settings = patched_apply_settings

    original_create_tab = cls._create_voltage_guessing_tab

    def patched_create_tab(self: Any, parent: Any) -> None:
        original_create_tab(self, parent)
        _add_checkbox_to_overview(gui_module, self)

    cls._create_voltage_guessing_tab = patched_create_tab

    for method_name in (
        "_run_voltage_auto_detect",
        "_apply_voltage_safe_matches",
        "_apply_voltage_selected_suggestion",
        "_load_voltage_store_if_present",
    ):
        original = getattr(cls, method_name, None)
        if callable(original):
            setattr(
                cls,
                method_name,
                _wrap_assignment_mutator(original, apply_default_zone1, save_after_zone_change),
            )

    setattr(cls, _PATCHED_ATTR, True)


def _wrap_assignment_mutator(
    original: Callable[..., Any],
    apply_default_zone1: Callable[[Any], int],
    save_after_zone_change: Callable[[Any], None],
) -> Callable[..., Any]:
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        changed = apply_default_zone1(self)
        if changed:
            save_after_zone_change(self)
            if hasattr(self, "_refresh_voltage_views"):
                self._refresh_voltage_views()
            if hasattr(self, "_append_log"):
                self._append_log(
                    f"Voltage Guessing: default Zone 1 applied to {changed} net(s) with blank galvanic zone."
                )
        return result

    return wrapped


def _add_checkbox_to_overview(gui_module: Any, gui: Any) -> None:
    if getattr(gui, "_zone1_default_control_added", False):
        return
    notebook = getattr(gui, "voltage_notebook", None)
    if notebook is None:
        return
    try:
        overview_tab = notebook.nametowidget(notebook.tabs()[0])
    except Exception:
        return

    ttk = gui_module.ttk
    x_fill = getattr(gui_module, "X", "x")
    left = getattr(gui_module, "LEFT", "left")

    if hasattr(gui, "_make_card"):
        card = gui._make_card(
            overview_tab,
            "Galvanic zone defaults",
            "Bulk default for voltage assignments",
        )
    else:
        card = ttk.Frame(overview_tab)

    children = list(overview_tab.winfo_children())
    pack_options: dict[str, Any] = {"fill": x_fill, "pady": (0, 8)}
    if len(children) >= 3:
        pack_options["before"] = children[2]
    card.pack(**pack_options)

    row = ttk.Frame(card, style="Card.TFrame")
    row.pack(anchor="w", fill=x_fill, pady=(4, 0))
    ttk.Checkbutton(
        row,
        text="Assign all unassigned nets to Zone 1 by default",
        variable=gui.voltage_default_all_nets_zone1,
        command=gui._apply_default_all_nets_zone1_setting,
    ).pack(side=left, padx=(0, 10))
    ttk.Label(
        row,
        text=(
            "When enabled, Auto-detect/import fills blank galvanic-zone fields with Zone 1. "
            "Existing Zone 2/manual choices are preserved."
        ),
        style="Muted.TLabel",
        wraplength=900,
    ).pack(side=left)
    gui._zone1_default_control_added = True
