"""Tkinter desktop GUI for ODB++ net-to-net clearance analysis."""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import traceback
from dataclasses import replace
from pathlib import Path
from importlib import resources
from tkinter import BOTH, END, LEFT, RIGHT, TOP, X, BooleanVar, DoubleVar, Entry, PhotoImage, StringVar, Text, Tk, Toplevel, filedialog, messagebox
from tkinter import ttk

from . import __version__
from .analyzer import ClearanceAnalyzer
from .geometry_viewer import GeometryViewer
from .odb_parser import OdbParser
from .settings_profile import DEFAULT_SETTINGS_FILENAME, analysis_config_to_profile, profile_to_analysis_config, read_settings_profile, write_settings_profile
from .models import AnalysisCancelled, AnalysisConfig, AnalysisResult, MeasurementRecord, PerNetMinimum
from .theme import MATERIAL_COLORS, install_material_theme, tag_tree_rows
from .layer_rules import guess_layer_role, guess_layer_roles, normalize_layer_role, role_display
from .voltage_estimator import estimate_effective_max_voltage, estimate_ipc2221a_max_voltage, ipc2221a_settings_text, material_group_from_cti, voltage_settings_summary




def _load_packaged_photoimage(name: str, master=None) -> PhotoImage | None:
    """Load a PNG image shipped inside the package.

    Returns ``None`` if the asset is missing or Tk cannot load it.
    """

    try:
        ref = resources.files("odb_clearance_analyzer").joinpath("assets", name)
        with resources.as_file(ref) as asset_path:
            return PhotoImage(master=master, file=str(asset_path))
    except Exception:
        return None


