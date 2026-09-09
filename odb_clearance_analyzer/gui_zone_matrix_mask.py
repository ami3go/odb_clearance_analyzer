"""Mask duplicate cells in the symmetric Voltage Guessing -> Zones matrix."""

from __future__ import annotations

import builtins
import sys
from typing import Any


_PATCHED_ATTR = "_zone_matrix_duplicate_mask_installed_v3"
_ORIGINAL_BUILD_ATTR = "_zone_matrix_duplicate_mask_original_build_tab"
_ORIGINAL_INIT_ATTR = "_zone_matrix_duplicate_mask_original_init"
_ORIGINAL_SETTINGS_FROM_GUI_ATTR = "_zone_matrix_duplicate_mask_original_settings_from_gui"
_IMPORT_HOOK_ATTR = "_odb_zone_matrix_duplicate_mask_import_hook"
_MASK_APPLIED_ATTR = "_zone_matrix_duplicate_mask_applied_v3"
MASK_TEXT = "—"


def install_zone_matrix_duplicate_mask_support() -> None:
    """Install duplicate-cell masking for the 10x10 zone matrix."""

    from . import gui_multi_zone as multi_zone

    _patch_matrix_settings_source(multi_zone)

    if not getattr(multi_zone, _PATCHED_ATTR, False):
        original_build = getattr(multi_zone, "_build_tab", None)
        if callable(original_build):
            setattr(multi_zone, _ORIGINAL_BUILD_ATTR, original_build)

            def build_with_duplicate_mask(gui_module: Any, gui: Any, parent: Any) -> None:
                original_build(gui_module, gui, parent)
                mask_zone_matrix_duplicate_fields(gui_module, gui)

            multi_zone._build_tab = build_with_duplicate_mask
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


def _patch_matrix_settings_source(multi_zone: Any) -> None:
    """Make the visible lower triangle the source of truth for saved/report settings.

    The multi-zone table initially used the upper triangle as the editable half.
    After the UI was changed to mask the top/upper triangle, the extraction code
    must prefer the lower-triangle variables; otherwise a user edit in the only
    visible editable cell could be overwritten by the hidden mirrored value before
    reports are generated.
    """

    if hasattr(multi_zone, _ORIGINAL_SETTINGS_FROM_GUI_ATTR):
        return

    original_settings_from_gui = getattr(multi_zone, "_settings_from_gui", None)
    if not callable(original_settings_from_gui):
        return

    setattr(multi_zone, _ORIGINAL_SETTINGS_FROM_GUI_ATTR, original_settings_from_gui)

    def lower_triangle_settings_from_gui(gui: Any) -> dict[str, object]:
        labels = tuple(getattr(multi_zone, "ZONE_LABELS", ()))
        matrix_key = getattr(multi_zone, "ZONE_MATRIX_KEY", "zone_to_zone_voltage_matrix")
        vars_map = getattr(gui, "voltage_zone_matrix_vars", None)

        # Snapshot editable lower-triangle values before calling the original
        # settings builder.  The original builder may still mirror the old upper
        # triangle into the lower triangle, so reading after it would be too late.
        lower_values: dict[tuple[str, str], object] = {}
        if vars_map and labels:
            for row_index, zone_a in enumerate(labels):
                for col_index, zone_b in enumerate(labels):
                    if row_index <= col_index:
                        continue
                    var = vars_map.get((zone_a, zone_b))
                    if var is None:
                        continue
                    try:
                        lower_values[(zone_a, zone_b)] = var.get()
                    except Exception:
                        pass

        settings = dict(original_settings_from_gui(gui))
        if not vars_map or not labels or not lower_values:
            return settings

        try:
            fallback = multi_zone._legacy_voltage(gui)
        except Exception:
            fallback = getattr(multi_zone, "DEFAULT_ZONE_VOLTAGE", 1000.0)

        matrix = settings.get(matrix_key)
        if not isinstance(matrix, dict):
            matrix = multi_zone.normalize_matrix(settings, fallback)
        else:
            matrix = multi_zone.normalize_matrix({matrix_key: matrix, **settings}, fallback)

        for (zone_a, zone_b), raw_value in lower_values.items():
            old_value = matrix.get(zone_a, {}).get(zone_b, fallback)
            value = multi_zone.valid_voltage(raw_value, old_value)
            matrix[zone_a][zone_b] = value
            matrix[zone_b][zone_a] = value
            try:
                vars_map[(zone_a, zone_b)].set(f"{value:g}")
                vars_map[(zone_b, zone_a)].set(f"{value:g}")
            except Exception:
                pass

        for zone in labels:
            matrix[zone][zone] = 0.0

        zone12 = matrix["Zone 1"]["Zone 2"]
        settings[matrix_key] = matrix
        settings["galvanic_zone_voltage_v"] = zone12
        settings["zone_to_zone_voltage_v"] = zone12
        return settings

    multi_zone._settings_from_gui = lower_triangle_settings_from_gui


