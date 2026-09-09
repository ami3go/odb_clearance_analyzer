"""10-zone galvanic-zone voltage matrix integration.

This module intentionally avoids recursive import hooks.  It patches the
voltage requirement resolver once, then patches the Tk GUI after
``odb_clearance_analyzer.gui`` is fully imported.
"""

from __future__ import annotations

import builtins
import importlib
import math
import sys
from typing import Any, Mapping

from .voltage_guessing.models import AssignmentStore, VoltageAssignment


MAX_GALVANIC_ZONES = 10
ZONE_LABELS = tuple(f"Zone {i}" for i in range(1, MAX_GALVANIC_ZONES + 1))
ZONE_MATRIX_KEY = "zone_to_zone_voltage_matrix"
DEFAULT_ZONE_VOLTAGE = 1000.0

_GUI_PATCHED_ATTR = "_multi_zone_gui_patch_installed_v2"
_ORIGINAL_INIT_ATTR = "_multi_zone_original_init_v2"
_ORIGINAL_SETTINGS_ATTR = "_multi_zone_original_settings_v2"
_ORIGINAL_APPLY_SETTINGS_ATTR = "_multi_zone_original_apply_settings_v2"
_ORIGINAL_APPLY_ZONE_ATTR = "_multi_zone_original_apply_zone_v2"
_IMPORT_HOOK_ATTR = "_odb_multi_zone_import_hook_v2"

_REQUIREMENTS_PATCHED = False
_REQUIREMENTS_PATCHING = False
_HOOK_PATCHING = False


