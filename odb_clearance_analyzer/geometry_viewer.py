"""Interactive Tkinter geometry viewer for reconstructed ODB++ copper."""

from __future__ import annotations

import math
import re
from importlib import resources
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, BooleanVar, Canvas, PhotoImage, StringVar, Toplevel, messagebox
from tkinter import ttk

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from .models import AnalysisResult, MeasurementRecord, GeometryDebugRecord
from .theme import MATERIAL_COLORS, install_material_theme




def _load_packaged_photoimage(name: str, master=None) -> PhotoImage | None:
    """Load a PNG image shipped inside the package."""

    try:
        ref = resources.files("odb_clearance_analyzer").joinpath("assets", name)
        with resources.as_file(ref) as asset_path:
            return PhotoImage(master=master, file=str(asset_path))
    except Exception:
        return None


class GeometryViewer(Toplevel):
    """Separate zoomable window for inspecting reconstructed copper geometry.

    The viewer intentionally displays the same Shapely geometries used by the
    clearance engine.  It is therefore useful for distinguishing real copper
    intersections from parser/reconstruction artifacts.
    """

    COLORS = {
        "net_a_fill": "#FFD8A8",
        "net_a_outline": "#B65F00",
        "net_b_fill": "#B8E6FF",
        "net_b_outline": "#006493",
        "other_fill": "#D8D2DD",
        "other_outline": "#79747E",
        "point_a": "#BA1A1A",
        "point_b": "#005DB7",
        "background": "#111318",
        "grid": "#2B2D33",
        "text": "#F4EFF4",
        "cutout": "#FFB4AB",
        "via_outline": "#FFE082",
        "via_fill": "",
        "pad_fill": "#C8E6C9",
        "pad_outline": "#00C853",
        "pad_selected_outline": "#FFFFFF",
        "pad_text": "#B9F6CA",
        "pcb_outline": "#FFFFFF",
        "pcb_outline_shadow": "#000000",
        "component_outline": "#FF80AB",
        "component_outline_shadow": "#000000",
        "component_text": "#FFFFFF",
        "component_text_bg": "#4A0B2E",
        "blocker_dot": "#FF2D95",
        "blocker_dot_outline": "#FFFFFF",
    }

    # Typical bright PCB-viewer layer colors tuned for the dark canvas background.
    # Top and bottom are deliberately red/blue; inner layers rotate through
    # green, gold, orange, violet, cyan and magenta so they remain distinguishable.
    LAYER_COLOR_PALETTE = [
        "#FF4D4D",  # top / layer 1 - red
        "#00E676",  # inner 1 - green
        "#FFD740",  # inner 2 - gold/yellow
        "#FF9100",  # inner 3 - orange
        "#B388FF",  # inner 4 - violet
        "#00E5FF",  # inner 5 - cyan
        "#FF5DC8",  # inner 6 - magenta
        "#AEEA00",  # inner 7 - lime
    ]
    TOP_LAYER_COLOR = "#FF4D4D"
    BOTTOM_LAYER_COLOR = "#4DA3FF"

    def __init__(
        self,
        master,
        result: AnalysisResult,
        layer: str | None = None,
        net_a: str | None = None,
        net_b: str | None = None,
        point_a: tuple[float, float] | None = None,
        point_b: tuple[float, float] | None = None,
        dark_theme: bool = False,
    ) -> None:
        super().__init__(master)
        self.dark_theme = dark_theme
        install_material_theme(self, dark=dark_theme)
        self.configure(bg=MATERIAL_COLORS["app_bg"])
        self.result = result
        self._window_icon = _load_packaged_photoimage("app_icon.png", master=self)
        self._header_icon = _load_packaged_photoimage("app_icon_small.png", master=self)
        self.title("ODB++ Geometry Viewer")
        self.geometry("1200x820")
        self.minsize(800, 500)
        if self._window_icon is not None:
            try:
                self.iconphoto(True, self._window_icon)
            except Exception:
                pass

        available_layers = list(result.net_geometry_by_layer.keys())
        initial_layer = layer if layer in available_layers else (available_layers[0] if available_layers else "")

        self.layer_var = StringVar(value=initial_layer)
        self.layer_color_var = StringVar(value="")
        self.net_a_var = StringVar(value=net_a or "")
        self.net_b_var = StringVar(value=net_b or "")
        self.net_a_filter_var = StringVar(value="")
        self.net_b_filter_var = StringVar(value="")
        self.show_other_nets_var = BooleanVar(value=False)
        self.fast_mode_var = BooleanVar(value=True)
        self.show_component_pads_var = BooleanVar(value=True)
        self.show_components_var = BooleanVar(value=False)
        self.show_vias_var = BooleanVar(value=True)
        self.show_pcb_outline_var = BooleanVar(value=True)
        self.show_points_var = BooleanVar(value=True)
        self.status_var = StringVar(value="Ready")
        self.spacing_var = StringVar(value="Minimum spacing: --")

        self.point_a = point_a
        self.point_b = point_b
        self.scale = 1.0
        self.offset_x = 20.0
        self.offset_y = 20.0
        self.world_bounds: tuple[float, float, float, float] | None = None
        self._drag_start: tuple[int, int] | None = None
        self._drag_button: int | None = None
        self._drag_moved = False
        self._last_mouse_world: tuple[float, float] | None = None
        self._next_click_role = "a" if not self.net_a_var.get().strip() else "b"
        self._last_clicked_net: str | None = None

        self._build_ui(available_layers)
        self._bind_events()
        self.after(100, self.fit_to_selection)

    def _build_ui(self, available_layers: list[str]) -> None:
        appbar = ttk.Frame(self, style="AppBar.TFrame", padding=(18, 14, 18, 12))
        appbar.pack(fill=X)
        header_row = ttk.Frame(appbar, style="AppBar.TFrame")
        header_row.pack(fill=X)
        if self._header_icon is not None:
            ttk.Label(header_row, image=self._header_icon, style="AppBarSubtitle.TLabel").pack(side=LEFT, padx=(0, 12))
        title_block = ttk.Frame(header_row, style="AppBar.TFrame")
        title_block.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(title_block, text="Geometry Viewer", style="AppBarTitle.TLabel").pack(anchor="w")
        ttk.Label(
            title_block,
            text="Click copper to select Net A and Net B. Zoom with mouse wheel, drag to pan.",
            style="AppBarSubtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        top = ttk.Frame(self, style="Card.TFrame", padding=(14, 12, 14, 12))
        top.pack(fill=X, padx=12, pady=(12, 8))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)
        top.columnconfigure(5, weight=1)
        top.columnconfigure(7, weight=1)

        ttk.Label(top, text="Layer").grid(row=0, column=0, sticky="w", padx=(0, 5), pady=(0, 8))
        self.layer_combo = ttk.Combobox(top, textvariable=self.layer_var, values=available_layers, width=18, state="readonly")
        self.layer_combo.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(0, 8))
        self.layer_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_layer_changed())

        self.layer_color_swatch = ttk.Label(top, textvariable=self.layer_color_var, style="Status.TLabel")
        self.layer_color_swatch.grid(row=0, column=2, sticky="w", padx=(0, 12), pady=(0, 8))

        button_row = ttk.Frame(top, style="Card.TFrame")
        button_row.grid(row=0, column=3, columnspan=5, sticky="e", pady=(0, 8))
        ttk.Button(button_row, text="Redraw", command=self.redraw).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="Fit", style="Primary.TButton", command=self.fit_to_selection).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="Zoom min 2/3", command=self._zoom_to_minimum_clearance_2_3).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="Swap", command=self._swap_nets).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="Show all nets", command=self._show_all_nets).pack(side=LEFT, padx=(0, 12))
        ttk.Checkbutton(button_row, text="Fast mode", variable=self.fast_mode_var, command=self.redraw).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(button_row, text="Other nets", variable=self.show_other_nets_var, command=self.redraw).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(button_row, text="Component pads", variable=self.show_component_pads_var, command=self.redraw).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(button_row, text="Show components", variable=self.show_components_var, command=self._on_components_toggle).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(button_row, text="Vias", variable=self.show_vias_var, command=self.redraw).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(button_row, text="PCB outline", variable=self.show_pcb_outline_var, command=self.redraw).pack(side=LEFT, padx=(0, 10))
        ttk.Checkbutton(button_row, text="Points", variable=self.show_points_var, command=self.redraw).pack(side=LEFT)

        ttk.Label(top, text="Net A filter").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=3)
        self.net_a_filter_entry = ttk.Entry(top, textvariable=self.net_a_filter_var, width=22)
        self.net_a_filter_entry.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=3)
        ttk.Label(top, text="Net A").grid(row=1, column=2, sticky="w", padx=(0, 5), pady=3)
        self.net_a_combo = ttk.Combobox(top, textvariable=self.net_a_var, values=[], width=28)
        self.net_a_combo.grid(row=1, column=3, sticky="ew", padx=(0, 18), pady=3)
        self.net_a_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_net_combo_selected())

        ttk.Label(top, text="Net B filter").grid(row=1, column=4, sticky="w", padx=(0, 5), pady=3)
        self.net_b_filter_entry = ttk.Entry(top, textvariable=self.net_b_filter_var, width=22)
        self.net_b_filter_entry.grid(row=1, column=5, sticky="ew", padx=(0, 12), pady=3)
        ttk.Label(top, text="Net B").grid(row=1, column=6, sticky="w", padx=(0, 5), pady=3)
        self.net_b_combo = ttk.Combobox(top, textvariable=self.net_b_var, values=[], width=28)
        self.net_b_combo.grid(row=1, column=7, sticky="ew", pady=3)
        self.net_b_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_net_combo_selected())

        self.net_a_filter_var.trace_add("write", lambda *_args: self._refresh_net_combo_values())
        self.net_b_filter_var.trace_add("write", lambda *_args: self._refresh_net_combo_values())
        self._refresh_net_combo_values()

        help_frame = ttk.Frame(self, style="Toolbar.TFrame", padding=(14, 8, 14, 8))
        help_frame.pack(fill=X, padx=12, pady=(0, 8))
        ttk.Label(
            help_frame,
            text="First click = Net A, second different net = Net B. Fast mode draws non-selected copper as simplified outlines; selected nets remain exact.",
            style="ViewerHelp.TLabel",
        ).pack(side=LEFT)
        ttk.Label(help_frame, textvariable=self.spacing_var, style="ViewerHelp.TLabel").pack(side=RIGHT)

        body = ttk.Frame(self, style="Card.TFrame", padding=0)
        body.pack(fill=BOTH, expand=True, padx=12, pady=(0, 8))

        self.canvas = Canvas(body, background=self.COLORS["background"], highlightthickness=0)
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        status = ttk.Label(self, textvariable=self.status_var, style="Status.TLabel")
        status.pack(fill=X, padx=12, pady=(0, 12))

    def _bind_events(self) -> None:
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)  # Windows/macOS
        self.canvas.bind("<Button-4>", lambda event: self._zoom_at(event.x, event.y, 1.15))  # Linux up
        self.canvas.bind("<Button-5>", lambda event: self._zoom_at(event.x, event.y, 1 / 1.15))  # Linux down
        for button in (1, 2, 3):
            self.canvas.bind(f"<ButtonPress-{button}>", self._start_pan)
            self.canvas.bind(f"<B{button}-Motion>", self._pan)
            self.canvas.bind(f"<ButtonRelease-{button}>", self._end_pan)
        self.canvas.bind("<Motion>", self._show_mouse_position)

    def _nets_for_current_layer(self) -> list[str]:
        layer = self.layer_var.get()
        return sorted(self.result.net_geometry_by_layer.get(layer, {}).keys())

    def _filter_nets(self, filter_text: str) -> list[str]:
        """Return current-layer nets matching a typed substring filter.

        Matching is case-insensitive and token based: typing ``cell 8`` matches
        names that contain both ``cell`` and ``8`` in any order.  Separators
        such as comma, semicolon, and spaces are treated as token boundaries.
        The active Net A / Net B value is not cleared when it is outside the
        filtered drop-down list; this preserves cross-layer selections.
        """

        nets = self._nets_for_current_layer()
        text = (filter_text or "").strip().lower()
        if not text:
            return nets
        normalized = text.replace(",", " ").replace(";", " ")
        tokens = [part for part in normalized.split() if part]
        if not tokens:
            return nets
        return [net for net in nets if all(token in net.lower() for token in tokens)]

    def _refresh_net_combo_values(self) -> None:
        """Apply Net A / Net B filter fields to the combobox drop-down lists."""

        if not hasattr(self, "net_a_combo") or not hasattr(self, "net_b_combo"):
            return
        self.net_a_combo.configure(values=self._filter_nets(self.net_a_filter_var.get()))
        self.net_b_combo.configure(values=self._filter_nets(self.net_b_filter_var.get()))

    def _selected_nets_missing_on_current_layer(self) -> list[str]:
        nets = set(self._nets_for_current_layer())
        selected = [self.net_a_var.get().strip(), self.net_b_var.get().strip()]
        return [net for net in selected if net and net not in nets]

    def _on_layer_changed(self) -> None:
        """Refresh layer-local net choices without dropping the active selection.

        Net A / Net B selections are intentionally global viewer state.  A user
        may pick a net on one layer and then switch to another copper layer to
        inspect whether the same net pair exists there.  Earlier versions cleared
        selections when the net was absent on the new layer, which made click
        selection feel inactive after changing layers.
        """
        self._refresh_net_combo_values()
        # Keep typed/click-selected net names even when the selected layer does
        # not contain them.  selected_geometries() will draw them automatically
        # whenever they exist on the active layer.
        self.point_a = None
        self.point_b = None
        self._next_click_role = "b" if self.net_a_var.get().strip() and not self.net_b_var.get().strip() else "a"
        self.fit_to_selection()

    def _swap_nets(self) -> None:
        a, b = self.net_a_var.get(), self.net_b_var.get()
        self.net_a_var.set(b)
        self.net_b_var.set(a)
        self.point_a, self.point_b = self.point_b, self.point_a
        self._next_click_role = "b" if self.net_a_var.get().strip() else "a"
        self.redraw()

    def _on_net_combo_selected(self) -> None:
        """Handle manual Net A / Net B selection from the filtered lists."""

        # Manual pair selection should calculate and display the current-layer
        # minimum spacing, not keep stale points from a previous critical row.
        self.point_a = None
        self.point_b = None
        self._next_click_role = "b" if self.net_a_var.get().strip() and not self.net_b_var.get().strip() else "a"
        self.fit_to_selection()

    def _show_all_nets(self) -> None:
        """Enable full-layer overview while keeping the selected pair highlighted."""

        self.show_other_nets_var.set(True)
        self.fit_to_layer()

    def fit_to_layer(self) -> None:
        """Fit the viewer to all copper geometries on the active layer."""

        layer = self.layer_var.get()
        geometries = list(self.result.net_geometry_by_layer.get(layer, {}).values())
        outline = self._pcb_outline_geometry()
        if outline is not None:
            geometries.append(outline)
        if self.show_components_var.get():
            geometries.extend([record.geometry for record in self._component_records_for_current_layer()])
        bounds = self._combined_bounds(geometries)
        if bounds is None:
            self.status_var.set(f"No geometry available on layer {layer}.")
            self.redraw()
            return
        minx, miny, maxx, maxy = bounds
        pad = max((maxx - minx), (maxy - miny), 1.0) * 0.04
        self.world_bounds = (minx - pad, miny - pad, maxx + pad, maxy + pad)
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        w = max(1e-9, self.world_bounds[2] - self.world_bounds[0])
        h = max(1e-9, self.world_bounds[3] - self.world_bounds[1])
        self.scale = max(1e-9, min(canvas_w / w, canvas_h / h))
        self.offset_x = (canvas_w - w * self.scale) / 2.0 - self.world_bounds[0] * self.scale
        self.offset_y = (canvas_h - h * self.scale) / 2.0 + self.world_bounds[3] * self.scale
        self.redraw()

    def selected_geometries(self) -> list[tuple[str, object, str]]:
        layer = self.layer_var.get()
        by_net = self.result.net_geometry_by_layer.get(layer, {})
        selected: list[tuple[str, object, str]] = []
        net_a = self.net_a_var.get().strip()
        net_b = self.net_b_var.get().strip()
        if self.show_other_nets_var.get():
            for net, geom in by_net.items():
                if net not in {net_a, net_b}:
                    selected.append((net, geom, "other"))
        if net_a and net_a in by_net:
            selected.append((net_a, by_net[net_a], "a"))
        if net_b and net_b in by_net and net_b != net_a:
            selected.append((net_b, by_net[net_b], "b"))
        if not selected and by_net:
            # No net selected: draw a light overview of the first few nets rather than an empty window.
            for net, geom in list(sorted(by_net.items()))[:80]:
                selected.append((net, geom, "other"))
        return selected

    def _on_components_toggle(self) -> None:
        """Redraw and refit when the component overlay is toggled on."""

        if self.show_components_var.get():
            self.fit_to_selection()
        else:
            self.redraw()

    def fit_to_selection(self) -> None:
        selected = self.selected_geometries()
        fit_geometries = [geom for _net, geom, _role in selected]
        outline = self._pcb_outline_geometry()
        if outline is not None:
            fit_geometries.append(outline)
        if self.show_components_var.get():
            fit_geometries.extend([record.geometry for record in self._component_records_for_current_layer()])
        bounds = self._combined_bounds(fit_geometries)
        if bounds is None:
            self.status_var.set("No geometry available for selected layer/nets.")
            self.redraw()
            return
        minx, miny, maxx, maxy = bounds
        # Include reported measurement points when available.
        for point in (self.point_a, self.point_b):
            if point:
                x, y = point
                minx, miny, maxx, maxy = min(minx, x), min(miny, y), max(maxx, x), max(maxy, y)
        pad = max((maxx - minx), (maxy - miny), 1.0) * 0.08
        self.world_bounds = (minx - pad, miny - pad, maxx + pad, maxy + pad)
        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        w = max(1e-9, self.world_bounds[2] - self.world_bounds[0])
        h = max(1e-9, self.world_bounds[3] - self.world_bounds[1])
        self.scale = max(1e-9, min(canvas_w / w, canvas_h / h))
        self.offset_x = (canvas_w - w * self.scale) / 2.0 - self.world_bounds[0] * self.scale
        self.offset_y = (canvas_h - h * self.scale) / 2.0 + self.world_bounds[3] * self.scale
        self.redraw()

    def redraw(self) -> None:
        self.canvas.delete("all")
        self._update_layer_color_swatch()
        selected = self.selected_geometries()
        component_records = self._component_records_for_current_layer() if self.show_components_var.get() else []
        pcb_outline = self._pcb_outline_geometry() if self.show_pcb_outline_var.get() else None
        if not selected and not component_records and pcb_outline is None:
            self.status_var.set("No geometry to draw.")
            return
        self._draw_grid()
        outline_count = self._draw_pcb_outline() if pcb_outline is not None else 0
        count = 0
        fast_mode = bool(self.fast_mode_var.get())
        for net, geom, role in selected:
            fill, outline = self._style_for_role(role)
            if fast_mode and role == "other":
                count += self._draw_fast_geometry(geom, outline=outline, width=1)
            else:
                count += self._draw_geometry(geom, fill=fill, outline=outline, width=1 if role == "other" else 2)
        pad_count = 0
        if self.show_component_pads_var.get():
            pad_count = self._draw_component_pad_overlay()
        via_count = 0
        if self.show_vias_var.get():
            via_count = self._draw_via_overlay()
        component_count = 0
        if component_records:
            component_count = self._draw_component_outlines(component_records)
        self._draw_selected_pair_spacing()
        if self.show_points_var.get():
            self._draw_measurement_points()
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, self.canvas.winfo_width(), self.canvas.winfo_height()))
        layer = self.layer_var.get()
        next_role = "Net A" if self._next_click_role == "a" else "Net B"
        missing = self._selected_nets_missing_on_current_layer()
        missing_text = "" if not missing else "; not on this layer: " + ", ".join(missing)
        net_a_matches = len(self._filter_nets(self.net_a_filter_var.get()))
        net_b_matches = len(self._filter_nets(self.net_b_filter_var.get()))
        layer_color = self._layer_base_color(layer)
        mode_text = "FAST" if bool(self.fast_mode_var.get()) else "EXACT"
        self.status_var.set(
            f"Layer {layer} ({layer_color}); mode: {mode_text}; drawn objects: {count}; outline: {outline_count}; components: {component_count}; pads: {pad_count}; vias: {via_count}; zoom: {self.scale:.1f} px/mm; "
            f"Net A filter: {net_a_matches}; Net B filter: {net_b_matches}; next click: {next_role}{missing_text}; mouse: "
            + ("" if self._last_mouse_world is None else f"{self._last_mouse_world[0]:.4f}, {self._last_mouse_world[1]:.4f} mm")
        )

    def _pcb_outline_geometry(self):
        """Return parsed PCB outline geometry from ODB++ profile/mechanical layer."""

        job = getattr(self.result, "job", None)
        if job is None:
            return None
        geom = getattr(job, "pcb_outline_geometry", None)
        if geom is None or getattr(geom, "is_empty", True):
            return None
        return geom

    def _draw_pcb_outline(self) -> int:
        """Draw the PCB board outline/profile as a high-contrast overlay."""

        geom = self._pcb_outline_geometry()
        if geom is None:
            return 0
        return self._draw_outline_geometry(geom)

    def _draw_outline_geometry(self, geom) -> int:
        """Draw geometry boundary/exterior only, without filling board area."""

        if geom is None or getattr(geom, "is_empty", True):
            return 0
        geom_type = getattr(geom, "geom_type", "")
        if geom_type == "Polygon":
            count = self._draw_outline_line(geom.exterior)
            for interior in getattr(geom, "interiors", []):
                count += self._draw_outline_line(interior)
            return count
        if geom_type in {"MultiPolygon", "GeometryCollection"}:
            count = 0
            for sub in getattr(geom, "geoms", []):
                count += self._draw_outline_geometry(sub)
            return count
        if geom_type in {"LineString", "LinearRing"}:
            return self._draw_outline_line(geom)
        try:
            boundary = geom.boundary
        except Exception:
            return 0
        return self._draw_outline_geometry(boundary)

    def _draw_outline_line(self, line) -> int:
        coords = []
        try:
            for xy in line.coords:
                coords.extend(self.world_to_screen(float(xy[0]), float(xy[1])))
        except Exception:
            return 0
        if len(coords) < 4:
            return 0
        # Shadow first, then bright outline.  This remains visible on both dark
        # canvas and bright layer colors.
        self.canvas.create_line(*coords, fill=self.COLORS["pcb_outline_shadow"], width=4)
        self.canvas.create_line(*coords, fill=self.COLORS["pcb_outline"], width=2)
        return 1

    def _zoom_to_minimum_clearance_2_3(self) -> None:
        """Zoom to exact minimum-clearance location.

        The nearest-point clearance line is centered in the canvas and scaled so
        its screen length is approximately 2/3 of the available graphic window
        length.  Available window length is the smaller of current canvas width
        and height, so the full clearance line remains visible in either
        horizontal or vertical orientation.
        """

        pair = self._selected_pair_geometries()
        if pair is None:
            messagebox.showinfo("Zoom min 2/3", "Select Net A and Net B on the current layer first.")
            return

        net_a, net_b, geom_a, geom_b = pair
        try:
            distance = float(geom_a.distance(geom_b))
        except Exception as exc:
            messagebox.showerror("Zoom min 2/3", f"Could not calculate minimum clearance: {exc}")
            return

        self.update_idletasks()
        canvas_w = max(1, int(self.canvas.winfo_width()))
        canvas_h = max(1, int(self.canvas.winfo_height()))
        available_px = max(1.0, min(float(canvas_w), float(canvas_h)))

        if distance <= 1e-12:
            # Overlap/touching case: there is no non-zero clearance line to scale.
            # Center on the intersection representative point and make a small
            # local window visible.
            try:
                intersection = geom_a.intersection(geom_b)
                if intersection is not None and not getattr(intersection, "is_empty", True):
                    rp = intersection.representative_point()
                    center = (float(rp.x), float(rp.y))
                else:
                    pa, pb = nearest_points(geom_a, geom_b)
                    center = ((float(pa.x) + float(pb.x)) / 2.0, (float(pa.y) + float(pb.y)) / 2.0)
            except Exception:
                self.fit_to_selection()
                return
            target_world_span = 0.5  # mm visible at 2/3 window in zero-clearance view
            self.scale = max(1e-9, (available_px * (2.0 / 3.0)) / target_world_span)
            self.offset_x = canvas_w / 2.0 - center[0] * self.scale
            self.offset_y = canvas_h / 2.0 + center[1] * self.scale
            self.point_a = center
            self.point_b = center
            self.spacing_var.set(f"Minimum spacing: 0.000000 mm ({net_a} ↔ {net_b}); zoomed to overlap/touch")
            self.redraw()
            return

        try:
            pa, pb = nearest_points(geom_a, geom_b)
        except Exception as exc:
            messagebox.showerror("Zoom min 2/3", f"Could not resolve exact nearest points: {exc}")
            return

        point_a = (float(pa.x), float(pa.y))
        point_b = (float(pb.x), float(pb.y))
        midpoint = ((point_a[0] + point_b[0]) / 2.0, (point_a[1] + point_b[1]) / 2.0)

        target_line_px = available_px * (2.0 / 3.0)
        self.scale = max(1e-9, target_line_px / distance)
        self.offset_x = canvas_w / 2.0 - midpoint[0] * self.scale
        self.offset_y = canvas_h / 2.0 + midpoint[1] * self.scale

        # Store exact minimum points so the viewer remains focused on the same
        # measured location after redraws.
        self.point_a = point_a
        self.point_b = point_b
        self.show_points_var.set(True)
        self.spacing_var.set(
            f"Minimum spacing: {distance:.6f} mm ({net_a} ↔ {net_b}); line = 2/3 window"
        )
        self.redraw()

    def _selected_pair_geometries(self):
        """Return Net A / Net B geometries on the current layer, if both exist."""

        layer = self.layer_var.get()
        by_net = self.result.net_geometry_by_layer.get(layer, {})
        net_a = self.net_a_var.get().strip()
        net_b = self.net_b_var.get().strip()
        if not net_a or not net_b or net_a == net_b:
            return None
        geom_a = by_net.get(net_a)
        geom_b = by_net.get(net_b)
        if geom_a is None or geom_b is None:
            return None
        if getattr(geom_a, "is_empty", True) or getattr(geom_b, "is_empty", True):
            return None
        return net_a, net_b, geom_a, geom_b

    def _draw_selected_pair_spacing(self) -> None:
        """Calculate and draw the minimum spacing for selected Net A / Net B."""

        pair = self._selected_pair_geometries()
        if pair is None:
            self.spacing_var.set("Minimum spacing: --")
            return
        net_a, net_b, geom_a, geom_b = pair
        try:
            distance = float(geom_a.distance(geom_b))
        except Exception as exc:
            self.spacing_var.set(f"Minimum spacing: error: {exc}")
            return

        self.spacing_var.set(f"Minimum spacing: {distance:.6f} mm ({net_a} ↔ {net_b})")

        if distance <= 1e-9:
            # For an overlap/touching condition, a zero-length nearest line may
            # be invisible.  Draw the intersection geometry itself as a warning.
            try:
                intersection = geom_a.intersection(geom_b)
            except Exception:
                intersection = None
            if intersection is not None and not getattr(intersection, "is_empty", True):
                self._draw_geometry(intersection, fill="#FFB4AB", outline="#BA1A1A", width=3)
                try:
                    rp = intersection.representative_point()
                    self._draw_spacing_label((rp.x, rp.y), "0.000000 mm overlap/touch")
                except Exception:
                    pass
            return

        try:
            pa, pb = nearest_points(geom_a, geom_b)
        except Exception:
            return
        point_a = (float(pa.x), float(pa.y))
        point_b = (float(pb.x), float(pb.y))
        ax, ay = self.world_to_screen(*point_a)
        bx, by = self.world_to_screen(*point_b)
        self.canvas.create_line(ax, ay, bx, by, fill="#FFEB3B", width=3, dash=(6, 3))
        blocker_count = self._draw_blocker_dots_on_spacing_line(net_a, net_b, point_a, point_b)
        self._draw_marker(point_a, "#FFEB3B", "min A")
        self._draw_marker(point_b, "#FFEB3B", "min B")
        mid = ((point_a[0] + point_b[0]) / 2.0, (point_a[1] + point_b[1]) / 2.0)
        label = f"{distance:.6f} mm"
        if blocker_count:
            label += f" / {blocker_count} blocker dot(s)"
        self._draw_spacing_label(mid, label)

    def _draw_blocker_dots_on_spacing_line(
        self,
        net_a: str,
        net_b: str,
        point_a: tuple[float, float],
        point_b: tuple[float, float],
    ) -> int:
        """Mark other copper pieces intersecting the straight spacing line.

        This makes the Effective Net-to-Net concept visible: if other copper lies
        between the two selected copper elements on the straight-line path, the
        viewer places magenta dots where that copper is removed from the available
        air gap.
        """

        try:
            line = LineString([point_a, point_b])
        except Exception:
            return 0
        if line.is_empty or line.length <= 1e-12:
            return 0

        by_net = self.result.net_geometry_by_layer.get(self.layer_var.get(), {})
        blocker_points: list[tuple[str, tuple[float, float]]] = []
        for other_net, geom in by_net.items():
            if other_net in {net_a, net_b}:
                continue
            if geom is None or getattr(geom, "is_empty", True):
                continue
            try:
                if not geom.intersects(line) and geom.distance(line) > 0.002:
                    continue
                hit = geom.intersection(line)
                if hit is None or getattr(hit, "is_empty", True):
                    # Precision fallback: use nearest point on line.
                    if geom.distance(line) <= 0.002:
                        from shapely.ops import nearest_points as _nearest_points

                        _pg, pl = _nearest_points(geom, line)
                        hit = pl
                    else:
                        continue
            except Exception:
                continue

            for pt in self._representative_points_from_intersection(hit):
                if pt is None:
                    continue
                blocker_points.append((other_net, pt))
                if len(blocker_points) >= 40:
                    break
            if len(blocker_points) >= 40:
                break

        if not blocker_points:
            return 0

        # De-duplicate visually nearby points.
        unique: list[tuple[str, tuple[float, float]]] = []
        for net, pt in blocker_points:
            if all((pt[0] - old[1][0]) ** 2 + (pt[1] - old[1][1]) ** 2 > 0.000004 for old in unique):
                unique.append((net, pt))

        for idx, (net, pt) in enumerate(unique[:40]):
            self._draw_blocker_dot(pt, net if idx < 6 else "")
        return len(unique)

    def _representative_points_from_intersection(self, geom) -> list[tuple[float, float]]:
        """Return one or more display points for a line/copper intersection."""

        if geom is None or getattr(geom, "is_empty", True):
            return []
        geom_type = getattr(geom, "geom_type", "")
        try:
            if geom_type == "Point":
                return [(float(geom.x), float(geom.y))]
            if geom_type == "MultiPoint":
                return [(float(pt.x), float(pt.y)) for pt in geom.geoms]
            if geom_type in {"LineString", "LinearRing"}:
                p = geom.interpolate(0.5, normalized=True)
                return [(float(p.x), float(p.y))]
            if geom_type in {"MultiLineString", "GeometryCollection", "MultiPolygon"}:
                pts: list[tuple[float, float]] = []
                for sub in getattr(geom, "geoms", []):
                    pts.extend(self._representative_points_from_intersection(sub))
                return pts
            if geom_type == "Polygon":
                p = geom.representative_point()
                return [(float(p.x), float(p.y))]
        except Exception:
            return []
        try:
            p = geom.representative_point()
            return [(float(p.x), float(p.y))]
        except Exception:
            return []

    def _draw_blocker_dot(self, point: tuple[float, float], net_label: str = "") -> None:
        """Draw one magenta dot on the straight-line spacing path."""

        x, y = self.world_to_screen(*point)
        r = 6
        self.canvas.create_oval(
            x - r,
            y - r,
            x + r,
            y + r,
            fill=self.COLORS["blocker_dot"],
            outline=self.COLORS["blocker_dot_outline"],
            width=2,
        )
        self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#FFFFFF", outline="")
        if net_label:
            self.canvas.create_text(
                x + 9,
                y + 8,
                text=f"blocked by {net_label}",
                fill=self.COLORS["blocker_dot_outline"],
                anchor="w",
                font=("Segoe UI", 8, "bold"),
            )

    def _draw_spacing_label(self, point: tuple[float, float], text: str) -> None:
        x, y = self.world_to_screen(*point)
        # Small dark/bright label badge; works on the dark PCB canvas and still
        # remains visible when the app theme is light.
        padding_x = 7
        padding_y = 4
        label = self.canvas.create_text(x + 10, y - 12, text=text, fill="#111318", anchor="w", font=("Segoe UI", 10, "bold"))
        bbox = self.canvas.bbox(label)
        if bbox:
            rect = self.canvas.create_rectangle(
                bbox[0] - padding_x,
                bbox[1] - padding_y,
                bbox[2] + padding_x,
                bbox[3] + padding_y,
                fill="#FFEB3B",
                outline="#5F5100",
                width=1,
            )
            self.canvas.tag_raise(label, rect)

    def _component_records_for_current_layer(self):
        """Return component contour records relevant for the active layer."""

        job = getattr(self.result, "job", None)
        if job is None:
            return []
        records = list(getattr(job, "component_outlines", []) or [])
        if not records:
            return []
        side = self._side_for_layer(self.layer_var.get())
        if side in {"top", "bottom"}:
            return [record for record in records if getattr(record, "side", "") == side]
        return records

    def _side_for_layer(self, layer: str) -> str | None:
        """Infer top/bottom side from common copper layer names."""

        compact = re.sub(r"[^a-z0-9]+", "", (layer or "").lower())
        if compact in {"top", "fcu", "front", "frontcu", "topcu", "signal1", "sig1", "l1", "layer1"}:
            return "top"
        if compact in {"bottom", "bot", "bcu", "back", "backcu", "bottomcu"}:
            return "bottom"
        layers = list(getattr(self.result.job, "signal_layers", []) or []) if getattr(self.result, "job", None) else []
        if layers:
            if layer == layers[0]:
                return "top"
            if layer == layers[-1]:
                return "bottom"
        return None

    def _draw_component_outlines(self, records=None) -> int:
        """Draw only component contour plus reference designator at contour center."""

        if records is None:
            records = self._component_records_for_current_layer()
        count = 0
        for record in records:
            geom = getattr(record, "geometry", None)
            if geom is None or getattr(geom, "is_empty", True):
                continue
            count += self._draw_colored_outline_geometry(
                geom,
                color=self.COLORS["component_outline"],
                shadow=self.COLORS["component_outline_shadow"],
                width=2,
            )
            self._draw_component_refdes(record)
        return count

    def _draw_component_refdes(self, record) -> None:
        """Draw reference designator centered on component contour."""

        try:
            x = float(getattr(record, "center_x_mm"))
            y = float(getattr(record, "center_y_mm"))
        except Exception:
            try:
                c = record.geometry.centroid
                x, y = float(c.x), float(c.y)
            except Exception:
                return
        sx, sy = self.world_to_screen(x, y)
        text = str(getattr(record, "refdes", "")).strip()
        if not text:
            return

        # Use a compact badge so the reference is readable on copper and outline colors.
        label = self.canvas.create_text(
            sx,
            sy,
            text=text,
            fill=self.COLORS["component_text"],
            anchor="center",
            font=("Segoe UI", 8 if self.scale < 120 else 9, "bold"),
        )
        bbox = self.canvas.bbox(label)
        if bbox:
            pad_x, pad_y = 4, 2
            rect = self.canvas.create_rectangle(
                bbox[0] - pad_x,
                bbox[1] - pad_y,
                bbox[2] + pad_x,
                bbox[3] + pad_y,
                fill=self.COLORS["component_text_bg"],
                outline=self.COLORS["component_outline"],
                width=1,
            )
            self.canvas.tag_raise(label, rect)

    def _draw_colored_outline_geometry(self, geom, color: str, shadow: str | None = None, width: int = 2) -> int:
        """Draw a geometry outline using supplied colors."""

        if geom is None or getattr(geom, "is_empty", True):
            return 0
        geom_type = getattr(geom, "geom_type", "")
        if geom_type == "Polygon":
            count = self._draw_colored_outline_line(geom.exterior, color=color, shadow=shadow, width=width)
            for interior in getattr(geom, "interiors", []):
                count += self._draw_colored_outline_line(interior, color=color, shadow=shadow, width=width)
            return count
        if geom_type in {"MultiPolygon", "GeometryCollection"}:
            count = 0
            for sub in getattr(geom, "geoms", []):
                count += self._draw_colored_outline_geometry(sub, color=color, shadow=shadow, width=width)
            return count
        if geom_type in {"LineString", "LinearRing"}:
            return self._draw_colored_outline_line(geom, color=color, shadow=shadow, width=width)
        try:
            boundary = geom.boundary
        except Exception:
            return 0
        return self._draw_colored_outline_geometry(boundary, color=color, shadow=shadow, width=width)

    def _draw_colored_outline_line(self, line, color: str, shadow: str | None = None, width: int = 2) -> int:
        coords = []
        try:
            for xy in line.coords:
                coords.extend(self.world_to_screen(float(xy[0]), float(xy[1])))
        except Exception:
            return 0
        if len(coords) < 4:
            return 0
        if shadow:
            self.canvas.create_line(*coords, fill=shadow, width=max(width + 2, 3))
        self.canvas.create_line(*coords, fill=color, width=width)
        return 1

    def _draw_component_pad_overlay(self) -> int:
        """Draw original ODB++ positive pad features on top of merged net copper.

        The main viewer draws unioned per-net copper geometry because that is what
        the clearance engine measures.  That is correct analytically, but IC pads
        and component pads can visually disappear inside a merged net polygon or
        under a nearby route/pour.  This overlay renders the original ODB++ pad
        features one-by-one so component pads remain visible and selectable when
        inspecting the board.
        """

        layer = self.layer_var.get()
        job = getattr(self.result, "job", None)
        if job is None:
            return 0
        features = getattr(job, "features_by_layer", {}).get(layer, [])
        if not features:
            return 0

        net_a = self.net_a_var.get().strip()
        net_b = self.net_b_var.get().strip()
        selected_nets = {net for net in (net_a, net_b) if net}
        draw_all = self.show_other_nets_var.get() or not selected_nets
        count = 0
        for feature in features:
            if not self._is_drawable_component_pad(feature):
                continue
            geom = feature.geometry
            if geom is None or getattr(geom, "is_empty", True):
                continue
            net = getattr(job, "feature_net_map", {}).get((layer.lower(), feature.index), "$NONE$")
            if not draw_all and net not in selected_nets:
                continue
            if net == net_a:
                outline = self.COLORS["net_a_outline"]
                fill = self.COLORS["net_a_fill"]
                width = 3
            elif net == net_b:
                outline = self.COLORS["net_b_outline"]
                fill = self.COLORS["net_b_fill"]
                width = 3
            else:
                fill, outline = self._layer_style(layer, selected=False)
                width = 1
            count += self._draw_geometry(geom, fill=fill, outline=outline, width=width)
            self._draw_pad_center_marker(feature, net, outline)
        return count

    def _is_drawable_component_pad(self, feature) -> bool:
        """Return True for copper-layer pad features worth drawing in the pad overlay."""

        try:
            if str(feature.kind).upper() != "P":
                return False
            if str(feature.polarity).upper() != "P":
                return False
            if feature.geometry is None or getattr(feature.geometry, "is_empty", True):
                return False
        except Exception:
            return False
        return True

    def _draw_pad_center_marker(self, feature, net: str, outline: str) -> None:
        """Draw a small center tick for a pad at high enough zoom.

        The marker makes rectangular IC pads visible even when the pad outline is
        nearly hidden by the selected-net fill.  Labels are intentionally shown
        only at high zoom to avoid overwhelming the canvas on dense boards.
        """

        if self.scale < 80:
            return
        try:
            c = feature.geometry.centroid
            x, y = self.world_to_screen(float(c.x), float(c.y))
        except Exception:
            return
        r = 2.5
        self.canvas.create_line(x - r, y, x + r, y, fill=outline, width=1)
        self.canvas.create_line(x, y - r, x, y + r, fill=outline, width=1)
        if self.scale >= 220:
            label = net
            try:
                attr = feature.decoded_attributes_text
                if attr:
                    # Prefer concise reference-like text when the exporter stores
                    # it in .string; otherwise fall back to the net name.
                    for part in attr.split(","):
                        key, sep, value = part.strip().partition("=")
                        if sep and key.strip() in {".string", ".refdes", ".pin"} and value.strip():
                            label = value.strip()
                            break
            except Exception:
                pass
            self.canvas.create_text(x + 5, y - 5, text=label, fill=self.COLORS["pad_text"], anchor="w", font=("Segoe UI", 8))

    def _draw_via_overlay(self) -> int:
        """Draw plated-via pad geometry as a visible overlay on the active layer."""

        layer = self.layer_var.get()
        via_by_net = getattr(self.result, "via_geometry_by_layer", {}).get(layer, {})
        if not via_by_net:
            return 0
        net_a = self.net_a_var.get().strip()
        net_b = self.net_b_var.get().strip()
        selected_nets = {net for net in (net_a, net_b) if net}

        count = 0
        for net, geom in sorted(via_by_net.items()):
            if selected_nets and net not in selected_nets and not self.show_other_nets_var.get():
                continue
            if geom is None or getattr(geom, "is_empty", True):
                continue
            if net in selected_nets:
                outline = self.COLORS["via_outline"]
                fill = self.COLORS["via_fill"]
                width = 2
            else:
                fill, outline = self._layer_style(layer, selected=False)
                width = 1
            count += self._draw_geometry(geom, fill=fill, outline=outline, width=width)
        return count

    def _draw_grid(self) -> None:
        # Draw a modest grid only when zoomed enough to be useful.
        if self.world_bounds is None or self.scale < 10:
            return
        minx, miny, maxx, maxy = self._visible_world_bounds()
        step = self._nice_grid_step(80.0 / max(self.scale, 1e-9))
        start_x = math.floor(minx / step) * step
        start_y = math.floor(miny / step) * step
        x = start_x
        while x <= maxx:
            sx1, sy1 = self.world_to_screen(x, miny)
            sx2, sy2 = self.world_to_screen(x, maxy)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill=self.COLORS["grid"], width=1)
            x += step
        y = start_y
        while y <= maxy:
            sx1, sy1 = self.world_to_screen(minx, y)
            sx2, sy2 = self.world_to_screen(maxx, y)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill=self.COLORS["grid"], width=1)
            y += step

    def _draw_measurement_points(self) -> None:
        if self.point_a:
            self._draw_marker(self.point_a, self.COLORS["point_a"], "A")
        if self.point_b:
            self._draw_marker(self.point_b, self.COLORS["point_b"], "B")
        if self.point_a and self.point_b:
            ax, ay = self.world_to_screen(*self.point_a)
            bx, by = self.world_to_screen(*self.point_b)
            self.canvas.create_line(ax, ay, bx, by, fill="#F4EFF4", dash=(4, 3), width=1)

    def _draw_marker(self, point: tuple[float, float], color: str, label: str) -> None:
        x, y = self.world_to_screen(*point)
        r = 5
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="#F4EFF4", width=1)
        self.canvas.create_text(x + 9, y - 9, text=label, fill=self.COLORS["text"], anchor="w")

    def _style_for_role(self, role: str) -> tuple[str, str]:
        if role == "a":
            return self.COLORS["net_a_fill"], self.COLORS["net_a_outline"]
        if role == "b":
            return self.COLORS["net_b_fill"], self.COLORS["net_b_outline"]
        return self._layer_style(self.layer_var.get(), selected=False)

    def _update_layer_color_swatch(self) -> None:
        """Update the text/color swatch next to the layer selector."""

        if not hasattr(self, "layer_color_swatch"):
            return
        layer = self.layer_var.get()
        color = self._layer_base_color(layer)
        self.layer_color_var.set(f"Layer color {color}")
        try:
            self.layer_color_swatch.configure(foreground=color)
        except Exception:
            pass

    def _layer_style(self, layer: str, selected: bool = False) -> tuple[str, str]:
        """Return fill/outline for non-selected copper on a layer."""

        base = self._layer_base_color(layer)
        background = self.COLORS["background"]
        if selected:
            return self._mix_hex(base, "#FFFFFF", 0.20), base
        # Use a darkened fill plus bright outline.  This is readable on the dark
        # canvas without hiding measurement markers or pad outlines.
        return self._mix_hex(background, base, 0.34), base

    def _layer_base_color(self, layer: str) -> str:
        """Return a deterministic, high-contrast, typical PCB-viewer color."""

        name = (layer or "").strip()
        compact = re.sub(r"[^a-z0-9]+", "", name.lower())

        if compact in {"top", "fcu", "frontcu", "topcu", "signal1", "sig1", "l1", "layer1"}:
            return self.TOP_LAYER_COLOR
        if compact in {"bottom", "bot", "bcu", "backcu", "bottomcu"}:
            return self.BOTTOM_LAYER_COLOR

        signal_layers = list(getattr(self.result, "job", None).signal_layers) if getattr(self.result, "job", None) else []
        if signal_layers:
            try:
                index = signal_layers.index(name)
            except ValueError:
                index = -1
            if index == 0:
                return self.TOP_LAYER_COLOR
            if index == len(signal_layers) - 1 and len(signal_layers) > 1:
                return self.BOTTOM_LAYER_COLOR
            if index > 0:
                return self.LAYER_COLOR_PALETTE[index % len(self.LAYER_COLOR_PALETTE)]

        match = re.search(r"(?:inner|internal|in|signal|sig|layer|l)(\d+)", compact)
        if match:
            idx = max(0, int(match.group(1)) - 1)
            return self.LAYER_COLOR_PALETTE[idx % len(self.LAYER_COLOR_PALETTE)]

        # Stable fallback hash for unusual names.
        idx = sum(ord(ch) for ch in compact) % len(self.LAYER_COLOR_PALETTE)
        return self.LAYER_COLOR_PALETTE[idx]

    def _hex_to_rgb(self, color: str) -> tuple[int, int, int]:
        color = color.strip().lstrip("#")
        if len(color) == 3:
            color = "".join(ch * 2 for ch in color)
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)

    def _rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(v))) for v in rgb))

    def _mix_hex(self, color_a: str, color_b: str, amount_b: float) -> str:
        amount_b = max(0.0, min(1.0, float(amount_b)))
        amount_a = 1.0 - amount_b
        ra, ga, ba = self._hex_to_rgb(color_a)
        rb, gb, bb = self._hex_to_rgb(color_b)
        return self._rgb_to_hex((
            round(ra * amount_a + rb * amount_b),
            round(ga * amount_a + gb * amount_b),
            round(ba * amount_a + bb * amount_b),
        ))

    def _draw_fast_geometry(self, geom, outline: str, width: int = 1) -> int:
        """Draw non-selected/background copper in a faster outline-only mode.

        Fast mode intentionally affects only background/other nets.  Net A, Net B,
        measurement points, blocker dots and selected overlap geometry remain
        drawn by the exact renderer so measurements stay trustworthy.
        """

        if geom is None or getattr(geom, "is_empty", True):
            return 0
        geom = self._fast_display_geometry(geom)
        geom_type = getattr(geom, "geom_type", "")
        if geom_type == "Polygon":
            return self._draw_fast_polygon_outline(geom, outline=outline, width=width)
        if geom_type in {"MultiPolygon", "GeometryCollection"}:
            count = 0
            for sub in getattr(geom, "geoms", []):
                count += self._draw_fast_geometry(sub, outline=outline, width=width)
            return count
        if geom_type in {"LineString", "LinearRing"}:
            coords = [coord for xy in geom.coords for coord in self.world_to_screen(xy[0], xy[1])]
            if len(coords) >= 4:
                self.canvas.create_line(*coords, fill=outline, width=width)
                return 1
            return 0
        # Fallback to exact drawing for unusual simple geometries.
        return self._draw_geometry(geom, fill="", outline=outline, width=width)

    def _draw_fast_polygon_outline(self, poly, outline: str, width: int = 1) -> int:
        """Draw only the exterior boundary of a polygon for fast background view."""

        count = 0
        try:
            exterior = self._screen_coords(poly.exterior.coords)
        except Exception:
            return 0
        if len(exterior) >= 6:
            self.canvas.create_line(*exterior, fill=outline, width=width)
            count += 1
        # Draw only large holes in fast mode.  This keeps anti-pad/void context
        # without spending time on every tiny cutout in large pours.
        try:
            min_hole_area_mm2 = max(0.01, (2.0 / max(float(self.scale), 1e-9)) ** 2)
            for interior in poly.interiors:
                try:
                    from shapely.geometry import Polygon as _Polygon

                    if _Polygon(interior).area < min_hole_area_mm2:
                        continue
                except Exception:
                    pass
                coords = self._screen_coords(interior.coords)
                if len(coords) >= 6:
                    self.canvas.create_line(*coords, fill=self.COLORS["cutout"], width=1)
                    count += 1
        except Exception:
            pass
        return count

    def _fast_display_geometry(self, geom):
        """Return a topology-preserving simplified geometry for fast background draw."""

        if geom is None or getattr(geom, "is_empty", True):
            return geom
        try:
            # About 0.8 screen pixel in world units. This is display-only and is
            # applied only to non-selected copper.
            tolerance_mm = max(0.0, 0.8 / max(float(self.scale), 1e-9))
            simplified = geom.simplify(tolerance_mm, preserve_topology=True)
            if simplified is not None and not getattr(simplified, "is_empty", True):
                return simplified
        except Exception:
            pass
        return geom

    def _draw_geometry(self, geom, fill: str, outline: str, width: int = 1) -> int:
        if geom is None or getattr(geom, "is_empty", True):
            return 0
        geom_type = getattr(geom, "geom_type", "")
        if geom_type == "Polygon":
            return self._draw_polygon(geom, fill, outline, width)
        if geom_type in {"MultiPolygon", "GeometryCollection"}:
            count = 0
            for sub in getattr(geom, "geoms", []):
                count += self._draw_geometry(sub, fill, outline, width)
            return count
        if geom_type in {"LineString", "LinearRing"}:
            coords = [coord for xy in geom.coords for coord in self.world_to_screen(xy[0], xy[1])]
            if len(coords) >= 4:
                self.canvas.create_line(*coords, fill=outline, width=width)
                return 1
            return 0
        if geom_type == "Point":
            x, y = self.world_to_screen(geom.x, geom.y)
            r = max(2, width + 1)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=outline)
            return 1
        # Fallback: draw bounds.
        try:
            minx, miny, maxx, maxy = geom.bounds
        except Exception:
            return 0
        x1, y1 = self.world_to_screen(minx, miny)
        x2, y2 = self.world_to_screen(maxx, maxy)
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=outline, width=width)
        return 1

    def _draw_polygon(self, poly, fill: str, outline: str, width: int) -> int:
        """Draw a polygon without corrupting dense copper-pour contours.

        Earlier versions reduced dense polygons by taking every Nth vertex. That is
        unsafe for PCB copper pours: skipping vertices can create false diagonal
        edges and make ground zones look geometrically wrong. Use Shapely's
        topology-preserving simplification for display performance instead, and
        keep full coordinate order for normal-sized contours.
        """

        display_poly = self._display_simplified_polygon(poly)
        count = 0
        exterior = self._screen_coords(display_poly.exterior.coords)
        if len(exterior) >= 6:
            self.canvas.create_polygon(*exterior, fill=fill, outline=outline, width=width, stipple="gray50")
            count += 1
        # Draw holes in background so cutouts/anti-pads are visible.
        for interior in display_poly.interiors:
            coords = self._screen_coords(interior.coords)
            if len(coords) >= 6:
                self.canvas.create_polygon(*coords, fill=self.COLORS["background"], outline=self.COLORS["cutout"], width=1)
                count += 1
        return count

    def _display_simplified_polygon(self, poly):
        """Return topology-preserving display geometry for very dense polygons."""

        try:
            point_count = len(poly.exterior.coords) + sum(len(ring.coords) for ring in poly.interiors)
        except Exception:
            return poly

        # Keep normal PCB contours exact.  The ground-pour bug in the screenshot
        # came from reducing ~8k vertices to ~2k by blind sub-sampling.  Tk can
        # handle this size well enough, and preserving all vertices keeps cutouts
        # and narrow clearances visually correct.
        if point_count <= 25000:
            return poly

        try:
            tolerance_mm = max(0.0, 0.15 / max(float(self.scale), 1e-9))
            simplified = poly.simplify(tolerance_mm, preserve_topology=True)
            if simplified is not None and not getattr(simplified, "is_empty", True):
                # If simplify returns a MultiPolygon due to pathological input,
                # the caller for Polygon cannot draw it here; keep original.
                if getattr(simplified, "geom_type", "") == "Polygon":
                    return simplified
        except Exception:
            pass
        return poly

    def _screen_coords(self, coords) -> list[float]:
        flat: list[float] = []
        # Do not blindly decimate by index. PCB polygon contours encode narrow
        # isolation gaps and pour boundaries where every vertex can matter.
        for x, y in coords:
            sx, sy = self.world_to_screen(float(x), float(y))
            flat.extend([sx, sy])
        return flat

    def world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        return x * self.scale + self.offset_x, -y * self.scale + self.offset_y

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx - self.offset_x) / self.scale, -(sy - self.offset_y) / self.scale

    def _start_pan(self, event) -> None:
        self._drag_start = (event.x, event.y)
        self._drag_button = getattr(event, "num", None)
        self._drag_moved = False

    def _pan(self, event) -> None:
        if self._drag_start is None:
            return
        last_x, last_y = self._drag_start
        dx = event.x - last_x
        dy = event.y - last_y
        if abs(dx) > 1 or abs(dy) > 1:
            self._drag_moved = True
        self.offset_x += dx
        self.offset_y += dy
        self._drag_start = (event.x, event.y)
        self.redraw()

    def _end_pan(self, event) -> None:
        click_without_drag = not self._drag_moved
        button = self._drag_button
        self._drag_start = None
        self._drag_button = None
        self._drag_moved = False
        if click_without_drag and button == 1:
            self._select_net_from_click(event.x, event.y)

    def _select_net_from_click(self, sx: float, sy: float) -> None:
        picked = self._pick_net_at_screen(sx, sy)
        if picked is None:
            wx, wy = self.screen_to_world(sx, sy)
            self.status_var.set(
                f"No net found near click at {wx:.4f}, {wy:.4f} mm on layer {self.layer_var.get()}."
            )
            return
        net, distance_mm = picked
        role = self._next_click_role
        if role == "a":
            self.net_a_var.set(net)
            self.point_a = None
            self._next_click_role = "b"
            self._last_clicked_net = net
            self.status_var.set(f"Selected Net A = {net} by click; next click selects Net B.")
        else:
            # If the user clicks the same net again for Net B, keep it as Net A and wait for another net.
            if net == self.net_a_var.get().strip():
                self.status_var.set(f"Clicked {net}, already Net A. Click a different copper net for Net B.")
                return
            self.net_b_var.set(net)
            self.point_b = None
            self._next_click_role = "a"
            self._last_clicked_net = net
            self.status_var.set(
                f"Selected Net B = {net} by click; distance from click to copper was {distance_mm:.6f} mm."
            )
        self.redraw()

    def _pick_net_at_screen(self, sx: float, sy: float) -> tuple[str, float] | None:
        """Return the nearest net under/near a screen click.

        The hit test uses the same reconstructed Shapely geometry displayed by the
        viewer.  A small screen-space tolerance is converted to mm so picking is
        still possible at low zoom.  When several nets overlap at the same point,
        the smallest copper body is preferred; this usually selects a pad/track
        instead of a large copper pour.
        """

        layer = self.layer_var.get()
        by_net = self.result.net_geometry_by_layer.get(layer, {})
        if not by_net:
            return None
        wx, wy = self.screen_to_world(sx, sy)
        click_point = Point(wx, wy)
        tolerance_mm = max(0.003, min(0.25, 6.0 / max(self.scale, 1e-9)))
        candidates: list[tuple[float, float, str]] = []
        visible_nets = {net for net, _geom, _role in self.selected_geometries()}
        for net, geom in by_net.items():
            if geom is None or getattr(geom, "is_empty", True):
                continue
            try:
                minx, miny, maxx, maxy = geom.bounds
            except Exception:
                continue
            if wx < minx - tolerance_mm or wx > maxx + tolerance_mm:
                continue
            if wy < miny - tolerance_mm or wy > maxy + tolerance_mm:
                continue
            try:
                distance = float(geom.distance(click_point))
            except Exception:
                continue
            if distance <= tolerance_mm:
                try:
                    area = float(getattr(geom, "area", 0.0) or 0.0)
                except Exception:
                    area = 0.0
                # Visible nets get a slight advantage.  This keeps picking aligned
                # with what the user sees when a selected pair is already drawn.
                visibility_bias = -1e-9 if net in visible_nets else 0.0
                candidates.append((distance + visibility_bias, area, net))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (round(max(item[0], 0.0), 9), item[1], item[2]))
        distance_with_bias, _area, net = candidates[0]
        return net, max(0.0, distance_with_bias)

    def _on_mousewheel(self, event) -> None:
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        self._zoom_at(event.x, event.y, factor)

    def _zoom_at(self, sx: float, sy: float, factor: float) -> None:
        wx, wy = self.screen_to_world(sx, sy)
        old_scale = self.scale
        self.scale = max(0.001, min(50000.0, self.scale * factor))
        if self.scale == old_scale:
            return
        self.offset_x = sx - wx * self.scale
        self.offset_y = sy + wy * self.scale
        self.redraw()

    def _show_mouse_position(self, event) -> None:
        self._last_mouse_world = self.screen_to_world(event.x, event.y)
        # Avoid full redraw just to update text; set status directly.
        layer = self.layer_var.get()
        next_role = "Net A" if self._next_click_role == "a" else "Net B"
        missing = self._selected_nets_missing_on_current_layer()
        missing_text = "" if not missing else "; not on this layer: " + ", ".join(missing)
        self.status_var.set(
            f"Layer {layer}; zoom: {self.scale:.1f} px/mm; next click: {next_role}{missing_text}; mouse: {self._last_mouse_world[0]:.4f}, {self._last_mouse_world[1]:.4f} mm"
        )

    def _combined_bounds(self, geometries: list[object]) -> tuple[float, float, float, float] | None:
        bounds = []
        for geom in geometries:
            if geom is None or getattr(geom, "is_empty", True):
                continue
            try:
                bounds.append(tuple(float(v) for v in geom.bounds))
            except Exception:
                continue
        if not bounds:
            return None
        return (
            min(b[0] for b in bounds),
            min(b[1] for b in bounds),
            max(b[2] for b in bounds),
            max(b[3] for b in bounds),
        )

    def _visible_world_bounds(self) -> tuple[float, float, float, float]:
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        x1, y1 = self.screen_to_world(0, h)
        x2, y2 = self.screen_to_world(w, 0)
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def _nice_grid_step(self, raw_step: float) -> float:
        if raw_step <= 0:
            return 1.0
        exp = math.floor(math.log10(raw_step))
        base = raw_step / (10 ** exp)
        if base <= 1:
            nice = 1
        elif base <= 2:
            nice = 2
        elif base <= 5:
            nice = 5
        else:
            nice = 10
        return nice * (10 ** exp)


class GeometryViewerLauncherMixin:
    """Mixin methods used by the main GUI to open geometry viewer windows."""

    def _measurement_from_selected_critical(self) -> MeasurementRecord | None:
        selection = self.critical_tree.selection()
        if not selection or self.last_result is None:
            return None
        try:
            row_index = int(selection[0])
        except Exception:
            # Tree item IDs default to I001, etc.  Fall back to visible row index.
            children = list(self.critical_tree.get_children())
            try:
                row_index = children.index(selection[0])
            except ValueError:
                return None
        records = self.last_result.critical_measurements[:1000]
        return records[row_index] if 0 <= row_index < len(records) else None

    def _debug_from_selected(self) -> GeometryDebugRecord | None:
        selection = self.debug_tree.selection()
        if not selection:
            return None
        try:
            return self.debug_records[int(selection[0])]
        except Exception:
            return None
