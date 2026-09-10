"""High-contrast styling for Show zones buttons.

The zone-visualization action can be placed in the purple app header.  A normal
Primary.TButton may blend into that app-bar background on some Tk themes, so this
module applies explicit high-contrast button styles after the buttons are built.
"""

from __future__ import annotations

import builtins
import sys
from typing import Any


ZONE_HEADER_BUTTON_STYLE = "ZoneHeader.TButton"
ZONE_VIEWER_BUTTON_STYLE = "ZoneViewer.TButton"

_GUI_PATCHED_ATTR = "_zone_button_visibility_gui_patch_installed_v1"
_VIEWER_PATCHED_ATTR = "_zone_button_visibility_viewer_patch_installed_v1"
_ORIGINAL_GUI_INIT_ATTR = "_zone_button_visibility_original_gui_init"
_ORIGINAL_VIEWER_INIT_ATTR = "_zone_button_visibility_original_viewer_init"
_IMPORT_HOOK_ATTR = "_odb_zone_button_visibility_import_hook"
_PATCHING_GUI = False
_PATCHING_VIEWER = False


def install_zone_button_visibility_support() -> None:
    """Install visible Show-zones button styles for main GUI and viewer."""

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
                _apply_main_show_zones_style(gui_module, self)

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


def _apply_main_show_zones_style(gui_module: Any, gui: Any) -> None:
    ttk = getattr(gui_module, "ttk", None)
    if ttk is None:
        return
    _configure_button_styles(ttk, getattr(gui, "master", None), getattr(gui_module, "MATERIAL_COLORS", {}) or {})
    button = getattr(gui, "zone_visualization_button", None)
    if button is None:
        button = _find_button(gui, ttk, "Show zones")
    if button is None:
        return
    try:
        button.configure(style=ZONE_HEADER_BUTTON_STYLE)
    except Exception:
        pass


def _apply_viewer_show_zones_style(viewer_module: Any, viewer: Any) -> None:
    ttk = getattr(viewer_module, "ttk", None)
    if ttk is None:
        return
    _configure_button_styles(ttk, viewer, {})
    button = _find_button(viewer, ttk, "Show zones")
    if button is None:
        return
    try:
        button.configure(style=ZONE_VIEWER_BUTTON_STYLE)
    except Exception:
        pass


def _configure_button_styles(ttk: Any, master: Any, colors: dict[str, str]) -> None:
    try:
        style = ttk.Style(master)
    except Exception:
        try:
            style = ttk.Style()
        except Exception:
            return

    primary = colors.get("primary_dark", colors.get("primary", "#4F378B"))
    primary_container = colors.get("primary_container", "#EADDFF")
    outline = colors.get("on_primary", "#FFFFFF")
    disabled_bg = colors.get("outline_variant", "#E7E0EC")
    disabled_fg = colors.get("muted", "#49454F")

    # Main header: visible on the purple app bar.
    style.configure(
        ZONE_HEADER_BUTTON_STYLE,
        background="#FFFFFF",
        foreground=primary,
        padding=(16, 9),
        borderwidth=2,
        relief="raised",
        font=("Segoe UI", 10, "bold"),
        bordercolor=outline,
        lightcolor=outline,
        darkcolor=outline,
    )
    style.map(
        ZONE_HEADER_BUTTON_STYLE,
        background=[
            ("active", primary_container),
            ("pressed", primary_container),
            ("disabled", disabled_bg),
        ],
        foreground=[("disabled", disabled_fg)],
    )

    # Viewer toolbar: use a bright zone-color accent so it is distinguishable
    # from normal viewer actions.
    style.configure(
        ZONE_VIEWER_BUTTON_STYLE,
        background="#FFD740",
        foreground="#111318",
        padding=(14, 8),
        borderwidth=2,
        relief="raised",
        font=("Segoe UI", 9, "bold"),
        bordercolor="#FFFFFF",
        lightcolor="#FFFFFF",
        darkcolor="#5F5100",
    )
    style.map(
        ZONE_VIEWER_BUTTON_STYLE,
        background=[
            ("active", "#FFE082"),
            ("pressed", "#FFC400"),
            ("disabled", disabled_bg),
        ],
        foreground=[("disabled", disabled_fg)],
    )


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
