"""Main report-tab layout integration for the Tk GUI."""

from __future__ import annotations

import builtins
import sys
from typing import Any

_PATCHED_ATTR = "_report_tab_layout_patch_installed_v1"
_ORIGINAL_INIT_ATTR = "_report_tab_layout_original_init"
_IMPORT_HOOK_ATTR = "_odb_report_tab_layout_import_hook"
_MAIN_FIRST_TABS = (
    "Summary",
    "Settings",
    "Voltage Guessing",
    "IEC 60664-1",
    "IPC-2221A",
)
_DEBUG_SUBTABS = (
    ("Log", "Log"),
    ("Feature attributes", "Feature attributes"),
    ("Debug zero/overlap", "Debug zero"),
)


def install_report_tab_layout_patch() -> None:
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
    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None or getattr(cls, _PATCHED_ATTR, False):
        return

    setattr(cls, _ORIGINAL_INIT_ATTR, cls.__init__)

    def patched_init(self: Any, *args: Any, **kwargs: Any):
        original_init = getattr(cls, _ORIGINAL_INIT_ATTR)
        original_init(self, *args, **kwargs)
        apply_report_tab_layout(gui_module, self)

    cls.__init__ = patched_init
    setattr(cls, _PATCHED_ATTR, True)


def apply_report_tab_layout(gui_module: Any, gui: Any) -> None:
    """Reorder report tabs and group debug-only panes under one final tab."""

    if getattr(gui, "_report_tab_layout_applied", False):
        return

    notebook = getattr(gui, "notebook", None)
    if notebook is None:
        return

    debug_notebook = _ensure_debug_notebook(gui_module, gui, notebook)
    _move_debug_panes(notebook, debug_notebook)
    _order_main_tabs(notebook)

    summary_pane = _find_tab_by_text(notebook, "Summary")
    if summary_pane is not None:
        try:
            notebook.select(summary_pane)
        except Exception:
            pass

    gui._report_tab_layout_applied = True


def _ensure_debug_notebook(gui_module: Any, gui: Any, notebook: Any) -> Any:
    debug_notebook = getattr(gui, "debug_notebook", None)
    if debug_notebook is not None:
        return debug_notebook

    debug_parent = None
    existing_debug = _find_tab_by_text(notebook, "Debug")
    if existing_debug is not None:
        try:
            debug_parent = notebook.nametowidget(existing_debug)
        except Exception:
            debug_parent = None

    ttk = gui_module.ttk
    if debug_parent is None:
        debug_parent = ttk.Frame(notebook, padding=8, style="Card.TFrame")
        notebook.add(debug_parent, text="Debug")

    for child in list(debug_parent.winfo_children()):
        if isinstance(child, ttk.Notebook):
            gui.debug_parent_tab = debug_parent
            gui.debug_notebook = child
            return child

    debug_notebook = ttk.Notebook(debug_parent)
    debug_notebook.pack(fill=getattr(gui_module, "BOTH", "both"), expand=True)
    gui.debug_parent_tab = debug_parent
    gui.debug_notebook = debug_notebook
    return debug_notebook


def _move_debug_panes(notebook: Any, debug_notebook: Any) -> None:
    existing_subtab_texts = set(_tab_texts(debug_notebook))
    for source_text, target_text in _DEBUG_SUBTABS:
        if target_text in existing_subtab_texts:
            continue
        pane = _find_tab_by_text(notebook, source_text)
        if pane is None:
            continue
        try:
            widget = notebook.nametowidget(pane)
        except Exception:
            continue
        try:
            notebook.forget(pane)
        except Exception:
            pass
        try:
            debug_notebook.add(widget, text=target_text)
            existing_subtab_texts.add(target_text)
        except Exception:
            # Fallback: restore the original tab instead of losing access.
            try:
                notebook.add(widget, text=source_text)
            except Exception:
                pass


def _order_main_tabs(notebook: Any) -> None:
    index = 0
    for label in _MAIN_FIRST_TABS:
        pane = _find_tab_by_text(notebook, label)
        if pane is None:
            continue
        try:
            notebook.insert(index, pane)
            index += 1
        except Exception:
            pass

    debug_pane = _find_tab_by_text(notebook, "Debug")
    if debug_pane is not None:
        try:
            notebook.insert("end", debug_pane)
        except Exception:
            pass


def _find_tab_by_text(notebook: Any, text: str) -> str | None:
    try:
        for pane in notebook.tabs():
            if str(notebook.tab(pane, "text")) == text:
                return str(pane)
    except Exception:
        return None
    return None


def _tab_texts(notebook: Any) -> list[str]:
    try:
        return [str(notebook.tab(pane, "text")) for pane in notebook.tabs()]
    except Exception:
        return []
