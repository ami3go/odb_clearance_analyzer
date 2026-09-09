"""Galvanic-zone visualization for the Geometry Viewer.

Adds a zone-colored full-board view without replacing the existing geometry
inspection workflow.  The normal viewer remains pair-focused; the new
``Show zones`` action switches it into a board/layer overview where every net is
colored from its voltage-assignment galvanic zone.
"""

from __future__ import annotations

import builtins
import sys
from typing import Any, Mapping


ZONE_COLORS: dict[str, str] = {
    "Zone 1": "#FF5252",   # red
    "Zone 2": "#40C4FF",   # light blue
    "Zone 3": "#69F0AE",   # green
    "Zone 4": "#FFD740",   # yellow
    "Zone 5": "#B388FF",   # violet
    "Zone 6": "#FFAB40",   # orange
    "Zone 7": "#FF4081",   # pink
    "Zone 8": "#18FFFF",   # cyan
    "Zone 9": "#C6FF00",   # lime
    "Zone 10": "#8C9EFF",  # indigo
}
UNASSIGNED_ZONE_COLOR = "#9E9E9E"
UNASSIGNED_ZONE_LABEL = "Unassigned"

_GEOMETRY_PATCHED_ATTR = "_zone_visualization_geometry_patch_installed_v2"
_GUI_PATCHED_ATTR = "_zone_visualization_gui_patch_installed_v2"
_ORIGINAL_GEOMETRY_INIT_ATTR = "_zone_visualization_original_geometry_init"
_ORIGINAL_SELECTED_ATTR = "_zone_visualization_original_selected_geometries"
_ORIGINAL_STYLE_ATTR = "_zone_visualization_original_style_for_role"
_ORIGINAL_REDRAW_ATTR = "_zone_visualization_original_redraw"
_ORIGINAL_GUI_INIT_ATTR = "_zone_visualization_original_gui_init"
_IMPORT_HOOK_ATTR = "_odb_zone_visualization_import_hook"
_MAIN_BUTTON_ATTR = "_zone_visualization_main_button_added"
_VIEWER_BUTTON_ATTR = "_zone_visualization_viewer_button_added"

_GEOMETRY_PATCHING = False
_GUI_PATCHING = False


def install_zone_visualization_support() -> None:
    """Patch GeometryViewer and add Show zones launch controls."""

    # GeometryViewer is safe to patch before gui.py imports it.  ClearanceGui is
    # patched later by the import hook, but only after the class exists.
    _patch_geometry_viewer()

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
        # Do not patch gui.py while it is only partially imported.  Patching a
        # partial module is what previously re-entered while importing
        # geometry_viewer and produced an infinite hook loop on Windows.
        if module is not None and getattr(module, "ClearanceGui", None) is not None:
            _patch_gui(module)
            if builtins.__import__ is hook:
                builtins.__import__ = current_import
        return result

    setattr(hook, _IMPORT_HOOK_ATTR, True)
    builtins.__import__ = hook


def _zone_labels() -> tuple[str, ...]:
    try:
        from .gui_multi_zone import ZONE_LABELS

        return tuple(ZONE_LABELS)
    except Exception:
        return tuple(f"Zone {idx}" for idx in range(1, 11))


def _normalize_zone(value: object) -> str:
    try:
        from .gui_multi_zone import normalize_zone

        return normalize_zone(value)
    except Exception:
        text = str(value or "").strip()
        return text if text in _zone_labels() else ""


def _assignment_map(assignments: Any) -> dict[str, str]:
    """Return ``net -> normalized zone`` from a store, mapping or iterable."""

    if assignments is None:
        return {}
    raw = getattr(assignments, "assignments", assignments)
    result: dict[str, str] = {}

    if isinstance(raw, Mapping):
        items = raw.items()
    else:
        try:
            items = ((getattr(item, "net_name", ""), item) for item in raw)
        except Exception:
            return {}

    for key, assignment in items:
        net = str(getattr(assignment, "net_name", key) or key or "").strip()
        if not net:
            continue
        zone = _normalize_zone(getattr(assignment, "galvanic_zone", ""))
        result[net] = zone
    return result


