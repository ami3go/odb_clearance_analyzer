"""Main report-tab layout integration for the Tk GUI."""

from __future__ import annotations

import builtins
import sys
from typing import Any

_PATCHED_ATTR = "_report_tab_layout_patch_installed_v2"
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
    "Log",
    "Feature attributes",
    "Debug zero",
)
_TOP_LEVEL_DEBUG_TABS = (
    "Log",
    "Feature attributes",
    "Debug zero/overlap",
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
    """Reorder report tabs and build live debug subtabs.

    Do not try to move already-created Tk notebook panes into a nested notebook:
    those panes belong to the original notebook and can render empty when
    re-parented.  Instead, create fresh Log / Feature attributes / Debug zero
    views inside the nested Debug notebook and repoint the GUI's live widget
    references to them.  The update/fill methods then write to the same kind of
    widgets as before, only inside the new Debug parent tab.
    """

    if getattr(gui, "_report_tab_layout_applied", False):
        return

    notebook = getattr(gui, "notebook", None)
    if notebook is None:
        return

    old_log = getattr(gui, "log", None)
    old_feature_tree = getattr(gui, "feature_attr_tree", None)
    old_debug_tree = getattr(gui, "debug_tree", None)

    debug_notebook = _ensure_debug_notebook(gui_module, gui, notebook)
    _rebuild_debug_subtabs(gui_module, gui, debug_notebook, old_log, old_feature_tree, old_debug_tree)
    _forget_top_level_debug_tabs(notebook)
    _order_main_tabs(notebook)

    summary_pane = _find_tab_by_text(notebook, "Summary")
    if summary_pane is not None:
        try:
            notebook.select(summary_pane)
        except Exception:
            pass

    gui._report_tab_layout_applied = True


def _ensure_debug_notebook(gui_module: Any, gui: Any, notebook: Any) -> Any:
    debug_parent = getattr(gui, "debug_parent_tab", None)
    existing_debug = _find_tab_by_text(notebook, "Debug")
    if debug_parent is None and existing_debug is not None:
        try:
            debug_parent = notebook.nametowidget(existing_debug)
        except Exception:
            debug_parent = None

    ttk = gui_module.ttk
    if debug_parent is None:
        debug_parent = ttk.Frame(notebook, padding=8, style="Card.TFrame")
        notebook.add(debug_parent, text="Debug")

    debug_notebook = getattr(gui, "debug_notebook", None)
    if debug_notebook is not None:
        return debug_notebook

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


def _rebuild_debug_subtabs(
    gui_module: Any,
    gui: Any,
    debug_notebook: Any,
    old_log: Any,
    old_feature_tree: Any,
    old_debug_tree: Any,
) -> None:
    _clear_notebook(debug_notebook)
    ttk = gui_module.ttk
    both = getattr(gui_module, "BOTH", "both")

    log_tab = ttk.Frame(debug_notebook, padding=8, style="Card.TFrame")
    feature_tab = ttk.Frame(debug_notebook, padding=8, style="Card.TFrame")
    debug_tab = ttk.Frame(debug_notebook, padding=8, style="Card.TFrame")

    debug_notebook.add(log_tab, text="Log")
    debug_notebook.add(feature_tab, text="Feature attributes")
    debug_notebook.add(debug_tab, text="Debug zero")

    new_log = gui._create_log_tree(log_tab)
    _copy_tree_rows(old_log, new_log)
    gui.log = new_log

    new_feature_tree = gui._create_feature_attr_tree(feature_tab)
    _copy_tree_rows(old_feature_tree, new_feature_tree)
    gui.feature_attr_tree = new_feature_tree

    new_debug_tree = gui._create_debug_tree(debug_tab)
    _copy_tree_rows(old_debug_tree, new_debug_tree)
    gui.debug_tree = new_debug_tree

    for frame in (log_tab, feature_tab, debug_tab):
        try:
            frame.pack_propagate(True)
        except Exception:
            pass
    try:
        debug_notebook.pack(fill=both, expand=True)
    except Exception:
        pass


def _clear_notebook(notebook: Any) -> None:
    for pane in list(notebook.tabs()):
        try:
            widget = notebook.nametowidget(pane)
        except Exception:
            widget = None
        try:
            notebook.forget(pane)
        except Exception:
            pass
        if widget is not None:
            try:
                widget.destroy()
            except Exception:
                pass


def _copy_tree_rows(source: Any, target: Any) -> None:
    if source is None or target is None or source is target:
        return
    try:
        children = list(source.get_children(""))
    except Exception:
        return
    for item in children:
        try:
            options = source.item(item)
            kwargs: dict[str, Any] = {
                "text": options.get("text", ""),
                "values": options.get("values", ()),
                "tags": options.get("tags", ()),
            }
            iid = str(item)
            if not target.exists(iid):
                kwargs["iid"] = iid
            target.insert("", "end", **kwargs)
        except Exception:
            try:
                target.insert("", "end", values=source.item(item, "values"))
            except Exception:
                pass


def _forget_top_level_debug_tabs(notebook: Any) -> None:
    for label in _TOP_LEVEL_DEBUG_TABS:
        pane = _find_tab_by_text(notebook, label)
        if pane is None:
            continue
        try:
            notebook.forget(pane)
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