def install_multi_zone_support() -> None:
    """Install 10-zone resolver support and patch the GUI when available."""

    _patch_requirements()

    module = sys.modules.get("odb_clearance_analyzer.gui")
    if module is not None and _patch_gui(module):
        return

    current_import = builtins.__import__
    if getattr(current_import, _IMPORT_HOOK_ATTR, False):
        return

    def hook(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[override]
        global _HOOK_PATCHING
        result = current_import(name, globals, locals, fromlist, level)
        if _HOOK_PATCHING:
            return result

        module = sys.modules.get("odb_clearance_analyzer.gui")
        if module is not None:
            _HOOK_PATCHING = True
            try:
                patched = _patch_gui(module)
            finally:
                _HOOK_PATCHING = False
            if patched and builtins.__import__ is hook:
                builtins.__import__ = current_import
        return result

    setattr(hook, _IMPORT_HOOK_ATTR, True)
    builtins.__import__ = hook


def normalize_zone(value: object) -> str:
    """Return ``Zone 1`` ... ``Zone 10`` or ``""`` for unassigned/invalid."""

    text = str(value or "").strip()
    if not text:
        return ""
    compact = text.lower().replace(" ", "").replace("_", "").replace("-", "")
    for idx, label in enumerate(ZONE_LABELS, start=1):
        if text == label or compact in {str(idx), f"zone{idx}", f"z{idx}", f"galvaniczone{idx}"}:
            return label
    return ""


def valid_voltage(value: object, default: float = DEFAULT_ZONE_VOLTAGE) -> float:
    """Return a positive finite voltage, otherwise ``default``."""

    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if math.isfinite(parsed) and parsed > 0 else default


def default_matrix(default: float = DEFAULT_ZONE_VOLTAGE) -> dict[str, dict[str, float]]:
    """Return a symmetric 10-zone matrix with 0 V diagonal."""

    voltage = valid_voltage(default)
    return {a: {b: (0.0 if a == b else voltage) for b in ZONE_LABELS} for a in ZONE_LABELS}


def normalize_matrix(
    settings: Mapping[str, object] | None,
    default: float = DEFAULT_ZONE_VOLTAGE,
) -> dict[str, dict[str, float]]:
    """Normalize stored matrix settings to a full symmetric 10x10 float matrix."""

    settings = dict(settings or {})
    base = valid_voltage(
        settings.get("galvanic_zone_voltage_v", settings.get("zone_to_zone_voltage_v", default)),
        default,
    )
    matrix = default_matrix(base)
    raw = settings.get(ZONE_MATRIX_KEY, settings.get("galvanic_zone_voltage_matrix"))

    if isinstance(raw, Mapping):
        for raw_a, raw_row in raw.items():
            zone_a = normalize_zone(raw_a)
            if zone_a and isinstance(raw_row, Mapping):
                for raw_b, raw_voltage in raw_row.items():
                    zone_b = normalize_zone(raw_b)
                    if not zone_b:
                        continue
                    if zone_a == zone_b:
                        matrix[zone_a][zone_b] = 0.0
                    else:
                        voltage = valid_voltage(raw_voltage, base)
                        matrix[zone_a][zone_b] = voltage
                        matrix[zone_b][zone_a] = voltage
                continue

            key = str(raw_a)
            for separator in ("->", "↔", "|", ",", ";"):
                if separator not in key:
                    continue
                left, right = key.split(separator, 1)
                zone_a = normalize_zone(left)
                zone_b = normalize_zone(right)
                if zone_a and zone_b and zone_a != zone_b:
                    voltage = valid_voltage(raw_row, base)
                    matrix[zone_a][zone_b] = voltage
                    matrix[zone_b][zone_a] = voltage
                break

    elif isinstance(raw, list):
        for row_index, row in enumerate(raw[:MAX_GALVANIC_ZONES]):
            if not isinstance(row, (list, tuple)):
                continue
            zone_a = ZONE_LABELS[row_index]
            for col_index, raw_voltage in enumerate(row[:MAX_GALVANIC_ZONES]):
                zone_b = ZONE_LABELS[col_index]
                matrix[zone_a][zone_b] = 0.0 if zone_a == zone_b else valid_voltage(raw_voltage, base)
        for row_index, zone_a in enumerate(ZONE_LABELS):
            for col_index, zone_b in enumerate(ZONE_LABELS):
                if col_index > row_index:
                    matrix[zone_b][zone_a] = matrix[zone_a][zone_b]

    for zone in ZONE_LABELS:
        matrix[zone][zone] = 0.0
    return matrix


def zone_pair_voltage(
    zone_a: object,
    zone_b: object,
    settings: Mapping[str, object] | None,
    default: float = DEFAULT_ZONE_VOLTAGE,
) -> float:
    """Return required voltage between two zones from the matrix."""

    za = normalize_zone(zone_a)
    zb = normalize_zone(zone_b)
    if not za or not zb or za == zb:
        return 0.0
    return valid_voltage(normalize_matrix(settings, default)[za][zb], default)


def _settings_dict(settings: AssignmentStore | Mapping[str, object] | None) -> dict[str, object]:
    if settings is None:
        return {}
    if isinstance(settings, AssignmentStore):
        return dict(settings.settings or {})
    return dict(settings or {})


def _assignments_dict(
    assignments: AssignmentStore | Mapping[str, VoltageAssignment],
) -> Mapping[str, VoltageAssignment]:
    if isinstance(assignments, AssignmentStore):
        return assignments.assignments
    return assignments


def _patch_requirements() -> None:
    """Patch resolver/galvanic-zone modules once, with recursion protection."""

    global _REQUIREMENTS_PATCHED, _REQUIREMENTS_PATCHING
    if _REQUIREMENTS_PATCHED or _REQUIREMENTS_PATCHING:
        return

    _REQUIREMENTS_PATCHING = True
    try:
        gz = importlib.import_module("odb_clearance_analyzer.voltage_guessing.galvanic_zones")
        req = importlib.import_module("odb_clearance_analyzer.voltage_guessing.requirements")

        gz.GALVANIC_ZONE_CHOICES = ("", *ZONE_LABELS)
        gz.normalize_galvanic_zone = normalize_zone

        def zone_for_net(assignments, net_name):
            assignment = assignments.get(net_name)
            return normalize_zone(getattr(assignment, "galvanic_zone", "") if assignment else "")

        def is_inter_zone_pair(assignments, net_a, net_b):
            zone_a = zone_for_net(assignments, net_a)
            zone_b = zone_for_net(assignments, net_b)
            return bool(zone_a and zone_b and zone_a != zone_b)

        def iter_inter_zone_measurements(measurements, assignments):
            for rec in measurements:
                zone_a = zone_for_net(assignments, rec.net_a)
                zone_b = zone_for_net(assignments, rec.net_b)
                if zone_a and zone_b and zone_a != zone_b:
                    yield rec, zone_a, zone_b

        gz.zone_for_net = zone_for_net
        gz.is_inter_zone_pair = is_inter_zone_pair
        gz.iter_inter_zone_measurements = iter_inter_zone_measurements

        req.normalize_galvanic_zone = normalize_zone
        req._ZONE_VALUES = set(ZONE_LABELS)

        class MultiZoneVoltageRequirementResolver:
            """Matrix-backed replacement for the two-zone resolver."""

            def __init__(self, assignments, settings=None) -> None:
                self._assignments = _assignments_dict(assignments)
                self._settings = _settings_dict(
                    settings
                    if settings is not None
                    else assignments
                    if isinstance(assignments, AssignmentStore)
                    else None
                )
                self._zones_enabled = bool(self._settings.get("galvanic_zones_enabled", False)) or any(
                    normalize_zone(getattr(assignment, "galvanic_zone", ""))
                    for assignment in self._assignments.values()
                )
                self._default_zone_voltage = valid_voltage(
                    self._settings.get(
                        "galvanic_zone_voltage_v",
                        self._settings.get("zone_to_zone_voltage_v", DEFAULT_ZONE_VOLTAGE),
                    )
                )
                self._zone_matrix = normalize_matrix(self._settings, self._default_zone_voltage)
                self._pair_cache: dict[tuple[str, str], Any] = {}

            @property
            def zone_voltage_v(self) -> float:
                """Backward-compatible Zone 1 ↔ Zone 2 voltage."""

                return self._zone_matrix["Zone 1"]["Zone 2"]

            @property
            def zone_voltage_matrix(self) -> dict[str, dict[str, float]]:
                return self._zone_matrix

            def resolve(self, net_a: str, net_b: str):
                key = (net_a, net_b)
                cached = self._pair_cache.get(key)
                if cached is not None:
                    return cached

                local = req.resolve_existing_local_net_voltage(net_a, net_b, self._assignments)
                zone_a = normalize_zone(local.zone_a)
                zone_b = normalize_zone(local.zone_b)

                if self._zones_enabled and zone_a and zone_b and zone_a != zone_b:
                    voltage = valid_voltage(self._zone_matrix[zone_a][zone_b], self._default_zone_voltage)
                    result = req.VoltageRequirementResult(
                        net_a=net_a,
                        net_b=net_b,
                        required_voltage_v=voltage,
                        requirement_source=req.REQUIREMENT_SOURCE_GALVANIC_ZONE,
                        zone_a=zone_a,
                        zone_b=zone_b,
                        zone_voltage_v=voltage,
                        net_a_voltage_v=local.net_a_voltage_v,
                        net_b_voltage_v=local.net_b_voltage_v,
                        local_voltage_v=local.local_voltage_v,
                        voltage_difference_v=local.voltage_difference_v,
                        warning="",
                    )
                else:
                    warning = local.warning
                    if self._zones_enabled and (not zone_a or not zone_b):
                        incomplete = getattr(
                            req,
                            "_INCOMPLETE_ZONE_WARNING",
                            "Zone assignment incomplete; result uses local net voltage only.",
                        )
                        warning = incomplete if not warning else f"{incomplete} {warning}"
                    result = req.VoltageRequirementResult(
                        net_a=net_a,
                        net_b=net_b,
                        required_voltage_v=local.required_voltage_v,
                        requirement_source=local.requirement_source,
                        zone_a=zone_a,
                        zone_b=zone_b,
                        zone_voltage_v=None,
                        net_a_voltage_v=local.net_a_voltage_v,
                        net_b_voltage_v=local.net_b_voltage_v,
                        local_voltage_v=local.local_voltage_v,
                        voltage_difference_v=local.voltage_difference_v,
                        warning=warning,
                    )

                if len(self._pair_cache) < getattr(req, "_PAIR_CACHE_LIMIT", 200_000):
                    self._pair_cache[key] = result
                return result

        def resolve_required_spacing_voltage(net_a, net_b, assignments, settings=None):
            return req.VoltageRequirementResolver(assignments, settings).resolve(net_a, net_b)

        def summarize_voltage_requirements_for_measurements(measurements, assignments, settings=None):
            resolver = req.VoltageRequirementResolver(assignments, settings)
            summary: dict[str, int | float | None] = {
                "zone_voltage_v": resolver.zone_voltage_v,
                "cross_zone_pairs": 0,
                "cross_zone_pass": 0,
                "cross_zone_fail": 0,
                "cross_zone_unknown": 0,
                "local_voltage_pairs": 0,
                "incomplete_zone_pairs": 0,
                "unknown_voltage_pairs": 0,
            }
            for index, label in enumerate(ZONE_LABELS, start=1):
                summary[f"zone_{index}_nets"] = sum(
                    1
                    for assignment in resolver._assignments.values()
                    if normalize_zone(getattr(assignment, "galvanic_zone", "")) == label
                )

            for rec in measurements or []:
                resolved = resolver.resolve(rec.net_a, rec.net_b)
                if resolved.requirement_source == req.REQUIREMENT_SOURCE_GALVANIC_ZONE:
                    summary["cross_zone_pairs"] += 1
                    status, _ = req.resolve_voltage_standard_compliance(
                        resolved.required_voltage_v,
                        getattr(rec, "effective_max_voltage_v", None),
                    )
                    if status == req.STANDARD_STATUS_OK:
                        summary["cross_zone_pass"] += 1
                    elif status == req.STANDARD_STATUS_NOK:
                        summary["cross_zone_fail"] += 1
                    else:
                        summary["cross_zone_unknown"] += 1
                else:
                    summary["local_voltage_pairs"] += 1
                    warning = str(resolved.warning or "").lower()
                    if "incomplete" in warning:
                        summary["incomplete_zone_pairs"] += 1
                    if "unknown" in warning:
                        summary["unknown_voltage_pairs"] += 1
            return summary

        req.VoltageRequirementResolver = MultiZoneVoltageRequirementResolver
        req.resolve_required_spacing_voltage = resolve_required_spacing_voltage
        req.summarize_voltage_requirements_for_measurements = summarize_voltage_requirements_for_measurements

        for module_name in ("odb_clearance_analyzer.reports", "odb_clearance_analyzer.gui"):
            module = sys.modules.get(module_name)
            if module is not None:
                setattr(module, "VoltageRequirementResolver", req.VoltageRequirementResolver)
                setattr(module, "summarize_voltage_requirements_for_measurements", summarize_voltage_requirements_for_measurements)
                if module_name.endswith(".gui"):
                    setattr(module, "normalize_galvanic_zone", normalize_zone)

        _REQUIREMENTS_PATCHED = True
    finally:
        _REQUIREMENTS_PATCHING = False


def _patch_gui(gui_module: Any) -> bool:
    """Patch ClearanceGui after its class exists.  Returns True when done."""

    _patch_requirements()

    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None:
        return False
    if getattr(cls, _GUI_PATCHED_ATTR, False):
        return True

    req = importlib.import_module("odb_clearance_analyzer.voltage_guessing.requirements")
    gui_module.normalize_galvanic_zone = normalize_zone
    gui_module.VoltageRequirementResolver = req.VoltageRequirementResolver
    gui_module.summarize_voltage_requirements_for_measurements = req.summarize_voltage_requirements_for_measurements

    if not hasattr(cls, _ORIGINAL_SETTINGS_ATTR):
        setattr(cls, _ORIGINAL_SETTINGS_ATTR, cls._current_voltage_guessing_settings)

        def current_settings(self):
            settings = dict(getattr(cls, _ORIGINAL_SETTINGS_ATTR)(self))
            settings.update(_settings_from_gui(self))
            return settings

        cls._current_voltage_guessing_settings = current_settings

    if not hasattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR):
        setattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR, cls._apply_voltage_guessing_settings)

        def apply_settings(self, settings, *args, **kwargs):
            getattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR)(self, settings, *args, **kwargs)
            _ensure_vars(gui_module, self)
            _load_vars(self, dict(settings or {}))
            _refresh_zone_comboboxes(gui_module, self)

        cls._apply_voltage_guessing_settings = apply_settings

    if not hasattr(cls, _ORIGINAL_APPLY_ZONE_ATTR):
        setattr(cls, _ORIGINAL_APPLY_ZONE_ATTR, getattr(cls, "_apply_zone_to_zone_voltage_setting", None))
        cls._apply_zone_to_zone_voltage_setting = lambda self: _apply_matrix(gui_module, self)

    if not hasattr(cls, _ORIGINAL_INIT_ATTR):
        setattr(cls, _ORIGINAL_INIT_ATTR, cls.__init__)

        def init(self, *args, **kwargs):
            getattr(cls, _ORIGINAL_INIT_ATTR)(self, *args, **kwargs)
            _install_tab(gui_module, self)

        cls.__init__ = init

    setattr(cls, _GUI_PATCHED_ATTR, True)
    return True


