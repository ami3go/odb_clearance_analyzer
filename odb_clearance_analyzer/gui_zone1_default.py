"""Visible GUI integration for default Zone 1 voltage-assignment workflow."""

from __future__ import annotations

import builtins
import sys
from typing import Any, Callable


_PATCHED_ATTR = "_zone1_default_gui_patch_installed_v2"
_IMPORT_HOOK_ATTR = "_odb_zone1_default_import_hook"
_ORIGINAL_INIT_ATTR = "_zone1_default_original_init"
_ORIGINAL_CREATE_TAB_ATTR = "_zone1_default_original_create_tab"
_ORIGINAL_SETTINGS_ATTR = "_zone1_default_original_settings"
_ORIGINAL_APPLY_SETTINGS_ATTR = "_zone1_default_original_apply_settings"
_ORIGINAL_MUTATOR_PREFIX = "_zone1_default_original_"
_CHECKBOX_TEXT = "Assign all unassigned nets to Zone 1 automatically"
_SETTING_KEY = "default_all_nets_to_zone_1"


def main() -> None:
    """Launch the GUI after applying the visible Zone 1 checkbox integration."""

    from . import gui as gui_module

    _patch_gui_module(gui_module)
    gui_module.main()


def install_zone1_default_gui_patch() -> None:
    """Patch ``odb_clearance_analyzer.gui`` now or when it is imported later."""

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
    """Install a robust runtime patch on ClearanceGui.

    The previous implementation only wrapped tab creation. That was too fragile:
    if helper methods already existed, the patch could return before the visible
    control was inserted. This version also runs after ``ClearanceGui.__init__``
    and places the checkbox directly inside the already-visible workflow card.
    """

    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None:
        return

    # Always publish/refresh these methods, even if an older patch ran already.
    cls._default_all_nets_zone1_enabled = _make_default_enabled()
    cls._apply_default_zone1_to_unassigned_assignments = _make_apply_default_zone1(gui_module)
    cls._apply_default_all_nets_zone1_setting = _make_apply_checkbox_setting(gui_module)

    if not hasattr(cls, _ORIGINAL_INIT_ATTR):
        setattr(cls, _ORIGINAL_INIT_ATTR, cls.__init__)

        def patched_init(self: Any, *args: Any, **kwargs: Any):
            if not hasattr(self, "voltage_default_all_nets_zone1"):
                self.voltage_default_all_nets_zone1 = gui_module.BooleanVar(value=False)
            original_init = getattr(cls, _ORIGINAL_INIT_ATTR)
            original_init(self, *args, **kwargs)
            _add_checkbox_to_overview(gui_module, self)

        cls.__init__ = patched_init

    if not hasattr(cls, _ORIGINAL_CREATE_TAB_ATTR):
        setattr(cls, _ORIGINAL_CREATE_TAB_ATTR, cls._create_voltage_guessing_tab)

        def patched_create_tab(self: Any, parent: Any) -> None:
            original_create_tab = getattr(cls, _ORIGINAL_CREATE_TAB_ATTR)
            original_create_tab(self, parent)
            _add_checkbox_to_overview(gui_module, self)

        cls._create_voltage_guessing_tab = patched_create_tab

    if not hasattr(cls, _ORIGINAL_SETTINGS_ATTR):
        setattr(cls, _ORIGINAL_SETTINGS_ATTR, cls._current_voltage_guessing_settings)

        def patched_settings(self: Any) -> dict[str, object]:
            original_settings = getattr(cls, _ORIGINAL_SETTINGS_ATTR)
            settings = dict(original_settings(self))
            settings[_SETTING_KEY] = self._default_all_nets_zone1_enabled()
            return settings

        cls._current_voltage_guessing_settings = patched_settings

    if not hasattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR):
        setattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR, cls._apply_voltage_guessing_settings)

        def patched_apply_settings(
            self: Any, settings: dict[str, object] | None, *args: Any, **kwargs: Any
        ) -> None:
            original_apply_settings = getattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR)
            original_apply_settings(self, settings, *args, **kwargs)
            values = dict(settings or {})
            raw = values.get(_SETTING_KEY, values.get("assign_all_nets_to_zone_1", None))
            if raw is not None:
                _ensure_checkbox_var(gui_module, self).set(_coerce_bool(raw))
            _add_checkbox_to_overview(gui_module, self)

        cls._apply_voltage_guessing_settings = patched_apply_settings

    for method_name in (
        "_run_voltage_auto_detect",
        "_apply_voltage_safe_matches",
        "_apply_voltage_selected_suggestion",
        "_load_voltage_store_if_present",
    ):
        _wrap_assignment_mutator_once(gui_module, cls, method_name)

    setattr(cls, _PATCHED_ATTR, True)


def _make_default_enabled() -> Callable[[Any], bool]:
    def default_enabled(self: Any) -> bool:
        var = getattr(self, "voltage_default_all_nets_zone1", None)
        try:
            return bool(var.get())
        except Exception:
            return False

    return default_enabled


def _make_apply_default_zone1(gui_module: Any) -> Callable[[Any], int]:
    def apply_default_zone1(self: Any) -> int:
        if not self._default_all_nets_zone1_enabled():
            return 0
        store = getattr(self, "voltage_store", None)
        assignments = getattr(store, "assignments", {}) if store is not None else {}
        if not assignments:
            return 0
        blank_nets = [
            net
            for net, assignment in sorted(assignments.items())
            if not gui_module.normalize_galvanic_zone(getattr(assignment, "galvanic_zone", ""))
        ]
        if not blank_nets:
            return 0
        return gui_module.review_service.apply_galvanic_zone_bulk(
            store, blank_nets, galvanic_zone=gui_module.GALVANIC_ZONE_1
        )

    return apply_default_zone1


