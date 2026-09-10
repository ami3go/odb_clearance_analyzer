"""Shared header-button styling and app-header title cleanup.

Keep the visible app-bar controls consistent.  The detailed application version
belongs in the operating-system window title bar; the large in-app header uses a
clean product title without repeating the version number.
"""

from __future__ import annotations

import builtins
import sys
from typing import Any


HEADER_BUTTON_STYLE = "HeaderRun.TButton"
VIEWER_BUTTON_STYLE = "TButton"
HEADER_BUTTON_TEXTS = {
    "Run analysis",
    "Stop",
    "Open output",
    "Geometry viewer",
    "Show zones",
}
APP_HEADER_TITLE = "ODB++ Clearance Analyzer"

_GUI_PATCHED_ATTR = "_zone_button_visibility_gui_patch_installed_v2"
_VIEWER_PATCHED_ATTR = "_zone_button_visibility_viewer_patch_installed_v2"
_ORIGINAL_GUI_INIT_ATTR = "_zone_button_visibility_original_gui_init"
_ORIGINAL_VIEWER_INIT_ATTR = "_zone_button_visibility_original_viewer_init"
_IMPORT_HOOK_ATTR = "_odb_zone_button_visibility_import_hook"
_PATCHING_GUI = False
_PATCHING_VIEWER = False


def install_zone_button_visibility_support() -> None:
    """Install shared header button style and viewer toolbar normalization."""

    _patch_viewer_if_available()

    module = sys.modules.get("odb_clearance_analyzer.gui")
    if module is not None and getattr(module, "ClearanceGui", None) is not None:
        _patch_gui(module)
        return

    current_import = builtins.__import__
    if getattr(current_import, _IMPORT_HOOK_ATTR, False):
        return

    def hook(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[override]
        result = current_import(name, globals, locals, fromlist, level)
        module = sys.modules.get("odb_clearance_analyzer.gui")
        if module is not None and getattr(module, "ClearanceGui", None) is not None:
            _patch_gui(module)
            if builtins.__import__ is hook:
                builtins.__import__ = current_import
        _patch_viewer_if_available()
        return result

    setattr(hook, _IMPORT_HOOK_ATTR, True)
    builtins.__import__ = hook


def _patch_gui(gui_module: Any) -> None:
    global _PATCHING_GUI

    if _PATCHING_GUI:
        return
    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None or getattr(cls, _GUI_PATCHED_ATTR, False):
        return

    _PATCHING_GUI = True
    try:
        if not hasattr(cls, _ORIGINAL_GUI_INIT_ATTR):
            setattr(cls, _ORIGINAL_GUI_INIT_ATTR, cls.__init__)

            def init(self: Any, *args: Any, **kwargs: Any) -> None:
                getattr(cls, _ORIGINAL_GUI_INIT_ATTR)(self, *args, **kwargs)
                _apply_main_header_style_and_title(gui_module, self)

            cls.__init__ = init

        setattr(cls, _GUI_PATCHED_ATTR, True)
    finally:
        _PATCHING_GUI = False


def _patch_viewer_if_available() -> None:
    global _PATCHING_VIEWER

    if _PATCHING_VIEWER:
        return
    module = sys.modules.get("odb_clearance_analyzer.geometry_viewer")
    if module is None:
        return
    cls = getattr(module, "GeometryViewer", None)
    if cls is None or getattr(cls, _VIEWER_PATCHED_ATTR, False):
        return

    _PATCHING_VIEWER = True
    try:
        if not hasattr(cls, _ORIGINAL_VIEWER_INIT_ATTR):
            setattr(cls, _ORIGINAL_VIEWER_INIT_ATTR, cls.__init__)

            def init(self: Any, *args: Any, **kwargs: Any) -> None:
                getattr(cls, _ORIGINAL_VIEWER_INIT_ATTR)(self, *args, **kwargs)
                _apply_viewer_show_zones_style(module, self)

            cls.__init__ = init

        setattr(cls, _VIEWER_PATCHED_ATTR, True)
    finally:
        _PATCHING_VIEWER = False


def _apply_main_header_style_and_title(gui_module: Any, gui: Any) -> None:
    ttk = getattr(gui_module, "ttk", None)
    if ttk is None:
        return
    _configure_header_button_style(ttk, getattr(gui, "master", None), getattr(gui_module, "MATERIAL_COLORS", {}) or {})
    _remove_version_from_header_title(gui, ttk)
    _style_main_header_buttons(gui, ttk)


def _apply_viewer_show_zones_style(viewer_module: Any, viewer: Any) -> None:
    """Make the viewer Show-zones action look like the other viewer buttons."""

    ttk = getattr(viewer_module, "ttk", None)
    if ttk is None:
        return
    button = _find_button(viewer, ttk, "Show zones")
    if button is None:
        return
    try:
        button.configure(style=VIEWER_BUTTON_STYLE)
    except Exception:
        pass


def _configure_header_button_style(ttk: Any, master: Any, colors: dict[str, str]) -> None:
    try:
        style = ttk.Style(master)
    except Exception:
        try:
            style = ttk.Style()
        except Exception:
            return

    background = colors.get("surface", "#FFFFFF")
    foreground = colors.get("primary_dark", colors.get("primary", "#4F378B"))
    active_background = colors.get("primary_container", "#EADDFF")
    disabled_background = colors.get("outline_variant", "#E7E0EC")
    disabled_foreground = colors.get("muted", "#49454F")
    border = colors.get("on_primary", "#FFFFFF")

    style.configure(
        HEADER_BUTTON_STYLE,
        background=background,
        foreground=foreground,
        padding=(18, 9),
        borderwidth=1,
        relief="raised",
        font=("Segoe UI", 10, "bold"),
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
    )
    style.map(
        HEADER_BUTTON_STYLE,
        background=[
            ("active", active_background),
            ("pressed", active_background),
            ("disabled", disabled_background),
        ],
        foreground=[("disabled", disabled_foreground)],
    )


def _remove_version_from_header_title(gui: Any, ttk: Any) -> None:
    for widget in _walk(gui):
        if not isinstance(widget, ttk.Label):
            continue
        try:
            text = str(widget.cget("text") or "")
            label_style = str(widget.cget("style") or "")
        except Exception:
            continue
        if label_style == "AppBarTitle.TLabel" and text.startswith(APP_HEADER_TITLE):
            try:
                widget.configure(text=APP_HEADER_TITLE)
            except Exception:
                pass


def _style_main_header_buttons(gui: Any, ttk: Any) -> None:
    parent = getattr(gui, "_header_control_row", None)
    if parent is not None:
        widgets = list(getattr(parent, "winfo_children", lambda: [])())
    else:
        widgets = list(_walk(gui))

    for widget in widgets:
        if not isinstance(widget, ttk.Button):
            continue
        try:
            text = str(widget.cget("text") or "")
        except Exception:
            text = ""
        if text in HEADER_BUTTON_TEXTS:
            try:
                widget.configure(style=HEADER_BUTTON_STYLE)
            except Exception:
                pass


def _find_button(root: Any, ttk: Any, text: str) -> Any | None:
    for widget in _walk(root):
        if isinstance(widget, ttk.Button):
            try:
                if str(widget.cget("text")) == text:
                    return widget
            except Exception:
                pass
    return None


def _walk(widget: Any):
    try:
        children = list(widget.winfo_children())
    except Exception:
        children = []
    for child in children:
        yield child
        yield from _walk(child)
