"""Mask duplicate cells in the symmetric Voltage Guessing -> Zones matrix."""

from __future__ import annotations

import builtins
import sys
from typing import Any


_PATCHED_ATTR = "_zone_matrix_duplicate_mask_installed_v2"
_ORIGINAL_BUILD_ATTR = "_zone_matrix_duplicate_mask_original_build_tab"
_ORIGINAL_INIT_ATTR = "_zone_matrix_duplicate_mask_original_init"
_IMPORT_HOOK_ATTR = "_odb_zone_matrix_duplicate_mask_import_hook"
_MASK_APPLIED_ATTR = "_zone_matrix_duplicate_mask_applied_v2"
MASK_TEXT = "—"


def install_zone_matrix_duplicate_mask_support() -> None:
    """Install duplicate-cell masking for the 10x10 zone matrix."""

    from . import gui_multi_zone as multi_zone

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