def _legacy_voltage(gui: Any) -> float:
    try:
        return valid_voltage(gui.voltage_galvanic_zone_voltage.get())
    except Exception:
        return DEFAULT_ZONE_VOLTAGE


def _ensure_vars(gui_module: Any, gui: Any) -> dict[tuple[str, str], Any]:
    if not hasattr(gui, "voltage_zone_matrix_vars"):
        gui.voltage_zone_matrix_vars = {}
    vars_map = gui.voltage_zone_matrix_vars
    matrix = normalize_matrix(getattr(getattr(gui, "voltage_store", None), "settings", {}) or {}, _legacy_voltage(gui))
    for zone_a in ZONE_LABELS:
        for zone_b in ZONE_LABELS:
            key = (zone_a, zone_b)
            if key not in vars_map:
                vars_map[key] = gui_module.StringVar(
                    value="0" if zone_a == zone_b else f"{matrix[zone_a][zone_b]:g}"
                )
    return vars_map


def _settings_from_gui(gui: Any) -> dict[str, object]:
    vars_map = getattr(gui, "voltage_zone_matrix_vars", None)
    previous = normalize_matrix(getattr(getattr(gui, "voltage_store", None), "settings", {}) or {}, _legacy_voltage(gui))
    if not vars_map:
        matrix = previous
    else:
        matrix = default_matrix(_legacy_voltage(gui))
        for zone_a in ZONE_LABELS:
            for zone_b in ZONE_LABELS:
                if zone_a == zone_b:
                    matrix[zone_a][zone_b] = 0.0
                else:
                    matrix[zone_a][zone_b] = valid_voltage(vars_map[(zone_a, zone_b)].get(), previous[zone_a][zone_b])

        for row_index, zone_a in enumerate(ZONE_LABELS):
            for col_index, zone_b in enumerate(ZONE_LABELS):
                if col_index <= row_index:
                    continue
                value = matrix[zone_a][zone_b]
                matrix[zone_b][zone_a] = value
                try:
                    vars_map[(zone_a, zone_b)].set(f"{value:g}")
                    vars_map[(zone_b, zone_a)].set(f"{value:g}")
                except Exception:
                    pass

    zone12 = matrix["Zone 1"]["Zone 2"]
    return {
        "galvanic_zones_supported": list(ZONE_LABELS),
        "galvanic_zone_count": MAX_GALVANIC_ZONES,
        "galvanic_zones_enabled": True,
        ZONE_MATRIX_KEY: matrix,
        "galvanic_zone_voltage_v": zone12,
        "zone_to_zone_voltage_v": zone12,
    }


