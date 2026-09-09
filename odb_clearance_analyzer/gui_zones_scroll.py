"""Scrollable container for the Voltage Guessing -> Zones tab."""

from __future__ import annotations

import tkinter as tk
from typing import Any


_PATCHED_ATTR = "_zones_tab_scroll_wrapper_installed_v1"
_ORIGINAL_BUILD_ATTR = "_zones_tab_scroll_original_build_tab"


def install_zones_tab_scroll_support() -> None:
    """Wrap the multi-zone tab builder with a vertical scroll container."""

    from . import gui_multi_zone as multi_zone

    if getattr(multi_zone, _PATCHED_ATTR, False):
        return

    original_build = getattr(multi_zone, "_build_tab", None)
    if not callable(original_build):
        return

    setattr(multi_zone, _ORIGINAL_BUILD_ATTR, original_build)

    def build_scrollable_zones_tab(gui_module: Any, gui: Any, parent: Any) -> None:
        _build_scroll_container(gui_module, gui, parent, original_build)

    multi_zone._build_tab = build_scrollable_zones_tab
    setattr(multi_zone, _PATCHED_ATTR, True)


def _build_scroll_container(gui_module: Any, gui: Any, parent: Any, original_build: Any) -> None:
    """Create a vertical-scrollable body, then build the normal Zones UI inside it."""

    for child in list(parent.winfo_children()):
        try:
            child.destroy()
        except Exception:
            pass

    ttk = gui_module.ttk
    both = getattr(gui_module, "BOTH", "both")
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)

    canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    body = ttk.Frame(canvas, style="Card.TFrame")

    window_id = canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    def _update_scroll_region(_event: object | None = None) -> None:
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _sync_body_width(event: Any) -> None:
        try:
            canvas.itemconfigure(window_id, width=event.width)
        except Exception:
            pass

    body.bind("<Configure>", _update_scroll_region)
    canvas.bind("<Configure>", _sync_body_width)

    def _wheel_units(event: Any) -> int:
        delta = getattr(event, "delta", 0)
        if delta:
            return -1 if delta > 0 else 1
        number = getattr(event, "num", 0)
        if number == 4:
            return -1
        if number == 5:
            return 1
        return 0

    def _on_mousewheel(event: Any) -> str | None:
        units = _wheel_units(event)
        if units:
            try:
                canvas.yview_scroll(units, "units")
            except Exception:
                pass
            return "break"
        return None

    def _bind_mousewheel(_event: object | None = None) -> None:
        # Windows/macOS use <MouseWheel>; many Linux Tk builds use Button-4/5.
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

    def _unbind_mousewheel(_event: object | None = None) -> None:
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    canvas.bind("<Enter>", _bind_mousewheel)
    body.bind("<Enter>", _bind_mousewheel)
    canvas.bind("<Leave>", _unbind_mousewheel)

    gui.voltage_zones_scroll_canvas = canvas
    gui.voltage_zones_vertical_scrollbar = scrollbar
    gui.voltage_zones_scroll_body = body

    original_build(gui_module, gui, body)
    _update_scroll_region()
    try:
        body.pack_propagate(True)
        canvas.pack_propagate(True)
    except Exception:
        pass
    try:
        canvas.configure(height=max(360, parent.winfo_height()))
    except Exception:
        pass

    # Keep a visible right-side scrollbar even when the initial window is tall;
    # the 10x10 table still needs scrolling on normal laptop displays.
    try:
        parent.pack_propagate(True)
    except Exception:
        pass
