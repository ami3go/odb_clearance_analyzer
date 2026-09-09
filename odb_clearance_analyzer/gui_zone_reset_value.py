"""Configurable reset-voltage control for the Voltage Guessing -> Zones tab."""

from __future__ import annotations

import builtins
import sys
from typing import Any


_PATCHED_ATTR = "_zones_reset_value_patch_installed_v1"
_ORIGINAL_BUILD_ATTR = "_zones_reset_value_original_build_tab"
_ORIGINAL_INIT_ATTR = "_zones_reset_value_original_init"
_IMPORT_HOOK_ATTR = "_odb_zones_reset_value_import_hook"
_RESET_CONTROL_ATTR = "_zones_reset_value_control_added"


def install_zone_reset_value_support() -> None:
    """Install the configurable matrix-reset control when the GUI is available."""

    from . import gui_multi_zone as multi_zone

    if not getattr(multi_zone, _PATCHED_ATTR, False):
        original_build = getattr(multi_zone, "_build_tab", None)
        if callable(original_build):
            setattr(multi_zone, _ORIGINAL_BUILD_ATTR, original_build)

            def build_with_reset_control(gui_module: Any, gui: Any, parent: Any) -> None:
                original_build(gui_module, gui, parent)
                add_zone_reset_value_control(gui_module, gui)

            multi_zone._build_tab = build_with_reset_control
            setattr(multi_zone, _PATCHED_ATTR, True)

    module = sys.modules.get("odb_clearance_analyzer.gui")
    if module is not None:
        _patch_gui_init(module)
        return

    current_import = builtins.__import__
    if getattr(current_import, _IMPORT_HOOK_ATTR, False):
        return

    def hook(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[override]
        result = current_import(name, globals, locals, fromlist, level)
        module = sys.modules.get("odb_clearance_analyzer.gui")
        if module is not None:
            _patch_gui_init(module)
            if builtins.__import__ is hook:
                builtins.__import__ = current_import
        return result

    setattr(hook, _IMPORT_HOOK_ATTR, True)
    builtins.__import__ = hook


def _patch_gui_init(gui_module: Any) -> None:
    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None or getattr(cls, _PATCHED_ATTR, False):
        return

    if not hasattr(cls, _ORIGINAL_INIT_ATTR):
        setattr(cls, _ORIGINAL_INIT_ATTR, cls.__init__)

        def init(self: Any, *args: Any, **kwargs: Any):
            getattr(cls, _ORIGINAL_INIT_ATTR)(self, *args, **kwargs)
            add_zone_reset_value_control(gui_module, self)

        cls.__init__ = init

    setattr(cls, _PATCHED_ATTR, True)


def _ensure_reset_var(gui_module: Any, gui: Any):
    if not hasattr(gui, "voltage_zone_reset_value"):
        try:
            current = gui.voltage_galvanic_zone_voltage.get()
        except Exception:
            current = "1000"
        gui.voltage_zone_reset_value = gui_module.StringVar(value=str(current or "1000"))
    return gui.voltage_zone_reset_value


def add_zone_reset_value_control(gui_module: Any, gui: Any) -> None:
    """Add Reset voltage textbox/button into an already-built Zones tab."""

    if getattr(gui, _RESET_CONTROL_ATTR, False):
        return

    parent = getattr(gui, "voltage_zones_scroll_body", None) or getattr(gui, "voltage_zones_tab", None)
    if parent is None:
        return

    ttk = gui_module.ttk
    left = getattr(gui_module, "LEFT", "left")
    x = getattr(gui_module, "X", "x")

    row = ttk.Frame(parent, style="Card.TFrame")
    pack_options: dict[str, Any] = {"anchor": "w", "fill": x, "pady": (0, 8)}
    try:
        children = list(parent.winfo_children())
        if len(children) >= 2:
            pack_options["before"] = children[1]
    except Exception:
        pass
    row.pack(**pack_options)

    ttk.Label(row, text="Reset voltage, V").pack(side=left, padx=(0, 6))
    ttk.Entry(row, textvariable=_ensure_reset_var(gui_module, gui), width=10).pack(side=left, padx=(0, 8), ipady=2)
    ttk.Button(
        row,
        text="Reset all to value",
        command=lambda: reset_matrix_to_entered_value(gui_module, gui),
    ).pack(side=left, padx=(0, 8))
    ttk.Label(
        row,
        text="Fills every off-diagonal Zone X ↔ Zone Y cell with this value; diagonal remains 0 V.",
        style="Muted.TLabel",
        wraplength=760,
    ).pack(side=left)

    gui.voltage_zone_reset_value_row = row
    setattr(gui, _RESET_CONTROL_ATTR, True)


def _parse_reset_voltage(gui_module: Any, gui: Any) -> float | None:
    raw = str(_ensure_reset_var(gui_module, gui).get() or "").strip()
    try:
        value = float(raw)
    except Exception:
        gui_module.messagebox.showerror("Voltage zones", f"Reset voltage must be a number, got: {raw!r}")
        return None
    if not value > 0 or value in (float("inf"), float("-inf")) or value != value:
        gui_module.messagebox.showerror("Voltage zones", "Reset voltage must be a positive finite number.")
        return None
    return value


def reset_matrix_to_entered_value(gui_module: Any, gui: Any) -> None:
    """Reset all off-diagonal matrix cells to the textbox value and apply/save."""

    from . import gui_multi_zone as multi_zone

    value = _parse_reset_voltage(gui_module, gui)
    if value is None:
        return

    vars_map = getattr(gui, "voltage_zone_matrix_vars", None)
    if not vars_map:
        vars_map = multi_zone._ensure_vars(gui_module, gui)

    for zone_a in multi_zone.ZONE_LABELS:
        for zone_b in multi_zone.ZONE_LABELS:
            text = "0" if zone_a == zone_b else f"{value:g}"
            vars_map[(zone_a, zone_b)].set(text)

    try:
        gui.voltage_galvanic_zone_voltage.set(value)
    except Exception:
        pass

    multi_zone._apply_matrix(gui_module, gui)
    _ensure_reset_var(gui_module, gui).set(f"{value:g}")
    if hasattr(gui, "_append_log"):
        gui._append_log(f"Voltage Guessing: reset all zone-pair matrix voltages to {value:g} V.")