def _patch_geometry_viewer() -> None:
    global _GEOMETRY_PATCHING

    if _GEOMETRY_PATCHING:
        return
    module = sys.modules.get("odb_clearance_analyzer.geometry_viewer")
    if module is not None:
        viewer_module = module
    else:
        _GEOMETRY_PATCHING = True
        try:
            from . import geometry_viewer as viewer_module
        finally:
            _GEOMETRY_PATCHING = False

    cls = getattr(viewer_module, "GeometryViewer", None)
    if cls is None or getattr(cls, _GEOMETRY_PATCHED_ATTR, False):
        return

    if not hasattr(cls, _ORIGINAL_GEOMETRY_INIT_ATTR):
        setattr(cls, _ORIGINAL_GEOMETRY_INIT_ATTR, cls.__init__)

        def init(self: Any, *args: Any, **kwargs: Any) -> None:
            getattr(cls, _ORIGINAL_GEOMETRY_INIT_ATTR)(self, *args, **kwargs)
            _init_viewer_zone_state(self)
            _load_zone_assignments_from_master(self)
            _add_viewer_show_zones_button(viewer_module, self)

        cls.__init__ = init

    if not hasattr(cls, "set_zone_assignments"):
        cls.set_zone_assignments = set_zone_assignments
    if not hasattr(cls, "show_zones"):
        cls.show_zones = show_zones
    if not hasattr(cls, "disable_zone_view"):
        cls.disable_zone_view = disable_zone_view
    if not hasattr(cls, "_zone_for_net"):
        cls._zone_for_net = _zone_for_net
    if not hasattr(cls, "_style_for_zone"):
        cls._style_for_zone = _style_for_zone
    if not hasattr(cls, "_draw_zone_legend"):
        cls._draw_zone_legend = _draw_zone_legend
    if not hasattr(cls, "_zone_counts_for_current_layer"):
        cls._zone_counts_for_current_layer = _zone_counts_for_current_layer

    if not hasattr(cls, _ORIGINAL_SELECTED_ATTR):
        setattr(cls, _ORIGINAL_SELECTED_ATTR, cls.selected_geometries)

        def selected_geometries(self: Any):
            if bool(getattr(self, "zone_visualization_enabled", False)):
                layer = self.layer_var.get()
                by_net = self.result.net_geometry_by_layer.get(layer, {})
                selected = []
                for net, geom in sorted(by_net.items()):
                    if geom is None or getattr(geom, "is_empty", True):
                        continue
                    zone = self._zone_for_net(net)
                    role = f"zone:{zone}" if zone else "zone:unassigned"
                    selected.append((net, geom, role))
                return selected
            return getattr(cls, _ORIGINAL_SELECTED_ATTR)(self)

        cls.selected_geometries = selected_geometries

    if not hasattr(cls, _ORIGINAL_STYLE_ATTR):
        setattr(cls, _ORIGINAL_STYLE_ATTR, cls._style_for_role)

        def style_for_role(self: Any, role: str):
            text = str(role or "")
            if text.startswith("zone:"):
                zone = text.split(":", 1)[1]
                return self._style_for_zone(zone)
            return getattr(cls, _ORIGINAL_STYLE_ATTR)(self, role)

        cls._style_for_role = style_for_role

    if not hasattr(cls, _ORIGINAL_REDRAW_ATTR):
        setattr(cls, _ORIGINAL_REDRAW_ATTR, cls.redraw)

        def redraw(self: Any) -> None:
            getattr(cls, _ORIGINAL_REDRAW_ATTR)(self)
            if bool(getattr(self, "zone_visualization_enabled", False)):
                self._draw_zone_legend()
                counts = self._zone_counts_for_current_layer()
                assigned_count = sum(counts.get(label, 0) for label in _zone_labels())
                total = sum(counts.values())
                layer = self.layer_var.get()
                self.status_var.set(
                    f"Zone view: layer {layer}; nets drawn {total}; assigned {assigned_count}; "
                    f"unassigned {counts.get(UNASSIGNED_ZONE_LABEL, 0)}; zoom {self.scale:.1f} px/mm"
                )

        cls.redraw = redraw

    setattr(cls, _GEOMETRY_PATCHED_ATTR, True)


def _init_viewer_zone_state(viewer: Any) -> None:
    if not hasattr(viewer, "zone_visualization_enabled"):
        viewer.zone_visualization_enabled = False
    if not hasattr(viewer, "zone_assignment_map"):
        viewer.zone_assignment_map = {}


def _load_zone_assignments_from_master(viewer: Any) -> None:
    provider = getattr(getattr(viewer, "master", None), "_odb_zone_assignment_provider", None)
    if callable(provider):
        try:
            viewer.set_zone_assignments(provider())
        except Exception:
            pass