def _load_vars(gui: Any, settings: Mapping[str, object]) -> None:
    vars_map = getattr(gui, "voltage_zone_matrix_vars", {})
    matrix = normalize_matrix(settings, _legacy_voltage(gui))
    for zone_a in ZONE_LABELS:
        for zone_b in ZONE_LABELS:
            var = vars_map.get((zone_a, zone_b))
            if var is not None:
                var.set("0" if zone_a == zone_b else f"{matrix[zone_a][zone_b]:g}")
    try:
        gui.voltage_galvanic_zone_voltage.set(matrix["Zone 1"]["Zone 2"])
    except Exception:
        pass


def _apply_matrix(gui_module: Any, gui: Any) -> None:
    _install_tab(gui_module, gui)
    settings = _settings_from_gui(gui)
    store = getattr(gui, "voltage_store", None)
    if store is not None:
        if not getattr(store, "settings", None):
            store.settings = {}
        store.settings.update(settings)
    try:
        gui.voltage_galvanic_zone_voltage.set(settings["galvanic_zone_voltage_v"])
    except Exception:
        pass
    if hasattr(gui, "_save_voltage_settings_safely"):
        gui._save_voltage_settings_safely()
    if hasattr(gui, "_refresh_voltage_views"):
        gui._refresh_voltage_views()
    if hasattr(gui, "_append_log"):
        gui._append_log("Voltage Guessing: applied 10-zone voltage matrix.")
    try:
        gui_module.messagebox.showinfo("Voltage zones", "Saved the 10-zone voltage matrix.")
    except Exception:
        pass