class ClearanceGui(ttk.Frame):
    """Main Tkinter application frame."""

    def __init__(self, master: Tk):
        install_material_theme(master)
        super().__init__(master, padding=0, style="App.TFrame")
        self.master = master
        self.pack(fill=BOTH, expand=True)
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.last_result: AnalysisResult | None = None
        self.debug_records = []
        self.visible_critical_records: list[MeasurementRecord] = []
        self.visible_per_net_records: list[PerNetMinimum] = []
        self.visible_airgap_records = []
        self.layer_roles: dict[str, str] = {}
        self.layer_role_reasons: dict[str, str] = {}
        self.layer_role_tree: ttk.Treeview | None = None
        self.iec_layer_pollution_degrees: dict[str, int] = {}
        self.iec_layer_reasons: dict[str, str] = {}
        self.iec_layer_tree: ttk.Treeview | None = None
        self.last_metadata_job = None

        self.odb_path = StringVar()
        self.output_dir = StringVar(value=str(Path.cwd() / "clearance_report"))
        self.threshold_mm = DoubleVar(value=0.15)
        self.include_none = BooleanVar(value=False)
        self.effective_air_gap_matrix = BooleanVar(value=False)
        self.dark_theme = BooleanVar(value=False)
        self.clearance_gradient = BooleanVar(value=True)
        self.cti = DoubleVar(value=175.0)
        self.pollution_degree = StringVar(value="2")
        self.altitude_m = DoubleVar(value=5500.0)
        self.material_group_preview = StringVar(value=voltage_settings_summary(175.0, 2, 5500.0))
        self.export_effective_max_voltage = BooleanVar(value=True)
        self.export_ipc2221a_max_voltage = BooleanVar(value=True)
        self.external_conformal_coating = BooleanVar(value=False)
        self.metallic_particle_size_mm = DoubleVar(value=0.0)
        self.debug_limit = DoubleVar(value=500)
        self.status = StringVar(value="Ready")
        self.header_stats = StringVar(value="No ODB++ loaded")
        self.settings_profile_path = StringVar(value="")
        self.settings_profile_status = StringVar(value="No settings profile loaded")
        self._tree_sort_state: dict[int, tuple[str, bool]] = {}
        self._tree_heading_text: dict[tuple[int, str], str] = {}
        self._window_icon = None
        self._header_icon = None

        self._build_ui()
        self.after(150, self._poll_queue)

    def _apply_branding(self) -> None:
        """Load packaged icon/banner assets and apply window branding."""

        self._window_icon = _load_packaged_photoimage("app_icon.png", master=self.master)
        self._header_icon = _load_packaged_photoimage("app_icon_small.png", master=self.master)
        if self._window_icon is not None:
            try:
                self.master.iconphoto(True, self._window_icon)
            except Exception:
                pass

    def _make_card(self, parent, title: str, subtitle: str = "") -> ttk.Frame:
        """Create a Material-style card and return its body frame."""

        card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 14, 16, 16))
        if title:
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(card, text=subtitle, style="CardSubtitle.TLabel").pack(anchor="w", pady=(2, 10))
        elif title:
            ttk.Frame(card, style="Card.TFrame", height=8).pack(fill=X)
        return card

    def _make_collapsible_card(
        self,
        parent,
        title: str,
        subtitle: str = "",
        collapsed: bool = False,
    ) -> tuple[ttk.Frame, ttk.Frame]:
        """Create a compact card with a clickable collapse/expand header."""

        card = ttk.Frame(parent, style="Card.TFrame", padding=(10, 6, 10, 8))
        header = ttk.Frame(card, style="Card.TFrame")
        header.pack(fill=X)

        expanded = BooleanVar(value=not collapsed)
        button_text = StringVar(value=("▾ " if expanded.get() else "▸ ") + title)

        body = ttk.Frame(card, style="Card.TFrame")

        def toggle() -> None:
            if expanded.get():
                body.pack_forget()
                expanded.set(False)
                button_text.set("▸ " + title)
            else:
                body.pack(fill=X, pady=(6, 0))
                expanded.set(True)
                button_text.set("▾ " + title)

        ttk.Button(header, textvariable=button_text, style="Text.TButton", command=toggle).pack(side=LEFT)
        if subtitle:
            ttk.Label(header, text=subtitle, style="CardSubtitle.TLabel").pack(side=LEFT, padx=(10, 0))
        if expanded.get():
            body.pack(fill=X, pady=(6, 0))
        return card, body

    def _build_ui(self) -> None:
        self.master.title(f"ODB++ Clearance Analyzer {__version__}")
        self.master.geometry("1240x800")
        self.master.minsize(980, 640)
        self.master.configure(bg=MATERIAL_COLORS["app_bg"])
        self._apply_branding()

        appbar = ttk.Frame(self, style="AppBar.TFrame", padding=(20, 14, 20, 12))
        appbar.pack(fill=X)
        appbar.columnconfigure(0, weight=1)
        appbar.columnconfigure(1, weight=1)

        title_row = ttk.Frame(appbar, style="AppBar.TFrame")
        title_row.grid(row=0, column=0, sticky="w")
        if self._header_icon is not None:
            ttk.Label(title_row, image=self._header_icon, style="AppBarSubtitle.TLabel").pack(side=LEFT, padx=(0, 12))
        title_text = ttk.Frame(title_row, style="AppBar.TFrame")
        title_text.pack(side=LEFT, fill=X, expand=True)
        ttk.Label(title_text, text=f"ODB++ Clearance Analyzer {__version__}", style="AppBarTitle.TLabel").pack(anchor="w")
        ttk.Label(
            title_text,
            text="Same-layer copper spacing, voltage-screening columns, and geometry inspection",
            style="AppBarSubtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        status_panel = ttk.Frame(appbar, style="AppBar.TFrame")
        status_panel.grid(row=0, column=1, sticky="e", padx=(18, 0))
        ttk.Label(status_panel, textvariable=self.status, style="AppBarSubtitle.TLabel").pack(anchor="e")
        self.progress = ttk.Progressbar(status_panel, mode="indeterminate", style="Horizontal.TProgressbar", length=360)
        self.progress.pack(anchor="e", fill=X, pady=(4, 3))
        ttk.Label(status_panel, textvariable=self.header_stats, style="AppBarSubtitle.TLabel", wraplength=520, justify=RIGHT).pack(anchor="e")

        content = ttk.Frame(self, style="App.TFrame", padding=(16, 12, 16, 12))
        content.pack(fill=BOTH, expand=True)

        io_frame, io_body = self._make_collapsible_card(
            content,
            "Input, output and analysis",
            "ODB++ source, output folder, threshold, options and run controls",
            collapsed=False,
        )
        io_frame.pack(fill=X, pady=(0, 8))

        io_form = ttk.Frame(io_body, style="Card.TFrame")
        io_form.pack(fill=X)
        io_form.columnconfigure(1, weight=1)
        io_form.columnconfigure(4, weight=1)

        ttk.Label(io_form, text="ODB++ archive/folder").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(io_form, textvariable=self.odb_path).grid(row=0, column=1, sticky="ew", pady=4, ipady=2)
        ttk.Button(io_form, text="Browse", style="Text.TButton", command=self._browse_odb).grid(row=0, column=2, padx=(10, 0), pady=4)
        ttk.Button(io_form, text="Read ODB++", style="Primary.TButton", command=self._read_odb_metadata).grid(row=0, column=3, padx=(8, 18), pady=4)

        ttk.Label(io_form, text="Output folder").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Entry(io_form, textvariable=self.output_dir).grid(row=1, column=1, sticky="ew", pady=4, ipady=2)
        ttk.Button(io_form, text="Browse", style="Text.TButton", command=self._browse_output).grid(row=1, column=2, padx=(10, 0), pady=4)

        threshold_label = ttk.Label(io_form, text="Critical threshold, mm", font=("Segoe UI", 9, "bold"))
        threshold_label.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(8, 4))
        self.threshold_entry = Entry(
            io_form,
            textvariable=self.threshold_mm,
            width=10,
            bg="#FFF8C6",
            highlightbackground="#D6B656",
            highlightcolor="#D6B656",
            highlightthickness=1,
            relief="solid",
        )
        self.threshold_entry.grid(row=2, column=1, sticky="w", pady=(8, 4), ipady=2)

        option_row = ttk.Frame(io_body, style="Card.TFrame")
        option_row.pack(fill=X, pady=(6, 0))
        ttk.Checkbutton(option_row, text="Include $NONE$ net", variable=self.include_none).pack(side=LEFT, padx=(0, 14))
        ttk.Checkbutton(
            option_row,
            text="Effective Net-to-Net distance",
            variable=self.effective_air_gap_matrix,
        ).pack(side=LEFT, padx=(0, 14))
        ttk.Checkbutton(
            option_row,
            text="Dark theme",
            variable=self.dark_theme,
            command=self._toggle_theme,
        ).pack(side=LEFT, padx=(0, 18))

        self.run_button = ttk.Button(option_row, text="Run analysis", style="Primary.TButton", command=self._start_analysis)
        self.run_button.pack(side=LEFT, padx=(0, 8))
        self.stop_button = ttk.Button(option_row, text="Stop", style="Danger.TButton", command=self._stop_analysis, state="disabled")
        self.stop_button.pack(side=LEFT, padx=(0, 8))
        ttk.Button(option_row, text="Open output", command=self._open_output_folder).pack(side=LEFT, padx=(0, 8))
        ttk.Button(option_row, text="Geometry viewer", command=self._open_geometry_viewer_overview).pack(side=LEFT)

        results_card = self._make_card(
            content,
            "Reports and diagnostics",
            "Summary, critical pairs, per-net minima, decoded attributes, and geometry debug records.",
        )
        results_card.pack(fill=BOTH, expand=True)
        tabs = ttk.Notebook(results_card)
        tabs.pack(fill=BOTH, expand=True)

        settings_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        layer_roles_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        settings_profile_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        summary_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        critical_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        per_net_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        airgap_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        attr_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        debug_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")
        log_tab = ttk.Frame(tabs, padding=8, style="Card.TFrame")

        tabs.add(settings_tab, text="IEC 60664-1")
        tabs.add(layer_roles_tab, text="IPC-2221A")
        tabs.add(settings_profile_tab, text="Settings")
        tabs.add(summary_tab, text="Summary")
        tabs.add(critical_tab, text="Critical pairs")
        tabs.add(per_net_tab, text="Per-net minimum")
        tabs.add(airgap_tab, text="Effective Net-to-Net distance")
        tabs.add(attr_tab, text="Feature attributes")
        tabs.add(debug_tab, text="Debug zero/overlap")
        tabs.add(log_tab, text="Log")

        self._create_settings_tab(settings_tab)
        self._create_layer_roles_tab(layer_roles_tab)
        self._create_settings_profile_tab(settings_profile_tab)
        self.summary_text = self._create_summary_tree(summary_tab)
        self.critical_tree = self._create_measurement_tree(critical_tab)
        self.per_net_tree = self._create_per_net_tree(per_net_tab)
        self.airgap_tree = self._create_airgap_tree(airgap_tab)
        self.feature_attr_tree = self._create_feature_attr_tree(attr_tab)
        self.debug_tree = self._create_debug_tree(debug_tab)
        self.log = self._create_log_tree(log_tab)

        note = ttk.Label(
            content,
            text=(
                "Measurement is same-layer copper-to-copper clearance from reconstructed ODB++ geometry. "
                "Formal IEC/UL pass/fail still needs a voltage-class table."
            ),
            style="Muted.TLabel",
        )
        note.pack(anchor="w", pady=(12, 0))

    def _install_tree_sorting(self, tree: ttk.Treeview, numeric_columns: set[str] | None = None) -> None:
        """Enable click-to-sort behavior on all columns of one Treeview.

        First click sorts ascending. The next click on the same header reverses
        the order. Sorting moves whole rows, so tags, colors, selections, and
        hidden row IDs remain attached to the row.
        """

        numeric_columns = numeric_columns or set()
        display = str(tree.cget("show") or "")
        columns = list(tree["columns"])
        sortable_columns = list(columns)
        if "tree" in display:
            sortable_columns = ["#0", *sortable_columns]

        tree_id = id(tree)
        for col in sortable_columns:
            try:
                original_text = str(tree.heading(col).get("text", col))
            except Exception:
                original_text = str(col)
            self._tree_heading_text[(tree_id, col)] = original_text
            tree.heading(
                col,
                text=original_text,
                command=lambda c=col, t=tree, n=set(numeric_columns): self._sort_tree_by_column(t, c, n),
            )

    def _sort_tree_by_column(self, tree: ttk.Treeview, column: str, numeric_columns: set[str]) -> None:
        """Sort a Treeview by one column and toggle ascending/descending order."""

        tree_id = id(tree)
        previous_column, previous_reverse = self._tree_sort_state.get(tree_id, ("", True))
        reverse = False if previous_column != column else not previous_reverse

        rows = list(tree.get_children(""))
        indexed_rows = list(enumerate(rows))

        def row_value(item_id: str):
            if column == "#0":
                raw = tree.item(item_id, "text")
            else:
                try:
                    raw = tree.set(item_id, column)
                except Exception:
                    raw = ""
            return self._tree_sort_key(raw, force_numeric=column in numeric_columns)

        indexed_rows.sort(key=lambda pair: (row_value(pair[1]), pair[0]), reverse=reverse)

        for new_index, (_old_index, item_id) in enumerate(indexed_rows):
            tree.move(item_id, "", new_index)

        self._tree_sort_state[tree_id] = (column, reverse)
        self._refresh_sort_heading_marks(tree, active_column=column, reverse=reverse)

    def _tree_sort_key(self, value, force_numeric: bool = False):
        """Return a robust sort key that handles numbers, blanks and text."""

        text = "" if value is None else str(value).strip()
        if text == "":
            return (2, 0.0, "")
        numeric = self._parse_sort_number(text)
        if force_numeric or numeric is not None:
            return (0, numeric if numeric is not None else float("-inf"), text.lower())
        return (1, 0.0, text.lower())

    def _parse_sort_number(self, text: str) -> float | None:
        """Parse common numeric table formats, including points like '(1.2, 3.4)'."""

        cleaned = text.strip()
        if not cleaned:
            return None
        cleaned = cleaned.replace(",", "")
        # Try direct float first.
        try:
            return float(cleaned)
        except Exception:
            pass
        # Fall back to the first number in strings such as '(104.2, -70.9)'.
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except Exception:
            return None

    def _refresh_sort_heading_marks(self, tree: ttk.Treeview, active_column: str, reverse: bool) -> None:
        """Update header arrows after a sort."""

        tree_id = id(tree)
        display = str(tree.cget("show") or "")
        columns = list(tree["columns"])
        sortable_columns = list(columns)
        if "tree" in display:
            sortable_columns = ["#0", *sortable_columns]
        arrow = " ↓" if reverse else " ↑"
        for col in sortable_columns:
            base = self._tree_heading_text.get((tree_id, col), str(col))
            try:
                tree.heading(col, text=base + (arrow if col == active_column else ""))
            except Exception:
                pass

    def _create_summary_tree(self, parent) -> ttk.Treeview:
        """Create the Summary tab table."""

        tree = ttk.Treeview(parent, columns=("value",), show="tree headings", height=16, style="Modern.Treeview")
        yscroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        tag_tree_rows(tree)
        tree.heading("#0", text="Field")
        tree.heading("value", text="Value")
        tree.column("#0", width=300, anchor="w")
        tree.column("value", width=850, anchor="w")
        self._install_tree_sorting(tree)
        return tree

    def _create_log_tree(self, parent) -> ttk.Treeview:
        """Create the Log tab table."""

        tree = ttk.Treeview(parent, columns=("message",), show="headings", height=16, style="Modern.Treeview")
        yscroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        tag_tree_rows(tree)
        tree.heading("message", text="Message")
        tree.column("message", width=1100, anchor="w")
        self._install_tree_sorting(tree)
        return tree

    def _make_tree_with_scrollbars(self, parent, columns: tuple[str, ...]) -> ttk.Treeview:
        """Create a Treeview with fixed right/bottom scrollbars.

        Tkinter Treeview scrollbars are easiest to keep aligned when the
        table lives inside a dedicated grid-managed frame.  This avoids the
        previous pack-order problem where the vertical scrollbar could appear
        after the table instead of as a right-side slider.
        """

        table_frame = ttk.Frame(parent, style="Card.TFrame")
        table_frame.pack(fill=BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(table_frame, columns=columns, show="headings", style="Modern.Treeview")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        tag_tree_rows(tree)
        self._configure_clearance_gradient_tags(tree)
        return tree

    def _hex_to_rgb(self, color: str) -> tuple[int, int, int]:
        color = color.lstrip("#")
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    def _rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        return "#" + "".join(f"{max(0, min(255, value)):02X}" for value in rgb)

    def _lerp_color(self, a: str, b: str, t: float) -> str:
        ar, ag, ab = self._hex_to_rgb(a)
        br, bg, bb = self._hex_to_rgb(b)
        return self._rgb_to_hex((
            round(ar + (br - ar) * t),
            round(ag + (bg - ag) * t),
            round(ab + (bb - ab) * t),
        ))

    def _gradient_color(self, bucket: int) -> str:
        """Return clearance-gradient background color for bucket 0..10."""

        bucket = max(0, min(10, int(bucket)))
        dark = bool(self.dark_theme.get())
        if dark:
            red, amber, green = "#4A1C1C", "#4A3B14", "#123B25"
        else:
            red, amber, green = "#FCE4E4", "#FFF4CC", "#DDF4E5"
        if bucket <= 5:
            return self._lerp_color(red, amber, bucket / 5.0)
        return self._lerp_color(amber, green, (bucket - 5) / 5.0)

    def _configure_clearance_gradient_tags(self, tree: ttk.Treeview) -> None:
        """Install gradient row tags for a Treeview."""

        try:
            for bucket in range(11):
                tree.tag_configure(
                    f"clearance_grad_{bucket:02d}",
                    background=self._gradient_color(bucket),
                    foreground=MATERIAL_COLORS["text"],
                )
        except Exception:
            pass

    def _clearance_row_tag(self, clearance_mm: float | None, idx: int, zero_is_critical: bool = True) -> str:
        """Return row tag based on the active gradient setting."""

        if clearance_mm is None:
            return "even" if idx % 2 == 0 else "odd"
        if bool(self.clearance_gradient.get()):
            threshold = max(float(self.threshold_mm.get() or 0.0), 1e-12)
            ratio = max(0.0, min(1.0, float(clearance_mm) / threshold))
            bucket = int(round(ratio * 10.0))
            return f"clearance_grad_{bucket:02d}"
        if zero_is_critical and float(clearance_mm) <= 0:
            return "critical"
        return "even" if idx % 2 == 0 else "odd"

    def _recolor_clearance_tables(self) -> None:
        """Re-apply row tags after toggling the clearance gradient or theme."""

        self._configure_clearance_gradient_tags(self.critical_tree)
        self._configure_clearance_gradient_tags(self.per_net_tree)
        self._configure_clearance_gradient_tags(self.debug_tree)
        self._configure_clearance_gradient_tags(self.airgap_tree)

        for idx, iid in enumerate(self.critical_tree.get_children()):
            if idx < len(self.visible_critical_records):
                self.critical_tree.item(iid, tags=(self._clearance_row_tag(self.visible_critical_records[idx].clearance_mm, idx),))
        for idx, iid in enumerate(self.per_net_tree.get_children()):
            if idx < len(self.visible_per_net_records):
                self.per_net_tree.item(iid, tags=(self._clearance_row_tag(self.visible_per_net_records[idx].min_clearance_mm, idx),))
        for idx, iid in enumerate(self.debug_tree.get_children()):
            if idx < len(self.debug_records):
                self.debug_tree.item(iid, tags=(self._clearance_row_tag(self.debug_records[idx].clearance_mm, idx),))
        for idx, iid in enumerate(self.airgap_tree.get_children()):
            if idx < len(self.visible_airgap_records):
                rec = self.visible_airgap_records[idx]
                if bool(self.clearance_gradient.get()):
                    tag = self._clearance_row_tag(rec.effective_air_gap_mm, idx, zero_is_critical=False)
                else:
                    tag = "critical" if getattr(rec, "copper_on_path", False) else ("even" if idx % 2 == 0 else "odd")
                self.airgap_tree.item(iid, tags=(tag,))

    def _toggle_clearance_gradient(self) -> None:
        self._recolor_clearance_tables()


    def _create_settings_profile_tab(self, parent) -> None:
        """Create load/export JSON settings profile tab."""

        ttk.Label(
            parent,
            text=(
                "Load or export all manual/project settings as JSON. This includes threshold, IEC settings, "
                "IPC layer roles, IEC layer pollution-degree overrides, coating, particle size, altitude and export flags. "
                f"During analysis the same profile is automatically written to {DEFAULT_SETTINGS_FILENAME} in the output folder."
            ),
            wraplength=1100,
            style="CardSubtitle.TLabel",
        ).pack(anchor="w", fill=X, pady=(0, 10))

        display_settings = ttk.Frame(parent, style="Card.TFrame")
        display_settings.pack(fill=X, pady=(0, 10))
        ttk.Label(display_settings, text="Diagnostics / display", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 12))
        ttk.Checkbutton(
            display_settings,
            text="Clearance gradient",
            variable=self.clearance_gradient,
            command=self._toggle_clearance_gradient,
        ).pack(side=LEFT, padx=(0, 18))
        ttk.Label(display_settings, text="Debug rows").pack(side=LEFT, padx=(0, 8))
        ttk.Entry(display_settings, width=8, textvariable=self.debug_limit).pack(side=LEFT, padx=(0, 18), ipady=2)
        ttk.Label(
            display_settings,
            text="Gradient is on by default. Debug rows controls how many geometry-diagnostic rows are generated/exported.",
            style="Muted.TLabel",
        ).pack(side=LEFT, fill=X, expand=True)

        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=(0, 8))

        ttk.Button(row, text="Load settings JSON", style="Primary.TButton", command=self._load_settings_profile_dialog).pack(side=LEFT, padx=(0, 8))
        ttk.Button(row, text="Export current settings JSON", command=self._export_settings_profile_dialog).pack(side=LEFT, padx=(0, 8))
        ttk.Button(row, text="Refresh preview", command=self._refresh_settings_profile_preview).pack(side=LEFT, padx=(0, 8))

        path_row = ttk.Frame(parent, style="Card.TFrame")
        path_row.pack(fill=X, pady=(0, 8))
        ttk.Label(path_row, text="Profile path").pack(side=LEFT, padx=(0, 8))
        ttk.Entry(path_row, textvariable=self.settings_profile_path).pack(side=LEFT, fill=X, expand=True)

        ttk.Label(parent, textvariable=self.settings_profile_status, style="Status.TLabel").pack(anchor="w", fill=X, pady=(0, 8))

        self.settings_profile_preview = Text(parent, height=18, wrap="none", borderwidth=0)
        self.settings_profile_preview.pack(fill=BOTH, expand=True)

        self._refresh_settings_profile_preview()

    def _current_analysis_config(self) -> AnalysisConfig:
        """Build AnalysisConfig from current GUI/manual settings."""

        return AnalysisConfig(
            odb_path=Path(self.odb_path.get()),
            output_dir=Path(self.output_dir.get()),
            threshold_mm=float(self.threshold_mm.get()),
            include_none_net=bool(self.include_none.get()),
            debug_limit=max(0, int(self.debug_limit.get())),
            effective_air_gap_matrix=bool(self.effective_air_gap_matrix.get()),
            cti=float(self.cti.get()),
            pollution_degree=int(float(self.pollution_degree.get())),
            altitude_m=float(self.altitude_m.get()),
            layer_roles=dict(self.layer_roles),
            layer_pollution_degrees=dict(self.iec_layer_pollution_degrees),
            external_conformal_coating=bool(self.external_conformal_coating.get()),
            metallic_particle_size_mm=max(0.0, float(self.metallic_particle_size_mm.get())),
            export_effective_max_voltage=bool(self.export_effective_max_voltage.get()),
            export_ipc2221a_max_voltage=bool(self.export_ipc2221a_max_voltage.get()),
        )

    def _current_settings_profile(self, *, source: str = "gui_manual_export") -> dict:
        """Return JSON profile for current GUI settings."""

        return analysis_config_to_profile(
            self._current_analysis_config(),
            app_version=__version__,
            include_paths=True,
            source=source,
        )

    def _refresh_settings_profile_preview(self) -> None:
        """Refresh JSON preview in Settings tab."""

        if not hasattr(self, "settings_profile_preview"):
            return
        try:
            profile = self._current_settings_profile(source="gui_preview")
            text = json.dumps(profile, indent=2, sort_keys=True)
        except Exception as exc:
            text = f"Could not build settings preview: {exc}"
        self.settings_profile_preview.configure(state="normal")
        self.settings_profile_preview.delete("1.0", END)
        self.settings_profile_preview.insert("1.0", text)
        self.settings_profile_preview.configure(state="normal")

    def _export_settings_profile_dialog(self) -> None:
        """Export current GUI settings to a JSON file."""

        default_dir = Path(self.output_dir.get()).expanduser() if self.output_dir.get().strip() else Path.cwd()
        path = filedialog.asksaveasfilename(
            title="Export settings JSON",
            initialdir=str(default_dir),
            initialfile=DEFAULT_SETTINGS_FILENAME,
            defaultextension=".json",
            filetypes=[("JSON settings", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            profile = self._current_settings_profile(source="manual_gui_export")
            write_settings_profile(Path(path), profile)
            self.settings_profile_path.set(str(path))
            self.settings_profile_status.set(f"Exported settings to {path}")
            self._refresh_settings_profile_preview()
            self._append_log(f"Exported settings JSON: {path}")
        except Exception as exc:
            messagebox.showerror("Export settings failed", str(exc))
            self.settings_profile_status.set("Settings export failed")

    def _load_settings_profile_dialog(self) -> None:
        """Load JSON settings profile and apply it to the GUI."""

        path = filedialog.askopenfilename(
            title="Load settings JSON",
            filetypes=[("JSON settings", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            profile = read_settings_profile(Path(path))
            base = self._current_analysis_config()
            config = profile_to_analysis_config(profile, base_config=base)
            self._apply_config_to_ui(config)
            self.settings_profile_path.set(str(path))
            self.settings_profile_status.set(f"Loaded settings from {path}")
            self._refresh_settings_profile_preview()
            self._append_log(f"Loaded settings JSON: {path}")
        except Exception as exc:
            messagebox.showerror("Load settings failed", str(exc))
            self.settings_profile_status.set("Settings load failed")

    def _apply_config_to_ui(self, config: AnalysisConfig) -> None:
        """Apply loaded AnalysisConfig values to GUI controls and assignment tables."""

        self.odb_path.set(str(config.odb_path) if str(config.odb_path) else self.odb_path.get())
        self.output_dir.set(str(config.output_dir))
        self.threshold_mm.set(float(config.threshold_mm))
        self.include_none.set(bool(config.include_none_net))
        self.debug_limit.set(int(config.debug_limit))
        self.effective_air_gap_matrix.set(bool(config.effective_air_gap_matrix))
        self.cti.set(float(config.cti))
        self.pollution_degree.set(str(int(config.pollution_degree)))
        self.altitude_m.set(float(config.altitude_m))
        self.layer_roles = dict(config.layer_roles)
        self.layer_role_reasons = {layer: "loaded from settings JSON" for layer in self.layer_roles}
        self.iec_layer_pollution_degrees = {str(k): int(v) for k, v in dict(config.layer_pollution_degrees).items()}
        self.iec_layer_reasons = {layer: "loaded from settings JSON" for layer in self.iec_layer_pollution_degrees}
        self.external_conformal_coating.set(bool(config.external_conformal_coating))
        self.metallic_particle_size_mm.set(float(config.metallic_particle_size_mm))
        self.export_effective_max_voltage.set(bool(config.export_effective_max_voltage))
        self.export_ipc2221a_max_voltage.set(bool(config.export_ipc2221a_max_voltage))
        self._refresh_layer_role_tree()
        self._refresh_iec_layer_tree()
        self._update_voltage_settings_preview()

    def _create_settings_tab(self, parent) -> None:
        """Create IEC 60664-1 settings and keep all controls plus the layer table visible."""

        top = ttk.Frame(parent, style="Card.TFrame")
        top.pack(fill=X, pady=(0, 6))
        ttk.Label(
            top,
            text=(
                "IEC 60664-1 settings for the Effective max voltage V calculation. "
                "Controls are visible here, and the per-layer pollution-degree table remains below."
            ),
            wraplength=1050,
            style="CardSubtitle.TLabel",
        ).pack(side=LEFT, fill=X, expand=True)

        settings = ttk.Frame(parent, style="Card.TFrame")
        settings.pack(fill=X, pady=(0, 6))
        for col in (1, 3, 5):
            settings.columnconfigure(col, weight=1)

        ttk.Label(settings, text="CTI").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(settings, textvariable=self.cti, width=10).grid(row=0, column=1, sticky="w", padx=(0, 18), pady=3)

        ttk.Label(settings, text="External/base PD").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=3)
        ttk.Combobox(settings, textvariable=self.pollution_degree, values=("1", "2", "3", "4"), width=8, state="readonly").grid(
            row=0, column=3, sticky="w", padx=(0, 18), pady=3
        )

        ttk.Label(settings, text="Metallic particles, mm").grid(row=0, column=4, sticky="w", padx=(0, 6), pady=3)
        ttk.Entry(settings, textvariable=self.metallic_particle_size_mm, width=10).grid(row=0, column=5, sticky="w", padx=(0, 18), pady=3)

        ttk.Checkbutton(
            settings,
            text="External conformal coating: assign external layers as PD2",
            variable=self.external_conformal_coating,
            command=self._on_external_conformal_changed,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=3)

        ttk.Checkbutton(
            settings,
            text="Export Effective max voltage V",
            variable=self.export_effective_max_voltage,
        ).grid(row=1, column=3, columnspan=2, sticky="w", padx=(0, 18), pady=3)

        ttk.Button(
            settings,
            text="Update preview",
            command=self._update_voltage_settings_preview,
        ).grid(row=1, column=5, sticky="w", pady=3)

        ttk.Label(settings, text="Current IEC settings").grid(row=2, column=0, sticky="nw", padx=(0, 6), pady=(4, 2))
        ttk.Label(settings, textvariable=self.material_group_preview, wraplength=900, style="Status.TLabel").grid(
            row=2, column=1, columnspan=5, sticky="ew", pady=(4, 2)
        )

        button_row = ttk.Frame(parent, style="Card.TFrame")
        button_row.pack(anchor="w", fill=X, pady=(0, 6))
        ttk.Button(button_row, text="Read ODB++", style="Primary.TButton", command=self._read_odb_metadata).pack(side=LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Auto-assign IEC PD", command=self._auto_assign_iec_pollution_degrees).pack(side=LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Set selected PD1", command=lambda: self._set_selected_iec_pollution_degree(1)).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="PD2", command=lambda: self._set_selected_iec_pollution_degree(2)).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="PD3", command=lambda: self._set_selected_iec_pollution_degree(3)).pack(side=LEFT, padx=(0, 6))
        ttk.Button(button_row, text="PD4", command=lambda: self._set_selected_iec_pollution_degree(4)).pack(side=LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Recalculate voltage columns", command=self._recalculate_voltage_columns).pack(side=LEFT, padx=(0, 8))

        table_label = ttk.Label(
            parent,
            text=(
                "Layer pollution-degree table. Internal/external role comes from the IPC-2221A tab. "
                "Double-click a row to cycle PD1 → PD2 → PD3 → PD4."
            ),
            wraplength=1050,
            style="Muted.TLabel",
        )
        table_label.pack(anchor="w", fill=X, pady=(0, 4))

        table_holder = ttk.Frame(parent, style="Card.TFrame")
        table_holder.pack(fill=BOTH, expand=True, pady=(0, 0))

        columns = ("order", "layer", "role", "pollution_degree", "particle_adjustment", "reason")
        self.iec_layer_tree = self._make_tree_with_scrollbars(table_holder, columns)
        try:
            self.iec_layer_tree.configure(height=12)
        except Exception:
            pass
        headings = {
            "order": "#",
            "layer": "Layer",
            "role": "Role",
            "pollution_degree": "IEC pollution degree",
            "particle_adjustment": "External particle correction mm",
            "reason": "Default/override reason",
        }
        widths = {"order": 50, "layer": 220, "role": 90, "pollution_degree": 150, "particle_adjustment": 220, "reason": 560}
        for col in columns:
            self.iec_layer_tree.heading(col, text=headings[col])
            self.iec_layer_tree.column(col, width=widths[col], anchor="w")
        self._install_tree_sorting(self.iec_layer_tree, numeric_columns={"order", "pollution_degree", "particle_adjustment"})
        self.iec_layer_tree.bind("<Double-1>", lambda _event: self._cycle_selected_iec_pollution_degree())

        for var in (self.cti, self.pollution_degree, self.altitude_m, self.metallic_particle_size_mm):
            try:
                var.trace_add("write", lambda *_args: self._update_voltage_settings_preview())
            except Exception:
                pass
        self._update_voltage_settings_preview()
        self._refresh_iec_layer_tree()


    def _create_layer_roles_tab(self, parent) -> None:
        """Create the IPC-2221A settings and layer-role assignment tab."""

        top = ttk.Frame(parent, style="Card.TFrame")
        top.pack(fill=X, pady=(0, 8))

        ttk.Label(
            top,
            text=(
                "IPC-2221A/B voltage estimate settings. Altitude selects the external conductor spacing class, "
                "and each signal layer must be assigned as external or internal."
            ),
            wraplength=1050,
            style="CardSubtitle.TLabel",
        ).pack(side=LEFT, fill=X, expand=True)

        form = ttk.Frame(parent, style="Card.TFrame")
        form.pack(anchor="nw", fill=X, pady=(0, 8))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Altitude above sea level, m").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(form, textvariable=self.altitude_m, width=12).grid(row=0, column=1, sticky="w", padx=(0, 24), pady=4)
        ttk.Label(form, text="Default: 5500 m; IPC external class changes above 3050 m").grid(
            row=0, column=2, sticky="w", padx=(0, 8), pady=4
        )

        ttk.Label(form, text="Export").grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=(8, 4))
        export_options = ttk.Frame(form, style="Card.TFrame")
        export_options.grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 4))
        ttk.Checkbutton(
            export_options,
            text="Include IPC-2221A max voltage V in exported files",
            variable=self.export_ipc2221a_max_voltage,
        ).pack(side=LEFT, padx=(0, 18))

        button_row = ttk.Frame(parent, style="Card.TFrame")
        button_row.pack(fill=X, pady=(0, 8))
        ttk.Button(button_row, text="Read ODB++", style="Primary.TButton", command=self._read_odb_metadata).pack(side=LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Auto-detect layer roles", command=self._auto_detect_layer_roles).pack(side=LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Set selected external", command=lambda: self._set_selected_layer_role("external")).pack(side=LEFT, padx=(0, 8))
        ttk.Button(button_row, text="Set selected internal", command=lambda: self._set_selected_layer_role("internal")).pack(side=LEFT, padx=(0, 8))
        ttk.Button(
            button_row,
            text="Recalculate voltage columns",
            command=self._recalculate_voltage_columns,
        ).pack(side=LEFT, padx=(0, 8))

        ttk.Label(
            parent,
            text="Double-click a layer row to toggle internal/external. Select multiple rows to change them together.",
            wraplength=1050,
            style="Muted.TLabel",
        ).pack(anchor="w", fill=X, pady=(0, 6))

        columns = ("order", "layer", "role", "ipc_class", "reason")
        self.layer_role_tree = self._make_tree_with_scrollbars(parent, columns)
        headings = {
            "order": "#",
            "layer": "Layer",
            "role": "Role",
            "ipc_class": "IPC-2221A class",
            "reason": "Default/override reason",
        }
        widths = {"order": 50, "layer": 260, "role": 100, "ipc_class": 260, "reason": 560}
        for col in columns:
            self.layer_role_tree.heading(col, text=headings[col])
            self.layer_role_tree.column(col, width=widths[col], anchor="w")
        self._install_tree_sorting(self.layer_role_tree, numeric_columns={"order"})
        self.layer_role_tree.bind("<Double-1>", lambda _event: self._toggle_selected_layer_role())
        self._refresh_layer_role_tree()


    def _default_iec_pollution_degree_for_layer(self, layer: str) -> tuple[int, str]:
        """Return default IEC pollution degree and reason for a layer."""

        role = normalize_layer_role(self.layer_roles.get(layer, "external"))
        if role == "internal":
            return 1, "auto: internal layer → PD1"
        if bool(self.external_conformal_coating.get()):
            return 2, "auto: external conformal coating → PD2"
        try:
            pd = int(float(self.pollution_degree.get()))
        except Exception:
            pd = 2
        pd = min(4, max(1, pd))
        return pd, f"auto: external layer → base PD{pd}"

    def _apply_auto_iec_pollution_degrees(self, layers: list[str] | None = None) -> None:
        """Auto-assign IEC layer pollution degrees from layer roles."""

        if layers is None:
            layers = self._current_signal_layers()
        self.iec_layer_pollution_degrees = {}
        self.iec_layer_reasons = {}
        for layer in layers:
            pd, reason = self._default_iec_pollution_degree_for_layer(layer)
            self.iec_layer_pollution_degrees[layer] = pd
            self.iec_layer_reasons[layer] = reason

    def _current_signal_layers(self) -> list[str]:
        """Return layers from the latest result/metadata/role table."""

        if self.last_result is not None:
            return list(self.last_result.job.signal_layers)
        if self.last_metadata_job is not None:
            return list(self.last_metadata_job.signal_layers)
        if self.layer_roles:
            return list(self.layer_roles.keys())
        return []

    def _refresh_iec_layer_tree(self) -> None:
        """Refresh IEC 60664-1 per-layer pollution-degree table."""

        tree = self.iec_layer_tree
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)

        layers = self._current_signal_layers()
        if not layers:
            tree.insert("", END, values=("", "Read ODB++ to populate layer table", "", "", "", "No ODB++ metadata loaded yet"))
            return

        try:
            particle = max(0.0, float(self.metallic_particle_size_mm.get()))
        except Exception:
            particle = 0.0

        for idx, layer in enumerate(layers, start=1):
            role = normalize_layer_role(self.layer_roles.get(layer, "external"))
            if layer not in self.iec_layer_pollution_degrees:
                pd, reason = self._default_iec_pollution_degree_for_layer(layer)
                self.iec_layer_pollution_degrees[layer] = pd
                self.iec_layer_reasons[layer] = reason
            pd = min(4, max(1, int(self.iec_layer_pollution_degrees.get(layer, 2))))
            self.iec_layer_pollution_degrees[layer] = pd
            reason = self.iec_layer_reasons.get(layer, "manual/default")
            particle_text = f"{particle:.6g}" if role == "external" else "0"
            tree.insert(
                "",
                END,
                iid=f"iec-layer-{idx-1}",
                values=(idx, layer, role, pd, particle_text, reason),
            )

    def _selected_iec_layer_names(self) -> list[str]:
        """Return selected layer names from IEC table."""

        tree = self.iec_layer_tree
        if tree is None:
            return []
        layers: list[str] = []
        for iid in tree.selection():
            values = tree.item(iid, "values")
            if len(values) >= 2:
                layers.append(str(values[1]))
        return layers

    def _set_selected_iec_pollution_degree(self, pd: int) -> None:
        """Set selected IEC rows to PD1..PD4."""

        selected_layers = self._selected_iec_layer_names()
        if not selected_layers:
            messagebox.showinfo("IEC 60664-1", "Select one or more IEC layer rows first.")
            return
        pd = min(4, max(1, int(pd)))
        for layer in selected_layers:
            self.iec_layer_pollution_degrees[layer] = pd
            self.iec_layer_reasons[layer] = "user override"
        self._refresh_iec_layer_tree()
        self._append_log(f"Set {len(selected_layers)} IEC layer(s) to PD{pd}.")

    def _cycle_selected_iec_pollution_degree(self) -> None:
        """Cycle selected rows through PD1..PD4 on double click."""

        selected_layers = self._selected_iec_layer_names()
        if not selected_layers:
            return
        for layer in selected_layers:
            current = min(4, max(1, int(self.iec_layer_pollution_degrees.get(layer, 2))))
            self.iec_layer_pollution_degrees[layer] = 1 if current >= 4 else current + 1
            self.iec_layer_reasons[layer] = "user override"
        self._refresh_iec_layer_tree()

    def _auto_assign_iec_pollution_degrees(self) -> None:
        """Re-apply IEC pollution-degree defaults."""

        layers = self._current_signal_layers()
        if not layers:
            if self.odb_path.get().strip():
                self._read_odb_metadata()
            else:
                messagebox.showinfo("IEC 60664-1", "Read an ODB++ file first.")
            return
        self._apply_auto_iec_pollution_degrees(layers)
        self._refresh_iec_layer_tree()
        self._append_log("IEC 60664-1 pollution degrees auto-assigned from layer role, conformal coating and base pollution degree.")

    def _on_external_conformal_changed(self) -> None:
        """Apply conformal-coating rule to external IEC layers."""

        if self.external_conformal_coating.get():
            layers = self._current_signal_layers()
            for layer in layers:
                if normalize_layer_role(self.layer_roles.get(layer, "external")) == "external":
                    self.iec_layer_pollution_degrees[layer] = 2
                    self.iec_layer_reasons[layer] = "auto: conformal coating → PD2"
        self._refresh_iec_layer_tree()
        self._update_voltage_settings_preview()

    def _iec_pollution_degree_for_layer(self, layer: str) -> int:
        """Return selected IEC pollution degree for one layer."""

        if layer not in self.iec_layer_pollution_degrees:
            pd, reason = self._default_iec_pollution_degree_for_layer(layer)
            self.iec_layer_pollution_degrees[layer] = pd
            self.iec_layer_reasons[layer] = reason
        try:
            return min(4, max(1, int(self.iec_layer_pollution_degrees.get(layer, 2))))
        except Exception:
            return 2

    def _iec_effective_spacing_for_layer(self, layer: str, spacing_mm: float) -> float:
        """Apply metallic-particle correction for external layers."""

        spacing = max(0.0, float(spacing_mm))
        if normalize_layer_role(self.layer_roles.get(layer, "external")) == "internal":
            return spacing
        try:
            particle = max(0.0, float(self.metallic_particle_size_mm.get()))
        except Exception:
            particle = 0.0
        return max(0.0, spacing - particle)

    def _format_size_from_bounds(self, bounds) -> str:
        """Return compact board size text from bounds."""

        if bounds is None:
            return "size N/A"
        try:
            minx, miny, maxx, maxy = bounds
            return f"{maxx - minx:.1f}×{maxy - miny:.1f} mm"
        except Exception:
            return "size N/A"

    def _set_header_stats_from_job(self, job) -> None:
        """Update compact header statistics from ODB++ metadata."""

        outline = getattr(job, "pcb_outline_source", None) or "outline N/A"
        size = self._format_size_from_bounds(self._job_bounds(job))
        self.header_stats.set(
            f"Layers {len(getattr(job, 'signal_layers', []))} | "
            f"Nets {len(getattr(job, 'nets_by_number', {}))} | "
            f"{size} | {outline}"
        )

    def _set_header_stats_from_result(self, result: AnalysisResult) -> None:
        """Update compact header statistics from an analysis result."""

        minimum = result.minimum_clearance_mm
        min_text = "min N/A" if minimum is None else f"min {minimum:.4f} mm"
        self.header_stats.set(
            f"Layers {len(result.job.signal_layers)} | Nets {len(result.job.nets_by_number)} | "
            f"Pairs {result.measurement_count} | Critical {result.critical_count} | "
            f"{min_text} | threshold {result.config.threshold_mm:g} mm"
        )

    def _read_odb_metadata(self) -> None:
        """Read ODB++ metadata without running the full clearance report."""

        if not self.odb_path.get().strip():
            messagebox.showwarning("Missing input", "Select an ODB++ archive or folder first.")
            return

        self.status.set("Reading ODB++ metadata...")
        self.progress.start(10)
        parser = OdbParser(progress=lambda msg: self._append_log(str(msg)))
        try:
            job = parser.parse(Path(self.odb_path.get()))
            self.last_metadata_job = job
            self._apply_auto_layer_roles(job.signal_layers)
            self._apply_auto_iec_pollution_degrees(job.signal_layers)
            self._show_metadata_summary(job)
            self._set_header_stats_from_job(job)
            self._refresh_layer_role_tree()
            self._refresh_iec_layer_tree()
            self.status.set("ODB++ metadata read")
            self._append_log(
                f"Read ODB++ metadata: {len(job.signal_layers)} signal layer(s), "
                f"{len(job.nets_by_number)} net(s)"
            )
        except Exception as exc:
            self.status.set("ODB++ metadata read failed")
            self._append_log(f"Metadata read failed: {exc}")
            messagebox.showerror("Read ODB++ failed", str(exc))
        finally:
            parser.close()
            self.progress.stop()

    def _apply_auto_layer_roles(self, layers: list[str]) -> None:
        """Guess and store layer roles for the IPC-2221A tab."""

        self.layer_roles = {}
        self.layer_role_reasons = {}
        for index, layer in enumerate(layers):
            role, reason = guess_layer_role(layer, index=index, total=len(layers))
            self.layer_roles[layer] = role
            self.layer_role_reasons[layer] = reason

    def _auto_detect_layer_roles(self) -> None:
        """Re-apply layer-role heuristics from the current metadata/result."""

        layers: list[str] = []
        if self.last_result is not None:
            layers = list(self.last_result.job.signal_layers)
        elif self.last_metadata_job is not None:
            layers = list(self.last_metadata_job.signal_layers)

        if not layers:
            if self.odb_path.get().strip():
                self._read_odb_metadata()
            else:
                messagebox.showinfo("IPC-2221A", "Read an ODB++ file first.")
            return

        self._apply_auto_layer_roles(layers)
        self._apply_auto_iec_pollution_degrees(layers)
        self._refresh_layer_role_tree()
        self._refresh_iec_layer_tree()
        self._append_log("Layer roles and IEC pollution degrees auto-detected from layer names and stack order.")

    def _refresh_layer_role_tree(self) -> None:
        """Refresh the layer assignment table in the IPC-2221A tab."""

        tree = self.layer_role_tree
        if tree is None:
            return
        for item in tree.get_children():
            tree.delete(item)

        layers = []
        if self.last_result is not None:
            layers = list(self.last_result.job.signal_layers)
        elif self.last_metadata_job is not None:
            layers = list(self.last_metadata_job.signal_layers)
        elif self.layer_roles:
            layers = list(self.layer_roles.keys())

        for idx, layer in enumerate(layers, start=1):
            role = normalize_layer_role(self.layer_roles.get(layer, "external"))
            self.layer_roles[layer] = role
            reason = self.layer_role_reasons.get(layer, "manual/default")
            tree.insert(
                "",
                END,
                iid=f"layerrole-{idx-1}",
                values=(
                    idx,
                    layer,
                    role,
                    ipc2221a_settings_text(role, altitude_m=float(self.altitude_m.get() or 0.0)),
                    reason,
                ),
            )

    def _selected_layer_names(self) -> list[str]:
        """Return selected layer names from the Settings tab role table."""

        tree = self.layer_role_tree
        if tree is None:
            return []
        layers: list[str] = []
        for iid in tree.selection():
            values = tree.item(iid, "values")
            if len(values) >= 2:
                layers.append(str(values[1]))
        return layers

    def _set_selected_layer_role(self, role: str) -> None:
        """Set selected layer rows to internal/external."""

        selected_layers = self._selected_layer_names()
        if not selected_layers:
            messagebox.showinfo("IPC-2221A", "Select one or more layer rows first.")
            return
        role = normalize_layer_role(role)
        for layer in selected_layers:
            self.layer_roles[layer] = role
            self.layer_role_reasons[layer] = "user override"
        for layer in selected_layers:
            if self.iec_layer_reasons.get(layer, "").startswith("auto") or layer not in self.iec_layer_pollution_degrees:
                pd, reason = self._default_iec_pollution_degree_for_layer(layer)
                self.iec_layer_pollution_degrees[layer] = pd
                self.iec_layer_reasons[layer] = reason
        self._refresh_layer_role_tree()
        self._refresh_iec_layer_tree()
        self._append_log(f"Set {len(selected_layers)} layer(s) to {role}.")

    def _toggle_selected_layer_role(self) -> None:
        """Toggle selected layer role on double-click."""

        selected_layers = self._selected_layer_names()
        if not selected_layers:
            return
        for layer in selected_layers:
            current = normalize_layer_role(self.layer_roles.get(layer, "external"))
            self.layer_roles[layer] = "internal" if current == "external" else "external"
            self.layer_role_reasons[layer] = "user override"
            if self.iec_layer_reasons.get(layer, "").startswith("auto") or layer not in self.iec_layer_pollution_degrees:
                pd, reason = self._default_iec_pollution_degree_for_layer(layer)
                self.iec_layer_pollution_degrees[layer] = pd
                self.iec_layer_reasons[layer] = reason
        self._refresh_layer_role_tree()
        self._refresh_iec_layer_tree()

    def _show_metadata_summary(self, job) -> None:
        """Display ODB++ metadata in the Summary tab."""

        try:
            for item in self.summary_text.get_children():
                self.summary_text.delete(item)
        except Exception:
            pass

        bounds = self._job_bounds(job)
        if bounds is None:
            size_text = "N/A"
        else:
            minx, miny, maxx, maxy = bounds
            size_text = (
                f"{maxx - minx:.3f} × {maxy - miny:.3f} mm "
                f"(bbox x={minx:.3f}..{maxx:.3f}, y={miny:.3f}..{maxy:.3f})"
            )

        rows = [
            ("ODB++ source", job.source_path.name if job.source_path else str(job.root)),
            ("Step", job.step_name),
            ("Signal layer count", str(len(job.signal_layers))),
            ("Signal layers", ", ".join(job.signal_layers)),
            ("Approx PCB size", size_text),
            ("PCB outline source", getattr(job, "pcb_outline_source", None) or "Not found"),
            ("Nets in EDA data", str(len(job.nets_by_number))),
            ("Plated drill layers", ", ".join(layer.name for layer in getattr(job, "drill_layers", [])) or "None"),
            ("Layer role defaults", ", ".join(f"{layer}={self.layer_roles.get(layer, 'external')}" for layer in job.signal_layers)),
        ]

        matrix_rows = self._matrix_layer_rows(job)
        if matrix_rows:
            rows.append(("Stackup/matrix rows", str(len(matrix_rows))))
            for idx, row in enumerate(matrix_rows, start=1):
                rows.append((f"  {idx:02d}", row))

        for field, value in rows:
            idx = len(self.summary_text.get_children())
            self.summary_text.insert("", END, text=field, values=(value,), tags=("even" if idx % 2 == 0 else "odd",))

    def _job_bounds(self, job):
        """Return approximate bounding box, preferring parsed PCB outline/profile."""

        outline = getattr(job, "pcb_outline_geometry", None)
        if outline is not None and not getattr(outline, "is_empty", True):
            try:
                return tuple(float(v) for v in outline.bounds)
            except Exception:
                pass

        bounds = []
        for features in getattr(job, "features_by_layer", {}).values():
            for feature in features:
                geom = getattr(feature, "geometry", None)
                if geom is None or getattr(geom, "is_empty", True):
                    continue
                try:
                    bounds.append(tuple(float(v) for v in geom.bounds))
                except Exception:
                    continue
        if not bounds:
            return None
        minx = min(b[0] for b in bounds)
        miny = min(b[1] for b in bounds)
        maxx = max(b[2] for b in bounds)
        maxy = max(b[3] for b in bounds)
        return (minx, miny, maxx, maxy)

    def _matrix_layer_rows(self, job) -> list[str]:
        """Return readable ODB++ matrix/stackup rows when present."""

        path = Path(job.root) / "matrix" / "matrix"
        if not path.exists():
            return []
        text = path.read_text(errors="ignore")
        rows: list[str] = []
        for block in re.findall(r"LAYER\s*\{(.*?)\}", text, flags=re.IGNORECASE | re.S):
            props: dict[str, str] = {}
            for line in block.splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                props[key.strip().upper()] = value.strip()
            name = props.get("NAME", "")
            layer_type = props.get("TYPE", "")
            context = props.get("CONTEXT", "")
            side = props.get("SIDE", "")
            start = props.get("START_NAME", "")
            end = props.get("END_NAME", "")
            extras = []
            if context:
                extras.append(f"context={context}")
            if side:
                extras.append(f"side={side}")
            if start or end:
                extras.append(f"span={start}->{end}")
            rows.append(f"{name} ({layer_type}{'; ' + ', '.join(extras) if extras else ''})")
        return rows


    def _voltage_settings_values(self) -> tuple[float, int, float]:
        """Return sanitized CTI, pollution degree and altitude values from GUI fields."""

        try:
            cti = float(self.cti.get())
        except Exception:
            cti = 175.0
            self.cti.set(cti)
        try:
            pd = int(float(self.pollution_degree.get()))
        except Exception:
            pd = 2
            self.pollution_degree.set("2")
        pd = min(4, max(1, pd))
        try:
            altitude = float(self.altitude_m.get())
        except Exception:
            altitude = 5500.0
            self.altitude_m.set(altitude)
        altitude = max(0.0, altitude)
        return cti, pd, altitude

    def _update_voltage_settings_preview(self) -> None:
        """Update the material group/settings preview text."""

        try:
            cti, pd, altitude = self._voltage_settings_values()
            particle = float(self.metallic_particle_size_mm.get()) if str(self.metallic_particle_size_mm.get()).strip() else 0.0
            coating = "yes" if self.external_conformal_coating.get() else "no"
            self.material_group_preview.set(
                voltage_settings_summary(cti, pd, altitude)
                + f", external conformal coating={coating}, metallic particle size={particle:g} mm"
            )
            self._refresh_layer_role_tree()
            self._refresh_iec_layer_tree()
        except Exception:
            self.material_group_preview.set("Invalid voltage settings")

    def _recalculate_voltage_columns(self) -> None:
        """Recalculate effective max-voltage columns for the already displayed result."""

        if self.last_result is None:
            self._update_voltage_settings_preview()
            messagebox.showinfo("Voltage settings", "Run an analysis first, then recalculate voltage columns.")
            return

        cti, pd, altitude = self._voltage_settings_values()

        measurements = [
            replace(
                rec,
                effective_max_voltage_v=estimate_effective_max_voltage(
                    self._iec_effective_spacing_for_layer(rec.layer, rec.clearance_mm),
                    cti=cti,
                    pollution_degree=self._iec_pollution_degree_for_layer(rec.layer),
                    altitude_m=altitude,
                ),
                ipc2221a_max_voltage_v=estimate_ipc2221a_max_voltage(
                    rec.clearance_mm,
                    layer_role=self.layer_roles.get(rec.layer, "external"),
                    altitude_m=altitude,
                ),
            )
            for rec in self.last_result.measurements
        ]
        critical = [
            replace(
                rec,
                effective_max_voltage_v=estimate_effective_max_voltage(
                    self._iec_effective_spacing_for_layer(rec.layer, rec.clearance_mm),
                    cti=cti,
                    pollution_degree=self._iec_pollution_degree_for_layer(rec.layer),
                    altitude_m=altitude,
                ),
                ipc2221a_max_voltage_v=estimate_ipc2221a_max_voltage(
                    rec.clearance_mm,
                    layer_role=self.layer_roles.get(rec.layer, "external"),
                    altitude_m=altitude,
                ),
            )
            for rec in self.last_result.critical_measurements
        ]

        per_net = self._build_per_net_minimum_for_gui(measurements)

        airgap = [
            replace(
                rec,
                effective_max_voltage_v=estimate_effective_max_voltage(
                    self._iec_effective_spacing_for_layer(rec.layer, rec.effective_air_gap_mm),
                    cti=cti,
                    pollution_degree=self._iec_pollution_degree_for_layer(rec.layer),
                    altitude_m=altitude,
                ),
                ipc2221a_max_voltage_v=estimate_ipc2221a_max_voltage(
                    rec.effective_air_gap_mm,
                    layer_role=self.layer_roles.get(rec.layer, "external"),
                    altitude_m=altitude,
                ),
            )
            for rec in self.last_result.effective_air_gap_records
        ]

        self.last_result.config.cti = cti
        self.last_result.config.pollution_degree = pd
        self.last_result.config.altitude_m = altitude
        self.last_result.config.layer_roles = dict(self.layer_roles)
        self.last_result.config.layer_pollution_degrees = dict(self.iec_layer_pollution_degrees)
        self.last_result.config.external_conformal_coating = bool(self.external_conformal_coating.get())
        self.last_result.config.metallic_particle_size_mm = max(0.0, float(self.metallic_particle_size_mm.get()))
        self.last_result.config.export_effective_max_voltage = bool(self.export_effective_max_voltage.get())
        self.last_result.config.export_ipc2221a_max_voltage = bool(self.export_ipc2221a_max_voltage.get())
        self.last_result.measurements = measurements
        self.last_result.critical_measurements = critical
        self.last_result.per_net_minimum = per_net
        self.last_result.effective_air_gap_records = airgap

        for tree in (self.critical_tree, self.per_net_tree, self.airgap_tree):
            for item in tree.get_children():
                tree.delete(item)
        self._fill_critical_table(self.last_result.critical_measurements[:1000])
        self._fill_per_net_table(self.last_result.per_net_minimum[:1000])
        self._fill_airgap_table(self.last_result.effective_air_gap_records[:1000])
        self._update_voltage_settings_preview()
        self.status.set("Voltage columns recalculated using current IEC 60664-1 / IPC-2221A tab values")
        self._append_log("Voltage columns recalculated in GUI. Re-run analysis to regenerate CSV/XLSX/Markdown files with these settings.")

    def _build_per_net_minimum_for_gui(self, measurements: list[MeasurementRecord]) -> list[PerNetMinimum]:
        """Build per-net minimum rows in the GUI after voltage-only recalculation."""

        best: dict[str, PerNetMinimum] = {}
        for rec in measurements:
            candidate_a = PerNetMinimum(
                net=rec.net_a,
                min_clearance_mm=rec.clearance_mm,
                layer=rec.layer,
                other_net=rec.net_b,
                x_this_mm=rec.x_a_mm,
                y_this_mm=rec.y_a_mm,
                x_other_mm=rec.x_b_mm,
                y_other_mm=rec.y_b_mm,
                effective_max_voltage_v=rec.effective_max_voltage_v,
                ipc2221a_max_voltage_v=rec.ipc2221a_max_voltage_v,
            )
            candidate_b = PerNetMinimum(
                net=rec.net_b,
                min_clearance_mm=rec.clearance_mm,
                layer=rec.layer,
                other_net=rec.net_a,
                x_this_mm=rec.x_b_mm,
                y_this_mm=rec.y_b_mm,
                x_other_mm=rec.x_a_mm,
                y_other_mm=rec.y_a_mm,
                effective_max_voltage_v=rec.effective_max_voltage_v,
                ipc2221a_max_voltage_v=rec.ipc2221a_max_voltage_v,
            )
            for candidate in (candidate_a, candidate_b):
                current = best.get(candidate.net)
                if current is None or candidate.min_clearance_mm < current.min_clearance_mm:
                    best[candidate.net] = candidate
        return sorted(best.values(), key=lambda item: (item.min_clearance_mm, item.net))


    def _create_measurement_tree(self, parent) -> ttk.Treeview:
        topbar = ttk.Frame(parent, style="Card.TFrame")
        topbar.pack(fill=X, pady=(0, 6))
        ttk.Label(topbar, text="Double-click a row or click View geometry to inspect reconstructed copper.").pack(side=LEFT)
        ttk.Button(topbar, text="View selected geometry", command=self._open_selected_critical_geometry).pack(side=RIGHT)

        columns = ("layer", "net_a", "net_b", "clearance", "max_voltage", "ipc_voltage", "point_a", "point_b")
        tree = self._make_tree_with_scrollbars(parent, columns)
        headings = {
            "layer": "Layer",
            "net_a": "Net A",
            "net_b": "Net B",
            "clearance": "Clearance mm",
            "max_voltage": "Effective max voltage V",
            "ipc_voltage": "IPC-2221A max voltage V",
            "point_a": "Point A mm",
            "point_b": "Point B mm",
        }
        widths = {"layer": 80, "net_a": 230, "net_b": 230, "clearance": 110, "max_voltage": 170, "ipc_voltage": 180, "point_a": 130, "point_b": 130}
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w")
        self._install_tree_sorting(tree, numeric_columns={"clearance", "max_voltage", "ipc_voltage", "point_a", "point_b"})
        tree.bind("<Double-1>", lambda _event: self._open_selected_critical_geometry())
        return tree

    def _create_per_net_tree(self, parent) -> ttk.Treeview:
        topbar = ttk.Frame(parent, style="Card.TFrame")
        topbar.pack(fill=X, pady=(0, 6))
        ttk.Label(topbar, text="Shows each net's worst clearance. Double-click a row or click View geometry.").pack(side=LEFT)
        ttk.Button(topbar, text="View selected geometry", command=self._open_selected_per_net_geometry).pack(side=RIGHT)

        columns = ("net", "clearance", "max_voltage", "ipc_voltage", "layer", "other", "point_this", "point_other")
        tree = self._make_tree_with_scrollbars(parent, columns)
        headings = {
            "net": "Net",
            "clearance": "Minimum mm",
            "max_voltage": "Effective max voltage V",
            "ipc_voltage": "IPC-2221A max voltage V",
            "layer": "Layer",
            "other": "Other net",
            "point_this": "This point mm",
            "point_other": "Other point mm",
        }
        widths = {"net": 230, "clearance": 110, "max_voltage": 170, "ipc_voltage": 180, "layer": 80, "other": 230, "point_this": 130, "point_other": 130}
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w")
        self._install_tree_sorting(tree, numeric_columns={"clearance", "max_voltage", "ipc_voltage", "point_this", "point_other"})
        tree.bind("<Double-1>", lambda _event: self._open_selected_per_net_geometry())
        return tree

    def _create_feature_attr_tree(self, parent) -> ttk.Treeview:
        columns = ("layer", "feature", "net", "kind", "symbol", "raw", "decoded")
        tree = self._make_tree_with_scrollbars(parent, columns)
        headings = {
            "layer": "Layer",
            "feature": "Feature #",
            "net": "Net",
            "kind": "Kind",
            "symbol": "Symbol",
            "raw": "Raw attributes",
            "decoded": "Decoded attributes",
        }
        widths = {
            "layer": 80,
            "feature": 90,
            "net": 220,
            "kind": 70,
            "symbol": 180,
            "raw": 160,
            "decoded": 360,
        }
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w")
        self._install_tree_sorting(tree, numeric_columns={"feature"})
        return tree

    def _create_debug_tree(self, parent) -> ttk.Treeview:
        topbar = ttk.Frame(parent, style="Card.TFrame")
        topbar.pack(fill=X, pady=(0, 6))
        ttk.Label(
            topbar,
            text="Shows source features and geometry relation for critical pairs. Double-click a row for full details.",
        ).pack(side=LEFT)
        ttk.Button(topbar, text="Open selected details", command=self._open_selected_debug_details).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(topbar, text="View selected geometry", command=self._open_selected_debug_geometry).pack(side=RIGHT)

        columns = (
            "layer",
            "net_a",
            "net_b",
            "clearance",
            "relation",
            "zero_kind",
            "area",
            "hits_a",
            "hits_b",
            "negative",
            "notes",
        )
        tree = self._make_tree_with_scrollbars(parent, columns)
        headings = {
            "layer": "Layer",
            "net_a": "Net A",
            "net_b": "Net B",
            "clearance": "Clearance mm",
            "relation": "Relation",
            "zero_kind": "Zero kind",
            "area": "Overlap area mm²",
            "hits_a": "Source hits A",
            "hits_b": "Source hits B",
            "negative": "Cutouts near point",
            "notes": "Notes",
        }
        widths = {
            "layer": 80,
            "net_a": 160,
            "net_b": 160,
            "clearance": 110,
            "relation": 100,
            "zero_kind": 130,
            "area": 130,
            "hits_a": 280,
            "hits_b": 280,
            "negative": 280,
            "notes": 450,
        }
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w")
        self._install_tree_sorting(tree, numeric_columns={"clearance", "area"})
        tree.bind("<Double-1>", lambda _event: self._open_selected_debug_details())
        return tree


    def _create_airgap_tree(self, parent) -> ttk.Treeview:
        topbar = ttk.Frame(parent, style="Card.TFrame")
        topbar.pack(fill=X, pady=(0, 6))
        ttk.Label(
            topbar,
            text=(
                "Optional full matrix. It subtracts copper occupied by intermediate nets "
                "along the closest-point line and sums only non-copper gaps."
            ),
        ).pack(side=LEFT)
        ttk.Button(topbar, text="View selected geometry", command=self._open_selected_airgap_geometry).pack(side=RIGHT)

        columns = ("layer", "net_a", "net_b", "direct", "effective", "max_voltage", "ipc_voltage", "blocked", "copper", "blockers", "point_a", "point_b")
        tree = self._make_tree_with_scrollbars(parent, columns)
        headings = {
            "layer": "Layer",
            "net_a": "Net A",
            "net_b": "Net B",
            "direct": "Direct mm",
            "effective": "Effective Net-to-Net distance mm",
            "max_voltage": "Effective max voltage V",
            "ipc_voltage": "IPC-2221A max voltage V",
            "blocked": "Copper blocked mm",
            "copper": "Copper on path",
            "blockers": "Blocker nets",
            "point_a": "Point A mm",
            "point_b": "Point B mm",
        }
        widths = {
            "layer": 90,
            "net_a": 190,
            "net_b": 190,
            "direct": 110,
            "effective": 190,
            "max_voltage": 170,
            "ipc_voltage": 180,
            "blocked": 130,
            "copper": 120,
            "blockers": 320,
            "point_a": 130,
            "point_b": 130,
        }
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w")
        self._install_tree_sorting(tree, numeric_columns={"direct", "effective", "max_voltage", "ipc_voltage", "blocked", "point_a", "point_b"})
        tree.bind("<Double-1>", lambda _event: self._open_selected_airgap_geometry())
        return tree

    def _browse_odb(self) -> None:
        path = filedialog.askopenfilename(
            title="Select ODB++ archive",
            filetypes=[("ODB++ archives", "*.zip *.tgz *.tar.gz *.tar"), ("ZIP archives", "*.zip"), ("TGZ archives", "*.tgz *.tar.gz"), ("All files", "*.*")],
        )
        if path:
            self.odb_path.set(path)
            default_out = Path(path).with_suffix("").name + "_clearance_report"
            self.output_dir.set(str(Path(path).parent / default_out))

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir.set(path)

    def _start_analysis(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Analysis running", "Analysis is already running.")
            return
        if not self.odb_path.get().strip():
            messagebox.showwarning("Missing input", "Select an ODB++ archive or folder first.")
            return
        self.cancel_event.clear()
        self._clear_views()
        self.header_stats.set("Analysis running…")
        self.progress.start(10)
        self._set_running_state(True)
        self.status.set("Starting analysis...")

        config = self._current_analysis_config()

        self.worker = threading.Thread(target=self._worker_main, args=(config,), daemon=True)
        self.worker.start()

    def _stop_analysis(self) -> None:
        """Request cooperative cancellation of the running analysis."""

        if not (self.worker and self.worker.is_alive()):
            return
        self.cancel_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("Stopping analysis after the current geometry step...")
        self.header_stats.set("Stopping…")
        self._append_log("Stop requested. Waiting for analyzer to reach a safe cancellation point.")

    def _set_running_state(self, running: bool) -> None:
        """Enable/disable run and stop controls consistently."""

        self.run_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def _worker_main(self, config: AnalysisConfig) -> None:
        try:
            analyzer = ClearanceAnalyzer(
                progress=lambda msg: self.queue.put(("log", msg)),
                cancel_check=self.cancel_event.is_set,
            )
            result = analyzer.run(config)
            self.queue.put(("result", result))
        except AnalysisCancelled as exc:
            self.queue.put(("cancelled", str(exc)))
        except Exception as exc:
            self.queue.put(("error", f"{exc}\n\n{traceback.format_exc()}"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                    self.status.set(str(payload))
                elif kind == "result":
                    self._show_result(payload)  # type: ignore[arg-type]
                    self.progress.stop()
                    self._set_running_state(False)
                    self.status.set("Analysis completed")
                elif kind == "cancelled":
                    self.progress.stop()
                    self._set_running_state(False)
                    self.status.set("Analysis stopped")
                    self.header_stats.set("Analysis stopped")
                    self._append_log(str(payload) or "Analysis stopped by user.")
                elif kind == "error":
                    self.progress.stop()
                    self._set_running_state(False)
                    self.status.set("Analysis failed")
                    self.header_stats.set("Analysis failed")
                    self._append_log(str(payload))
                    messagebox.showerror("Analysis failed", str(payload))
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _append_log(self, message: str) -> None:
        idx = len(self.log.get_children())
        self.log.insert("", END, values=(message,), tags=("even" if idx % 2 == 0 else "odd",))
        children = self.log.get_children()
        if children:
            self.log.see(children[-1])

    def _show_result(self, result: AnalysisResult) -> None:
        self.last_result = result
        if result.config.layer_roles:
            self.layer_roles = dict(result.config.layer_roles)
            for layer, role in self.layer_roles.items():
                self.layer_role_reasons.setdefault(layer, "analysis/default")
            self._refresh_layer_role_tree()
        if result.config.layer_pollution_degrees:
            self.iec_layer_pollution_degrees = dict(result.config.layer_pollution_degrees)
            for layer in self.iec_layer_pollution_degrees:
                self.iec_layer_reasons.setdefault(layer, "analysis/default")
            self._refresh_iec_layer_tree()
        self.external_conformal_coating.set(bool(result.config.external_conformal_coating))
        self.metallic_particle_size_mm.set(float(result.config.metallic_particle_size_mm))
        self.export_effective_max_voltage.set(bool(result.config.export_effective_max_voltage))
        self.export_ipc2221a_max_voltage.set(bool(result.config.export_ipc2221a_max_voltage))
        self._set_header_stats_from_result(result)
        minimum = result.minimum_clearance_mm
        summary = [
            ("ODB++ source", result.job.source_path.name if result.job.source_path else str(result.job.root)),
            ("Step", result.job.step_name),
            ("Layers", ", ".join(result.job.signal_layers)),
            ("Measured pairs", str(result.measurement_count)),
            ("Critical below threshold", str(result.critical_count)),
            ("Minimum clearance", "N/A" if minimum is None else f"{minimum:.6f} mm"),
            ("PCB outline source", getattr(result.job, "pcb_outline_source", None) or "Not found"),
            ("IEC 60664-1 settings", voltage_settings_summary(result.config.cti, result.config.pollution_degree, result.config.altitude_m)),
            ("IEC layer pollution degrees", ", ".join(f"{layer}=PD{pd}" for layer, pd in result.config.layer_pollution_degrees.items())),
            ("External conformal coating", str(result.config.external_conformal_coating)),
            ("Metallic particle size", f"{result.config.metallic_particle_size_mm:g} mm"),
            ("IPC-2221A layer roles", ", ".join(f"{layer}={role}" for layer, role in result.config.layer_roles.items())),
            ("Export Effective max voltage V", str(result.config.export_effective_max_voltage)),
            ("Export IPC-2221A max voltage V", str(result.config.export_ipc2221a_max_voltage)),
            ("Decoded feature attribute rows", str(result.feature_attribute_count)),
            ("Geometry debug rows", str(len(result.geometry_debug_records))),
            ("Effective Net-to-Net distance rows", str(len(result.effective_air_gap_records))),
            ("Output folder", str(result.config.output_dir)),
        ]
        for field, value in summary:
            idx = len(self.summary_text.get_children())
            self.summary_text.insert("", END, text=field, values=(value,), tags=("even" if idx % 2 == 0 else "odd",))
        idx = len(self.summary_text.get_children())
        self.summary_text.insert("", END, text="Reports", values=("",), tags=("even" if idx % 2 == 0 else "odd",))
        for name, path in result.report_files.items():
            idx = len(self.summary_text.get_children())
            self.summary_text.insert("", END, text=f"  {name}", values=(str(path),), tags=("even" if idx % 2 == 0 else "odd",))

        self._fill_critical_table(result.critical_measurements[:1000])
        self._fill_per_net_table(result.per_net_minimum[:1000])
        self._fill_feature_attr_table(list(result.job.iter_feature_attributes(include_empty=False))[:1000])
        self._fill_debug_table(result.geometry_debug_records[:1000])
        self._fill_airgap_table(result.effective_air_gap_records[:1000])

    def _fill_critical_table(self, records: list[MeasurementRecord]) -> None:
        self.visible_critical_records = list(records)
        for idx, rec in enumerate(self.visible_critical_records):
            self.critical_tree.insert(
                "",
                END,
                iid=f"critical-{idx}",
                tags=(self._clearance_row_tag(rec.clearance_mm, idx),),
                values=(
                    rec.layer,
                    rec.net_a,
                    rec.net_b,
                    f"{rec.clearance_mm:.6f}",
                    self._fmt_voltage(rec.effective_max_voltage_v),
                    self._fmt_voltage(rec.ipc2221a_max_voltage_v),
                    self._fmt_point(rec.x_a_mm, rec.y_a_mm),
                    self._fmt_point(rec.x_b_mm, rec.y_b_mm),
                ),
            )

    def _fill_per_net_table(self, records: list[PerNetMinimum]) -> None:
        self.visible_per_net_records = list(records)
        for idx, rec in enumerate(self.visible_per_net_records):
            self.per_net_tree.insert(
                "",
                END,
                iid=f"pernet-{idx}",
                tags=(self._clearance_row_tag(rec.min_clearance_mm, idx),),
                values=(
                    rec.net,
                    f"{rec.min_clearance_mm:.6f}",
                    self._fmt_voltage(rec.effective_max_voltage_v),
                    self._fmt_voltage(rec.ipc2221a_max_voltage_v),
                    rec.layer,
                    rec.other_net,
                    self._fmt_point(rec.x_this_mm, rec.y_this_mm),
                    self._fmt_point(rec.x_other_mm, rec.y_other_mm),
                ),
            )

    def _fill_feature_attr_table(self, records) -> None:
        for idx, rec in enumerate(records):
            self.feature_attr_tree.insert(
                "",
                END,
                tags=("even" if idx % 2 == 0 else "odd",),
                values=(
                    rec.layer,
                    rec.feature_index,
                    rec.net,
                    rec.feature_kind,
                    rec.symbol_name or "",
                    rec.raw_attributes,
                    rec.decoded_attributes,
                ),
            )

    def _fill_debug_table(self, records) -> None:
        self.debug_records = list(records)
        for idx, rec in enumerate(self.debug_records):
            row = rec.as_row()
            area = "" if rec.intersection_area_mm2 is None else f"{rec.intersection_area_mm2:.9g}"
            self.debug_tree.insert(
                "",
                END,
                iid=str(idx),
                tags=(self._clearance_row_tag(rec.clearance_mm, idx),),
                values=(
                    rec.layer,
                    rec.net_a,
                    rec.net_b,
                    f"{rec.clearance_mm:.6f}",
                    rec.relation,
                    rec.zero_clearance_kind,
                    area,
                    row["feature_hits_a"],
                    row["feature_hits_b"],
                    row["negative_hits_near_point"],
                    rec.notes,
                ),
            )

    def _fill_airgap_table(self, records) -> None:
        self.visible_airgap_records = list(records)
        for idx, rec in enumerate(self.visible_airgap_records):
            tag = self._clearance_row_tag(rec.effective_air_gap_mm, idx, zero_is_critical=False) if bool(self.clearance_gradient.get()) else ("critical" if rec.copper_on_path else ("even" if idx % 2 == 0 else "odd"))
            self.airgap_tree.insert(
                "",
                END,
                iid=f"airgap-{idx}",
                tags=(tag,),
                values=(
                    rec.layer,
                    rec.net_a,
                    rec.net_b,
                    f"{rec.direct_clearance_mm:.6f}",
                    f"{rec.effective_air_gap_mm:.6f}",
                    self._fmt_voltage(rec.effective_max_voltage_v),
                    self._fmt_voltage(rec.ipc2221a_max_voltage_v),
                    f"{rec.copper_blocked_length_mm:.6f}",
                    str(rec.copper_on_path),
                    rec.blocker_nets,
                    self._fmt_point(rec.x_a_mm, rec.y_a_mm),
                    self._fmt_point(rec.x_b_mm, rec.y_b_mm),
                ),
            )

    def _fmt_voltage(self, value) -> str:
        if value is None:
            return ""
        try:
            return f"{float(value):.1f}"
        except Exception:
            return ""

    def _toggle_theme(self) -> None:
        dark = bool(self.dark_theme.get())
        install_material_theme(self.master, dark=dark)
        self.master.configure(bg=MATERIAL_COLORS["app_bg"])
        try:
            self.configure(style="App.TFrame")
        except Exception:
            pass
        for tree in (
            self.summary_text,
            self.log,
            self.critical_tree,
            self.per_net_tree,
            self.feature_attr_tree,
            self.debug_tree,
            self.airgap_tree,
        ):
            tag_tree_rows(tree)
        if self.layer_role_tree is not None:
            tag_tree_rows(self.layer_role_tree)
        if self.iec_layer_tree is not None:
            tag_tree_rows(self.iec_layer_tree)
        self._recolor_clearance_tables()



    def _open_geometry_viewer_overview(self) -> None:
        """Open a standalone geometry viewer after an analysis has been run."""

        if self.last_result is None:
            messagebox.showinfo("Geometry viewer", "Run an analysis first, then open the geometry viewer.")
            return
        GeometryViewer(self.master, self.last_result, dark_theme=bool(self.dark_theme.get()))

    def _open_selected_critical_geometry(self) -> None:
        """Open geometry viewer focused on the currently selected critical pair."""

        if self.last_result is None:
            messagebox.showinfo("Geometry viewer", "Run an analysis first.")
            return
        selection = self.critical_tree.selection()
        if not selection:
            messagebox.showinfo("Geometry viewer", "Select a critical pair first.")
            return
        try:
            idx = int(str(selection[0]).split("-")[-1])
            rec = self.visible_critical_records[idx]
        except Exception:
            messagebox.showerror("Geometry viewer", "Could not resolve the selected critical row.")
            return
        GeometryViewer(
            self.master,
            self.last_result,
            layer=rec.layer,
            net_a=rec.net_a,
            net_b=rec.net_b,
            point_a=self._point_tuple(rec.x_a_mm, rec.y_a_mm),
            point_b=self._point_tuple(rec.x_b_mm, rec.y_b_mm),
            dark_theme=bool(self.dark_theme.get()),
        )

    def _open_selected_per_net_geometry(self) -> None:
        """Open geometry viewer focused on the selected per-net minimum row."""

        if self.last_result is None:
            messagebox.showinfo("Geometry viewer", "Run an analysis first.")
            return
        selection = self.per_net_tree.selection()
        if not selection:
            messagebox.showinfo("Geometry viewer", "Select a per-net minimum row first.")
            return
        try:
            idx = int(str(selection[0]).split("-")[-1])
            rec = self.visible_per_net_records[idx]
        except Exception:
            messagebox.showerror("Geometry viewer", "Could not resolve the selected per-net row.")
            return
        GeometryViewer(
            self.master,
            self.last_result,
            layer=rec.layer,
            net_a=rec.net,
            net_b=rec.other_net,
            point_a=self._point_tuple(rec.x_this_mm, rec.y_this_mm),
            point_b=self._point_tuple(rec.x_other_mm, rec.y_other_mm),
            dark_theme=bool(self.dark_theme.get()),
        )

    def _open_selected_airgap_geometry(self) -> None:
        """Open geometry viewer focused on the selected Effective Net-to-Net distance row."""

        if self.last_result is None:
            messagebox.showinfo("Geometry viewer", "Run an analysis first.")
            return
        selection = self.airgap_tree.selection()
        if not selection:
            messagebox.showinfo("Geometry viewer", "Select an Effective Net-to-Net distance row first.")
            return
        try:
            idx = int(str(selection[0]).split("-")[-1])
            rec = self.visible_airgap_records[idx]
        except Exception:
            messagebox.showerror("Geometry viewer", "Could not resolve the selected Effective Net-to-Net distance row.")
            return
        GeometryViewer(
            self.master,
            self.last_result,
            layer=rec.layer,
            net_a=rec.net_a,
            net_b=rec.net_b,
            point_a=self._point_tuple(rec.x_a_mm, rec.y_a_mm),
            point_b=self._point_tuple(rec.x_b_mm, rec.y_b_mm),
            dark_theme=bool(self.dark_theme.get()),
        )

    def _open_selected_debug_geometry(self) -> None:
        """Open geometry viewer focused on the selected debug zero/overlap pair."""

        if self.last_result is None:
            messagebox.showinfo("Geometry viewer", "Run an analysis first.")
            return
        selection = self.debug_tree.selection()
        if not selection:
            messagebox.showinfo("Geometry viewer", "Select a debug row first.")
            return
        try:
            rec = self.debug_records[int(selection[0])]
        except Exception:
            messagebox.showerror("Geometry viewer", "Could not resolve the selected debug row.")
            return
        GeometryViewer(
            self.master,
            self.last_result,
            layer=rec.layer,
            net_a=rec.net_a,
            net_b=rec.net_b,
            point_a=self._point_tuple(rec.x_a_mm, rec.y_a_mm),
            point_b=self._point_tuple(rec.x_b_mm, rec.y_b_mm),
            dark_theme=bool(self.dark_theme.get()),
        )

    def _point_tuple(self, x: float | None, y: float | None) -> tuple[float, float] | None:
        if x is None or y is None:
            return None
        return (float(x), float(y))

    def _open_selected_debug_details(self) -> None:
        selection = self.debug_tree.selection()
        if not selection:
            messagebox.showinfo("Debug details", "Select a debug row first.")
            return
        try:
            rec = self.debug_records[int(selection[0])]
        except Exception:
            return

        win = Toplevel(self.master)
        install_material_theme(win, dark=bool(self.dark_theme.get()))
        win.configure(bg=MATERIAL_COLORS["app_bg"])
        win.title(f"Geometry debug: {rec.layer} {rec.net_a} ↔ {rec.net_b}")
        win.geometry("1050x720")
        text = Text(
            win,
            wrap="word",
            bg=MATERIAL_COLORS["surface"],
            fg=MATERIAL_COLORS["text"],
            insertbackground=MATERIAL_COLORS["primary"],
            relief="flat",
            padx=18,
            pady=18,
            font=("Cascadia Mono", 10),
        )
        yscroll = ttk.Scrollbar(win, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=yscroll.set)
        text.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll.pack(side=RIGHT, fill="y")
        text.insert(END, self._format_debug_details(rec))
        text.configure(state="disabled")

    def _format_debug_details(self, rec) -> str:
        def format_hits(title: str, hits) -> str:
            lines = [title]
            if not hits:
                lines.append("  <none>")
                return "\n".join(lines)
            for hit in hits:
                lines.extend(
                    [
                        f"  Feature #{hit.feature_index}",
                        f"    layer/net: {hit.layer} / {hit.net}",
                        f"    kind/polarity/symbol: {hit.feature_kind} / {hit.polarity} / {hit.symbol_name or ''}",
                        f"    distance to reported point: {hit.distance_to_point_mm}",
                        f"    intersects probe: {hit.intersects_probe}",
                        f"    bounds mm: {hit.bounds_mm}",
                        f"    area mm2: {hit.area_mm2}",
                        f"    raw attributes: {hit.raw_attributes}",
                        f"    decoded attributes: {hit.decoded_attributes}",
                        f"    raw ODB++ feature: {hit.raw_feature}",
                    ]
                )
            return "\n".join(lines)

        row = rec.as_row()
        lines = [
            "Geometry debug details",
            "======================",
            "",
            f"Layer: {rec.layer}",
            f"Net A: {rec.net_a}",
            f"Net B: {rec.net_b}",
            f"Clearance mm: {rec.clearance_mm}",
            f"Point A mm: ({rec.x_a_mm}, {rec.y_a_mm})",
            f"Point B mm: ({rec.x_b_mm}, {rec.y_b_mm})",
            f"Geometry relation: {rec.relation}",
            f"Zero clearance kind: {rec.zero_clearance_kind}",
            f"Intersection area mm2: {rec.intersection_area_mm2}",
            f"Intersection length mm: {rec.intersection_length_mm}",
            f"Geom A type/bounds: {rec.geom_a_type} / {rec.geom_a_bounds_mm}",
            f"Geom B type/bounds: {rec.geom_b_type} / {rec.geom_b_bounds_mm}",
            "",
            "Meaning:",
            "  - area_overlap usually means the reconstructed copper polygons overlap.",
            "  - touching_boundary means calculated polygons touch exactly at one boundary/point.",
            "  - if the real PCB has clearance but the debug row says area_overlap, inspect cutout/negative features and unsupported feature warnings.",
            "",
            f"Notes: {rec.notes}",
            "",
            format_hits("Source features near Point A", rec.feature_hits_a),
            "",
            format_hits("Source features near Point B", rec.feature_hits_b),
            "",
            format_hits("Negative/cutout features near reported point", rec.negative_hits),
            "",
            "CSV row:",
            str(row),
        ]
        return "\n".join(lines)

    def _fmt_point(self, x: float | None, y: float | None) -> str:
        if x is None or y is None:
            return ""
        return f"({x:.3f}, {y:.3f})"

    def _clear_views(self) -> None:
        self.debug_records = []
        self.visible_critical_records = []
        self.visible_per_net_records = []
        self.visible_airgap_records = []
        for tree in (self.summary_text, self.log, self.critical_tree, self.per_net_tree, self.feature_attr_tree, self.debug_tree, self.airgap_tree):
            for item in tree.get_children():
                tree.delete(item)

    def _open_output_folder(self) -> None:
        path = Path(self.output_dir.get()).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif os.uname().sysname == "Darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')


def main() -> None:
    root = Tk()
    install_material_theme(root)
    ClearanceGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