def set_zone_assignments(self: Any, assignments: Any) -> None:
    """Attach voltage-assignment zones to a viewer instance."""

    _init_viewer_zone_state(self)
    self.zone_assignment_map = _assignment_map(assignments)


def show_zones(self: Any) -> None:
    """Switch the viewer to full-board/layer galvanic-zone coloring."""

    _init_viewer_zone_state(self)
    _load_zone_assignments_from_master(self)
    self.zone_visualization_enabled = True
    try:
        self.net_a_var.set("")
        self.net_b_var.set("")
        self.show_other_nets_var.set(True)
        self.show_component_pads_var.set(False)
        self.show_points_var.set(False)
    except Exception:
        pass
    self.fit_to_layer()


def disable_zone_view(self: Any) -> None:
    """Return the viewer to normal role/layer coloring."""

    self.zone_visualization_enabled = False
    try:
        self.show_points_var.set(True)
    except Exception:
        pass
    self.redraw()


def _zone_for_net(self: Any, net: str) -> str:
    return _normalize_zone(getattr(self, "zone_assignment_map", {}).get(str(net), ""))


def _style_for_zone(self: Any, zone: str) -> tuple[str, str]:
    if zone == "unassigned" or not zone:
        base = UNASSIGNED_ZONE_COLOR
    else:
        base = ZONE_COLORS.get(_normalize_zone(zone), UNASSIGNED_ZONE_COLOR)
    try:
        fill = self._mix_hex(self.COLORS["background"], base, 0.58)
    except Exception:
        fill = base
    return fill, base


def _zone_counts_for_current_layer(self: Any) -> dict[str, int]:
    layer = self.layer_var.get()
    by_net = getattr(self.result, "net_geometry_by_layer", {}).get(layer, {})
    counts: dict[str, int] = {label: 0 for label in _zone_labels()}
    counts[UNASSIGNED_ZONE_LABEL] = 0
    for net in by_net.keys():
        zone = self._zone_for_net(net)
        counts[zone or UNASSIGNED_ZONE_LABEL] = counts.get(zone or UNASSIGNED_ZONE_LABEL, 0) + 1
    return counts


def _draw_zone_legend(self: Any) -> None:
    counts = self._zone_counts_for_current_layer()
    rows = [(label, ZONE_COLORS[label], counts.get(label, 0)) for label in _zone_labels() if counts.get(label, 0)]
    if counts.get(UNASSIGNED_ZONE_LABEL, 0):
        rows.append((UNASSIGNED_ZONE_LABEL, UNASSIGNED_ZONE_COLOR, counts[UNASSIGNED_ZONE_LABEL]))
    if not rows:
        rows = [(label, ZONE_COLORS[label], 0) for label in _zone_labels()[:2]]
        rows.append((UNASSIGNED_ZONE_LABEL, UNASSIGNED_ZONE_COLOR, 0))

    x0, y0 = 12, 12
    swatch = 14
    line_h = 20
    width = 230
    height = 30 + line_h * len(rows)
    try:
        self.canvas.create_rectangle(
            x0,
            y0,
            x0 + width,
            y0 + height,
            fill="#111318",
            outline="#FFFFFF",
            width=1,
            stipple="gray25",
        )
        self.canvas.create_text(
            x0 + 10,
            y0 + 8,
            text="Galvanic zones",
            anchor="nw",
            fill="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
        )
        for index, (label, color, count) in enumerate(rows):
            y = y0 + 30 + index * line_h
            self.canvas.create_rectangle(
                x0 + 10,
                y,
                x0 + 10 + swatch,
                y + swatch,
                fill=color,
                outline="#FFFFFF",
                width=1,
            )
            self.canvas.create_text(
                x0 + 32,
                y - 1,
                text=f"{label}: {count} net(s)",
                anchor="nw",
                fill="#FFFFFF",
                font=("Segoe UI", 8),
            )
    except Exception:
        pass


def _add_viewer_show_zones_button(viewer_module: Any, viewer: Any) -> None:
    if getattr(viewer, _VIEWER_BUTTON_ATTR, False):
        return
    ttk = getattr(viewer_module, "ttk", None)
    if ttk is None:
        return
    parent = _find_button_parent(viewer, ttk, "Show all nets")
    if parent is None:
        return
    try:
        ttk.Button(parent, text="Show zones", style="Primary.TButton", command=viewer.show_zones).pack(
            side=getattr(viewer_module, "LEFT", "left"),
            padx=(0, 12),
        )
        setattr(viewer, _VIEWER_BUTTON_ATTR, True)
    except Exception:
        pass