def _install_tab(gui_module: Any, gui: Any) -> None:
    notebook = getattr(gui, "voltage_notebook", None)
    if notebook is None:
        return

    _ensure_vars(gui_module, gui)
    _refresh_zone_comboboxes(gui_module, gui)

    if not getattr(gui, "_zones_tab_added", False):
        tab = gui_module.ttk.Frame(notebook, padding=8, style="Card.TFrame")
        _build_tab(gui_module, gui, tab)
        try:
            notebook.insert(1, tab, text="Zones")
        except Exception:
            notebook.add(tab, text="Zones")
        gui.voltage_zones_tab = tab
        gui._zones_tab_added = True

    _hide_old_zone_controls(gui)


def _build_tab(gui_module: Any, gui: Any, parent: Any) -> None:
    ttk = gui_module.ttk
    left = getattr(gui_module, "LEFT", "left")
    both = getattr(gui_module, "BOTH", "both")
    x_fill = getattr(gui_module, "X", "x")

    ttk.Label(
        parent,
        text=(
            "Define required voltage between galvanic zones. Assignments can use Zone 1 through "
            "Zone 10; same-zone pairs still use the local net-to-net voltage difference."
        ),
        style="Muted.TLabel",
        wraplength=1100,
        justify="left",
    ).pack(anchor="w", fill=x_fill, pady=(0, 10))

    row = ttk.Frame(parent, style="Card.TFrame")
    row.pack(anchor="w", fill=x_fill, pady=(0, 8))
    ttk.Label(row, text="Supported zones: Zone 1 … Zone 10").pack(side=left, padx=(0, 18))
    ttk.Button(
        row,
        text="Apply zone voltage matrix",
        style="Primary.TButton",
        command=lambda: _apply_matrix(gui_module, gui),
    ).pack(side=left, padx=(0, 8))
    ttk.Button(
        row,
        text="Reset matrix to 1000 V",
        command=lambda: _reset_matrix(gui_module, gui, DEFAULT_ZONE_VOLTAGE),
    ).pack(side=left, padx=(0, 8))
    ttk.Button(
        row,
        text="Use Zone 1↔2 value for all",
        command=lambda: _reset_matrix(gui_module, gui, _legacy_voltage(gui)),
    ).pack(side=left, padx=(0, 8))

    table = ttk.Frame(parent, style="Card.TFrame")
    table.pack(anchor="nw", fill=both, expand=True)
    gui.voltage_zone_matrix_table = table

    ttk.Label(table, text="V required", style="CardSubtitle.TLabel").grid(row=0, column=0, padx=4, pady=4, sticky="ew")
    for col, zone in enumerate(ZONE_LABELS, start=1):
        ttk.Label(table, text=zone, style="CardSubtitle.TLabel").grid(row=0, column=col, padx=2, pady=4, sticky="ew")
        table.columnconfigure(col, weight=1)

    vars_map = _ensure_vars(gui_module, gui)
    for row_index, zone_a in enumerate(ZONE_LABELS, start=1):
        ttk.Label(table, text=zone_a, style="CardSubtitle.TLabel").grid(row=row_index, column=0, padx=4, pady=2, sticky="ew")
        for col_index, zone_b in enumerate(ZONE_LABELS, start=1):
            entry = ttk.Entry(table, textvariable=vars_map[(zone_a, zone_b)], width=8, justify="center")
            entry.grid(row=row_index, column=col_index, padx=2, pady=2, sticky="ew")
            if zone_a == zone_b:
                entry.configure(state="disabled")
            else:
                entry.bind("<FocusOut>", lambda _event, a=zone_a, b=zone_b: _mirror(gui, a, b))
                entry.bind("<Return>", lambda _event, a=zone_a, b=zone_b: (_mirror(gui, a, b), "break")[-1])

    ttk.Label(
        parent,
        text="The matrix is symmetric; diagonal cells are fixed at 0 V. Values are saved in the project voltage-assignment settings.",
        style="Muted.TLabel",
        wraplength=1100,
    ).pack(anchor="w", fill=x_fill, pady=(10, 0))