def _patch_gui_init(gui_module: Any) -> None:
    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None or getattr(cls, _PATCHED_ATTR, False):
        return

    if not hasattr(cls, _ORIGINAL_INIT_ATTR):
        setattr(cls, _ORIGINAL_INIT_ATTR, cls.__init__)

        def init(self: Any, *args: Any, **kwargs: Any):
            getattr(cls, _ORIGINAL_INIT_ATTR)(self, *args, **kwargs)
            mask_zone_matrix_duplicate_fields(gui_module, self)

        cls.__init__ = init

    setattr(cls, _PATCHED_ATTR, True)


def mask_zone_matrix_duplicate_fields(gui_module: Any, gui: Any) -> None:
    """Disable and visually mask upper-triangle duplicate matrix entries.

    The zone matrix is symmetric.  The editable source of truth is the lower
    triangle, where row index is greater than column index.  The upper/top
    triangle duplicates the same Zone A <-> Zone B pairs, so those fields are
    shown as disabled placeholders.  The underlying matrix variables are not
    removed; resolver/export code still sees a complete 10x10 matrix.
    """

    if getattr(gui, _MASK_APPLIED_ATTR, False):
        return

    table = getattr(gui, "voltage_zone_matrix_table", None)
    if table is None:
        return

    try:
        ttk = gui_module.ttk
        string_var = gui_module.StringVar
    except Exception:
        return

    masked: dict[tuple[int, int], Any] = {}
    editable: dict[tuple[int, int], Any] = {}
    diagonal: dict[tuple[int, int], Any] = {}

    for child in list(table.winfo_children()):
        if not isinstance(child, ttk.Entry):
            continue
        try:
            info = child.grid_info()
            row = int(info.get("row", 0))
            col = int(info.get("column", 0))
        except Exception:
            continue
        if row <= 0 or col <= 0:
            continue

        if row == col:
            try:
                child.configure(state="disabled")
            except Exception:
                pass
            diagonal[(row, col)] = child
        elif row < col:
            mask_var = string_var(value=MASK_TEXT)
            try:
                child.configure(textvariable=mask_var, state="disabled", justify="center")
            except Exception:
                pass
            masked[(row, col)] = child
        else:
            try:
                child.configure(state="normal")
            except Exception:
                pass
            editable[(row, col)] = child

    if not masked:
        return

    gui.voltage_zone_matrix_masked_duplicate_entries = masked
    gui.voltage_zone_matrix_editable_entries = editable
    gui.voltage_zone_matrix_diagonal_entries = diagonal
    setattr(gui, _MASK_APPLIED_ATTR, True)

    try:
        note_parent = table.master
        note = ttk.Label(
            note_parent,
            text="Duplicate upper/top-triangle cells are masked; edit only the lower triangle. Diagonal cells stay 0 V.",
            style="Muted.TLabel",
            wraplength=1100,
        )
        note.pack(anchor="w", fill=getattr(gui_module, "X", "x"), pady=(6, 0))
        gui.voltage_zone_matrix_mask_note = note
    except Exception:
        pass