def _patch_gui(gui_module: Any) -> None:
    global _GUI_PATCHING

    if _GUI_PATCHING:
        return
    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None or getattr(cls, _GUI_PATCHED_ATTR, False):
        return

    _GUI_PATCHING = True
    try:
        _patch_geometry_viewer()

        if not hasattr(cls, "_open_zone_geometry_viewer"):
            cls._open_zone_geometry_viewer = _open_zone_geometry_viewer

        if not hasattr(cls, _ORIGINAL_GUI_INIT_ATTR):
            setattr(cls, _ORIGINAL_GUI_INIT_ATTR, cls.__init__)

            def init(self: Any, *args: Any, **kwargs: Any) -> None:
                getattr(cls, _ORIGINAL_GUI_INIT_ATTR)(self, *args, **kwargs)
                _install_zone_assignment_provider(self)
                _add_main_show_zones_button(gui_module, self)

            cls.__init__ = init

        setattr(cls, _GUI_PATCHED_ATTR, True)
    finally:
        _GUI_PATCHING = False


def _install_zone_assignment_provider(gui: Any) -> None:
    try:
        gui.master._odb_zone_assignment_provider = lambda gui=gui: getattr(  # type: ignore[attr-defined]
            getattr(gui, "voltage_store", None), "assignments", {}
        )
    except Exception:
        pass


def _open_zone_geometry_viewer(self: Any):
    """Open Geometry Viewer directly in full-board zone-color mode."""

    if getattr(self, "last_result", None) is None:
        try:
            from tkinter import messagebox

            messagebox.showinfo("Geometry viewer", "Run analysis first, then show zones.")
        except Exception:
            pass
        return None

    try:
        self._load_voltage_store_if_present()
        self._sync_voltage_settings_to_store()
    except Exception:
        pass

    viewer_class = getattr(sys.modules.get("odb_clearance_analyzer.gui"), "GeometryViewer", None)
    if viewer_class is None:
        from .geometry_viewer import GeometryViewer as viewer_class

    viewer = viewer_class(
        self.master,
        self.last_result,
        dark_theme=bool(self.dark_theme.get()),
        on_show_voltage_assignment=self._jump_to_voltage_assignment_from_viewer,
    )
    viewer.set_zone_assignments(getattr(getattr(self, "voltage_store", None), "assignments", {}))
    viewer.show_zones()
    if hasattr(self, "_append_log"):
        assigned = len(getattr(viewer, "zone_assignment_map", {}) or {})
        self._append_log(f"Geometry Viewer: opened zone visualization with {assigned} voltage assignment(s).")
    return viewer


def _add_main_show_zones_button(gui_module: Any, gui: Any) -> None:
    if getattr(gui, _MAIN_BUTTON_ATTR, False):
        return
    ttk = getattr(gui_module, "ttk", None)
    if ttk is None:
        return

    parent = getattr(gui, "_header_control_row", None)
    if parent is None:
        parent = _find_button_parent(gui, ttk, "Geometry viewer")
    if parent is None:
        return
    if _parent_has_button_text(parent, ttk, "Show zones"):
        setattr(gui, _MAIN_BUTTON_ATTR, True)
        return

    try:
        button = ttk.Button(parent, text="Show zones", style="Primary.TButton", command=gui._open_zone_geometry_viewer)
        button.pack(side=getattr(gui_module, "LEFT", "left"), padx=(6, 0))
        gui.zone_visualization_button = button
        setattr(gui, _MAIN_BUTTON_ATTR, True)
    except Exception:
        pass


def _find_button_parent(root: Any, ttk: Any, text: str) -> Any | None:
    for widget in _walk(root):
        if isinstance(widget, ttk.Button):
            try:
                if str(widget.cget("text")) == text:
                    return getattr(widget, "master", None)
            except Exception:
                pass
    return None


def _parent_has_button_text(parent: Any, ttk: Any, text: str) -> bool:
    for widget in getattr(parent, "winfo_children", lambda: [])():
        if isinstance(widget, ttk.Button):
            try:
                if str(widget.cget("text")) == text:
                    return True
            except Exception:
                pass
    return False


def _walk(widget: Any):
    try:
        children = list(widget.winfo_children())
    except Exception:
        children = []
    for child in children:
        yield child
        yield from _walk(child)