def _make_apply_checkbox_setting(gui_module: Any) -> Callable[[Any], None]:
    def apply_checkbox_setting(self: Any) -> None:
        _add_checkbox_to_overview(gui_module, self)
        changed = self._apply_default_zone1_to_unassigned_assignments()
        _save_zone1_default_state(self)
        if hasattr(self, "_refresh_voltage_views"):
            self._refresh_voltage_views()
        elif hasattr(self, "_refresh_voltage_overview"):
            self._refresh_voltage_overview()
        if hasattr(self, "_append_log"):
            if self._default_all_nets_zone1_enabled():
                self._append_log(
                    f"Voltage Guessing: default Zone 1 is enabled; assigned Zone 1 to {changed} net(s) with blank galvanic zone."
                )
            else:
                self._append_log(
                    "Voltage Guessing: default Zone 1 assignment is disabled; existing zones were not changed."
                )

    return apply_checkbox_setting


def _wrap_assignment_mutator_once(gui_module: Any, cls: Any, method_name: str) -> None:
    original_attr = _ORIGINAL_MUTATOR_PREFIX + method_name
    if hasattr(cls, original_attr):
        return
    original = getattr(cls, method_name, None)
    if not callable(original):
        return
    setattr(cls, original_attr, original)

    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        _add_checkbox_to_overview(gui_module, self)
        changed = self._apply_default_zone1_to_unassigned_assignments()
        if changed:
            _save_zone1_default_state(self)
            if hasattr(self, "_refresh_voltage_views"):
                self._refresh_voltage_views()
            if hasattr(self, "_append_log"):
                self._append_log(
                    f"Voltage Guessing: default Zone 1 applied to {changed} net(s) with blank galvanic zone."
                )
        return result

    setattr(cls, method_name, wrapped)


def _save_zone1_default_state(gui: Any) -> None:
    if hasattr(gui, "_sync_voltage_settings_to_store"):
        gui._sync_voltage_settings_to_store()
    store = getattr(gui, "voltage_store", None)
    settings = getattr(store, "settings", None) if store is not None else None
    if isinstance(settings, dict):
        settings[_SETTING_KEY] = gui._default_all_nets_zone1_enabled()
    assignments = getattr(store, "assignments", {}) if store is not None else {}
    if assignments and hasattr(gui, "_save_voltage_store_safely"):
        gui._save_voltage_store_safely()
    elif hasattr(gui, "_save_voltage_settings_safely"):
        gui._save_voltage_settings_safely()


def _ensure_checkbox_var(gui_module: Any, gui: Any):
    if not hasattr(gui, "voltage_default_all_nets_zone1"):
        gui.voltage_default_all_nets_zone1 = gui_module.BooleanVar(value=False)
    return gui.voltage_default_all_nets_zone1


def _widget_texts(widget: Any) -> list[str]:
    texts: list[str] = []
    try:
        text = widget.cget("text")
    except Exception:
        text = ""
    if text:
        texts.append(str(text))
    try:
        children = list(widget.winfo_children())
    except Exception:
        children = []
    for child in children:
        texts.extend(_widget_texts(child))
    return texts


def _find_voltage_overview_tab(gui: Any) -> Any | None:
    notebook = getattr(gui, "voltage_notebook", None)
    if notebook is None:
        return None
    try:
        tabs = notebook.tabs()
        if not tabs:
            return None
        return notebook.nametowidget(tabs[0])
    except Exception:
        return None


def _find_workflow_card(overview_tab: Any) -> Any:
    try:
        children = list(overview_tab.winfo_children())
    except Exception:
        return overview_tab
    for child in children:
        if "Voltage assignment workflow" in _widget_texts(child):
            return child
    return children[1] if len(children) > 1 else overview_tab


def _add_checkbox_to_overview(gui_module: Any, gui: Any) -> None:
    if getattr(gui, "_zone1_default_control_added", False):
        return
    overview_tab = _find_voltage_overview_tab(gui)
    if overview_tab is None:
        return
    if _CHECKBOX_TEXT in _widget_texts(overview_tab):
        gui._zone1_default_control_added = True
        return

    ttk = gui_module.ttk
    x_fill = getattr(gui_module, "X", "x")
    left = getattr(gui_module, "LEFT", "left")
    workflow = _find_workflow_card(overview_tab)
    row = ttk.Frame(workflow, style="Card.TFrame")

    pack_options: dict[str, Any] = {"anchor": "w", "fill": x_fill, "pady": (10, 0)}
    try:
        workflow_children = list(workflow.winfo_children())
        # Put the checkbox where the user is already looking: directly above
        # the existing "Max cell voltage" row in the workflow card.
        for child in workflow_children:
            if "Max cell voltage" in _widget_texts(child):
                pack_options["before"] = child
                break
    except Exception:
        pass
    row.pack(**pack_options)

    ttk.Checkbutton(
        row,
        text=_CHECKBOX_TEXT,
        variable=_ensure_checkbox_var(gui_module, gui),
        command=gui._apply_default_all_nets_zone1_setting,
    ).pack(side=left, padx=(0, 10))
    ttk.Label(
        row,
        text="Checked: blank galvanic-zone fields are filled with Zone 1 after Auto-detect/import. Manual Zone 2 choices are preserved.",
        style="Muted.TLabel",
        wraplength=900,
    ).pack(side=left)
    gui._zone1_default_control_added = True


def _coerce_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return bool(value)