def _mirror(gui: Any, zone_a: str, zone_b: str) -> None:
    vars_map = getattr(gui, "voltage_zone_matrix_vars", {})
    if (zone_a, zone_b) not in vars_map or (zone_b, zone_a) not in vars_map:
        return
    value = valid_voltage(vars_map[(zone_a, zone_b)].get(), _legacy_voltage(gui))
    vars_map[(zone_a, zone_b)].set(f"{value:g}")
    vars_map[(zone_b, zone_a)].set(f"{value:g}")


def _reset_matrix(gui_module: Any, gui: Any, voltage: float) -> None:
    vars_map = _ensure_vars(gui_module, gui)
    value = valid_voltage(voltage)
    for zone_a in ZONE_LABELS:
        for zone_b in ZONE_LABELS:
            vars_map[(zone_a, zone_b)].set("0" if zone_a == zone_b else f"{value:g}")
    _apply_matrix(gui_module, gui)


def _refresh_zone_comboboxes(gui_module: Any, gui: Any) -> None:
    ttk = gui_module.ttk
    mixed = getattr(gui_module, "_MIXED_ZONE_SELECTION", "<mixed - choose zone>")
    values_mixed = (mixed, "", *ZONE_LABELS)
    values_plain = ("", *ZONE_LABELS)

    def walk(widget):
        try:
            children = list(widget.winfo_children())
        except Exception:
            children = []
        for child in children:
            yield child
            yield from walk(child)

    for widget in list(walk(gui)):
        if not isinstance(widget, ttk.Combobox):
            continue
        try:
            values = tuple(str(v) for v in widget.cget("values"))
        except Exception:
            continue
        if "Zone 1" in values and "Zone 2" in values:
            widget.configure(values=values_mixed if mixed in values else values_plain)


def _hide_old_zone_controls(gui: Any) -> None:
    def widget_text(widget):
        try:
            return str(widget.cget("text") or "")
        except Exception:
            return ""

    def walk(widget):
        try:
            children = list(widget.winfo_children())
        except Exception:
            children = []
        for child in children:
            yield child
            yield from walk(child)

    for widget in list(walk(gui)):
        label = widget_text(widget)
        if label == "Zone 1 ↔ Zone 2 working voltage, V":
            try:
                widget.master.destroy()
            except Exception:
                pass
        elif label == "Zone-to-zone voltage V":
            parent = getattr(widget, "master", None)
            try:
                row = int(widget.grid_info().get("row", -1))
            except Exception:
                row = -1
            if parent is not None and row >= 0:
                for target_row in (row, row + 1, row + 2):
                    try:
                        slaves = list(parent.grid_slaves(row=target_row))
                    except Exception:
                        slaves = []
                    for sibling in slaves:
                        try:
                            sibling.destroy()
                        except Exception:
                            pass
