from __future__ import annotations

import builtins
import math
import sys
from typing import Any, Mapping

from .voltage_guessing.models import AssignmentStore, VoltageAssignment

MAX_GALVANIC_ZONES = 10
ZONE_LABELS = tuple(f"Zone {i}" for i in range(1, MAX_GALVANIC_ZONES + 1))
ZONE_MATRIX_KEY = "zone_to_zone_voltage_matrix"
DEFAULT_ZONE_VOLTAGE = 1000.0
_PATCHED = "_multi_zone_patch_v1"
_ORIG_INIT = "_multi_zone_orig_init"
_ORIG_SETTINGS = "_multi_zone_orig_settings"
_ORIG_APPLY_SETTINGS = "_multi_zone_orig_apply_settings"
_ORIG_APPLY_ZONE = "_multi_zone_orig_apply_zone"
_IMPORT_HOOK = "_odb_multi_zone_import_hook"


def install_multi_zone_support() -> None:
    _patch_requirements()
    module = sys.modules.get("odb_clearance_analyzer.gui")
    if module is not None:
        _patch_gui(module)
        return
    current_import = builtins.__import__
    if getattr(current_import, _IMPORT_HOOK, False):
        return

    def hook(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[override]
        result = current_import(name, globals, locals, fromlist, level)
        module = sys.modules.get("odb_clearance_analyzer.gui")
        if module is not None:
            _patch_gui(module)
            if builtins.__import__ is hook:
                builtins.__import__ = current_import
        return result

    setattr(hook, _IMPORT_HOOK, True)
    builtins.__import__ = hook


def normalize_zone(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = text.lower().replace(" ", "").replace("_", "").replace("-", "")
    for idx, label in enumerate(ZONE_LABELS, start=1):
        if text == label or compact in {str(idx), f"zone{idx}", f"z{idx}", f"galvaniczone{idx}"}:
            return label
    return ""


def valid_voltage(value: object, default: float = DEFAULT_ZONE_VOLTAGE) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if math.isfinite(parsed) and parsed > 0 else default


def default_matrix(default: float = DEFAULT_ZONE_VOLTAGE) -> dict[str, dict[str, float]]:
    v = valid_voltage(default)
    return {a: {b: (0.0 if a == b else v) for b in ZONE_LABELS} for a in ZONE_LABELS}


def normalize_matrix(settings: Mapping[str, object] | None, default: float = DEFAULT_ZONE_VOLTAGE) -> dict[str, dict[str, float]]:
    settings = dict(settings or {})
    base = valid_voltage(settings.get("galvanic_zone_voltage_v", settings.get("zone_to_zone_voltage_v", default)), default)
    matrix = default_matrix(base)
    raw = settings.get(ZONE_MATRIX_KEY, settings.get("galvanic_zone_voltage_matrix"))
    if isinstance(raw, Mapping):
        for raw_a, raw_row in raw.items():
            za = normalize_zone(raw_a)
            if za and isinstance(raw_row, Mapping):
                for raw_b, raw_v in raw_row.items():
                    zb = normalize_zone(raw_b)
                    if not zb:
                        continue
                    if za == zb:
                        matrix[za][zb] = 0.0
                    else:
                        v = valid_voltage(raw_v, base)
                        matrix[za][zb] = matrix[zb][za] = v
                continue
            key = str(raw_a)
            for sep in ("|", ",", ";", "->", "↔"):
                if sep in key:
                    left, right = key.split(sep, 1)
                    za, zb = normalize_zone(left), normalize_zone(right)
                    if za and zb and za != zb:
                        matrix[za][zb] = matrix[zb][za] = valid_voltage(raw_row, base)
                    break
    elif isinstance(raw, list):
        for r, row in enumerate(raw[:MAX_GALVANIC_ZONES]):
            if not isinstance(row, (list, tuple)):
                continue
            za = ZONE_LABELS[r]
            for c, raw_v in enumerate(row[:MAX_GALVANIC_ZONES]):
                zb = ZONE_LABELS[c]
                matrix[za][zb] = 0.0 if za == zb else valid_voltage(raw_v, base)
        for r, za in enumerate(ZONE_LABELS):
            for c, zb in enumerate(ZONE_LABELS):
                if c > r:
                    matrix[zb][za] = matrix[za][zb]
    return matrix


def zone_pair_voltage(zone_a: object, zone_b: object, settings: Mapping[str, object] | None, default: float = DEFAULT_ZONE_VOLTAGE) -> float:
    za, zb = normalize_zone(zone_a), normalize_zone(zone_b)
    if not za or not zb or za == zb:
        return 0.0
    return valid_voltage(normalize_matrix(settings, default)[za][zb], default)


def _settings_dict(settings: AssignmentStore | Mapping[str, object] | None) -> dict[str, object]:
    if settings is None:
        return {}
    if isinstance(settings, AssignmentStore):
        return dict(settings.settings or {})
    return dict(settings or {})


def _assignments_dict(assignments: AssignmentStore | Mapping[str, VoltageAssignment]) -> Mapping[str, VoltageAssignment]:
    return assignments.assignments if isinstance(assignments, AssignmentStore) else assignments


def _patch_requirements() -> None:
    from .voltage_guessing import galvanic_zones as gz
    from .voltage_guessing import requirements as req

    gz.GALVANIC_ZONE_CHOICES = ("", *ZONE_LABELS)
    gz.normalize_galvanic_zone = normalize_zone
    gz.zone_for_net = lambda assignments, net: normalize_zone(getattr(assignments.get(net), "galvanic_zone", "") if assignments.get(net) else "")
    gz.is_inter_zone_pair = lambda assignments, a, b: bool(gz.zone_for_net(assignments, a) and gz.zone_for_net(assignments, b) and gz.zone_for_net(assignments, a) != gz.zone_for_net(assignments, b))

    def iter_inter_zone_measurements(measurements, assignments):
        for rec in measurements:
            za, zb = gz.zone_for_net(assignments, rec.net_a), gz.zone_for_net(assignments, rec.net_b)
            if za and zb and za != zb:
                yield rec, za, zb

    gz.iter_inter_zone_measurements = iter_inter_zone_measurements
    req.normalize_galvanic_zone = normalize_zone
    req._ZONE_VALUES = set(ZONE_LABELS)

    class MultiZoneVoltageRequirementResolver:
        def __init__(self, assignments, settings=None) -> None:
            self._assignments = _assignments_dict(assignments)
            self._settings = _settings_dict(settings if settings is not None else assignments if isinstance(assignments, AssignmentStore) else None)
            self._zones_enabled = bool(self._settings.get("galvanic_zones_enabled", False)) or any(normalize_zone(getattr(a, "galvanic_zone", "")) for a in self._assignments.values())
            self._default_zone_voltage = valid_voltage(self._settings.get("galvanic_zone_voltage_v", self._settings.get("zone_to_zone_voltage_v", DEFAULT_ZONE_VOLTAGE)))
            self._zone_matrix = normalize_matrix(self._settings, self._default_zone_voltage)
            self._pair_cache = {}

        @property
        def zone_voltage_v(self) -> float:
            return self._zone_matrix["Zone 1"]["Zone 2"]

        @property
        def zone_voltage_matrix(self) -> dict[str, dict[str, float]]:
            return self._zone_matrix

        def resolve(self, net_a: str, net_b: str):
            key = (net_a, net_b)
            if key in self._pair_cache:
                return self._pair_cache[key]
            local = req.resolve_existing_local_net_voltage(net_a, net_b, self._assignments)
            za, zb = normalize_zone(local.zone_a), normalize_zone(local.zone_b)
            if self._zones_enabled and za and zb and za != zb:
                voltage = valid_voltage(self._zone_matrix[za][zb], self._default_zone_voltage)
                result = req.VoltageRequirementResult(net_a, net_b, voltage, req.REQUIREMENT_SOURCE_GALVANIC_ZONE, za, zb, voltage, local.net_a_voltage_v, local.net_b_voltage_v, local.local_voltage_v, local.voltage_difference_v, "")
            else:
                warning = local.warning
                if self._zones_enabled and (not za or not zb):
                    base = getattr(req, "_INCOMPLETE_ZONE_WARNING", "Zone assignment incomplete; result uses local net voltage only.")
                    warning = base if not warning else f"{base} {warning}"
                result = req.VoltageRequirementResult(net_a, net_b, local.required_voltage_v, local.requirement_source, za, zb, None, local.net_a_voltage_v, local.net_b_voltage_v, local.local_voltage_v, local.voltage_difference_v, warning)
            if len(self._pair_cache) < getattr(req, "_PAIR_CACHE_LIMIT", 200_000):
                self._pair_cache[key] = result
            return result

    def resolve_required_spacing_voltage(net_a, net_b, assignments, settings=None):
        return req.VoltageRequirementResolver(assignments, settings).resolve(net_a, net_b)

    def summarize_voltage_requirements_for_measurements(measurements, assignments, settings=None):
        resolver = req.VoltageRequirementResolver(assignments, settings)
        summary = {"zone_voltage_v": resolver.zone_voltage_v, "cross_zone_pairs": 0, "cross_zone_pass": 0, "cross_zone_fail": 0, "cross_zone_unknown": 0, "local_voltage_pairs": 0, "incomplete_zone_pairs": 0, "unknown_voltage_pairs": 0}
        for i, label in enumerate(ZONE_LABELS, start=1):
            summary[f"zone_{i}_nets"] = sum(1 for a in resolver._assignments.values() if normalize_zone(getattr(a, "galvanic_zone", "")) == label)
        for rec in measurements or []:
            vr = resolver.resolve(rec.net_a, rec.net_b)
            if vr.requirement_source == req.REQUIREMENT_SOURCE_GALVANIC_ZONE:
                summary["cross_zone_pairs"] += 1
                status, _ = req.resolve_voltage_standard_compliance(vr.required_voltage_v, getattr(rec, "effective_max_voltage_v", None))
                if status == req.STANDARD_STATUS_OK:
                    summary["cross_zone_pass"] += 1
                elif status == req.STANDARD_STATUS_NOK:
                    summary["cross_zone_fail"] += 1
                else:
                    summary["cross_zone_unknown"] += 1
            else:
                summary["local_voltage_pairs"] += 1
                if vr.warning and "incomplete" in vr.warning.lower():
                    summary["incomplete_zone_pairs"] += 1
                if vr.warning and "unknown" in vr.warning.lower():
                    summary["unknown_voltage_pairs"] += 1
        return summary

    req.VoltageRequirementResolver = MultiZoneVoltageRequirementResolver
    req.resolve_required_spacing_voltage = resolve_required_spacing_voltage
    req.summarize_voltage_requirements_for_measurements = summarize_voltage_requirements_for_measurements


def _patch_gui(gui_module: Any) -> None:
    _patch_requirements()
    from .voltage_guessing import requirements as req

    gui_module.normalize_galvanic_zone = normalize_zone
    gui_module.VoltageRequirementResolver = req.VoltageRequirementResolver
    gui_module.summarize_voltage_requirements_for_measurements = req.summarize_voltage_requirements_for_measurements

    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None or getattr(cls, _PATCHED, False):
        return

    if not hasattr(cls, _ORIG_SETTINGS):
        setattr(cls, _ORIG_SETTINGS, cls._current_voltage_guessing_settings)

        def current_settings(self):
            settings = dict(getattr(cls, _ORIG_SETTINGS)(self))
            settings.update(_settings_from_gui(self))
            return settings

        cls._current_voltage_guessing_settings = current_settings

    if not hasattr(cls, _ORIG_APPLY_SETTINGS):
        setattr(cls, _ORIG_APPLY_SETTINGS, cls._apply_voltage_guessing_settings)

        def apply_settings(self, settings, *args, **kwargs):
            getattr(cls, _ORIG_APPLY_SETTINGS)(self, settings, *args, **kwargs)
            _ensure_vars(gui_module, self)
            _load_vars(self, dict(settings or {}))
            _refresh_zone_comboboxes(gui_module, self)

        cls._apply_voltage_guessing_settings = apply_settings

    if not hasattr(cls, _ORIG_APPLY_ZONE):
        setattr(cls, _ORIG_APPLY_ZONE, getattr(cls, "_apply_zone_to_zone_voltage_setting", None))
        cls._apply_zone_to_zone_voltage_setting = lambda self: _apply_matrix(gui_module, self)

    if not hasattr(cls, _ORIG_INIT):
        setattr(cls, _ORIG_INIT, cls.__init__)

        def init(self, *args, **kwargs):
            getattr(cls, _ORIG_INIT)(self, *args, **kwargs)
            _install_tab(gui_module, self)

        cls.__init__ = init

    setattr(cls, _PATCHED, True)


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
    for a in ZONE_LABELS:
        for b in ZONE_LABELS:
            key = (a, b)
            if key not in vars_map:
                vars_map[key] = gui_module.StringVar(value="0" if a == b else f"{matrix[a][b]:g}")
    return vars_map


def _settings_from_gui(gui: Any) -> dict[str, object]:
    vars_map = getattr(gui, "voltage_zone_matrix_vars", None)
    previous = normalize_matrix(getattr(getattr(gui, "voltage_store", None), "settings", {}) or {}, _legacy_voltage(gui))
    if vars_map:
        matrix = default_matrix(_legacy_voltage(gui))
        for a in ZONE_LABELS:
            for b in ZONE_LABELS:
                matrix[a][b] = 0.0 if a == b else valid_voltage(vars_map[(a, b)].get(), previous[a][b])
        for r, a in enumerate(ZONE_LABELS):
            for c, b in enumerate(ZONE_LABELS):
                if c <= r:
                    continue
                ab, ba = matrix[a][b], matrix[b][a]
                chosen = ba if ab != ba and ab == previous[a][b] and ba != previous[b][a] else ab
                matrix[a][b] = matrix[b][a] = chosen
                try:
                    vars_map[(a, b)].set(f"{chosen:g}")
                    vars_map[(b, a)].set(f"{chosen:g}")
                except Exception:
                    pass
    else:
        matrix = previous
    zone12 = matrix["Zone 1"]["Zone 2"]
    return {"galvanic_zones_supported": list(ZONE_LABELS), "galvanic_zone_count": MAX_GALVANIC_ZONES, "galvanic_zones_enabled": True, ZONE_MATRIX_KEY: matrix, "galvanic_zone_voltage_v": zone12, "zone_to_zone_voltage_v": zone12}


def _load_vars(gui: Any, settings: Mapping[str, object]) -> None:
    vars_map = getattr(gui, "voltage_zone_matrix_vars", {})
    matrix = normalize_matrix(settings, _legacy_voltage(gui))
    for a in ZONE_LABELS:
        for b in ZONE_LABELS:
            if (a, b) in vars_map:
                vars_map[(a, b)].set("0" if a == b else f"{matrix[a][b]:g}")
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
    x = getattr(gui_module, "X", "x")
    ttk.Label(parent, text="Define voltage between galvanic zones. Assignments can use Zone 1 through Zone 10; same-zone pairs use net-to-net voltage difference.", style="Muted.TLabel", wraplength=1100, justify="left").pack(anchor="w", fill=x, pady=(0, 10))
    row = ttk.Frame(parent, style="Card.TFrame")
    row.pack(anchor="w", fill=x, pady=(0, 8))
    ttk.Label(row, text="Supported zones: Zone 1 … Zone 10").pack(side=left, padx=(0, 18))
    ttk.Button(row, text="Apply zone voltage matrix", style="Primary.TButton", command=lambda: _apply_matrix(gui_module, gui)).pack(side=left, padx=(0, 8))
    ttk.Button(row, text="Reset matrix to 1000 V", command=lambda: _reset_matrix(gui_module, gui, DEFAULT_ZONE_VOLTAGE)).pack(side=left, padx=(0, 8))
    ttk.Button(row, text="Use Zone 1↔2 value for all", command=lambda: _reset_matrix(gui_module, gui, _legacy_voltage(gui))).pack(side=left, padx=(0, 8))
    table = ttk.Frame(parent, style="Card.TFrame")
    table.pack(anchor="nw", fill=both, expand=True)
    gui.voltage_zone_matrix_table = table
    ttk.Label(table, text="V required", style="CardSubtitle.TLabel").grid(row=0, column=0, padx=4, pady=4, sticky="ew")
    for c, zone in enumerate(ZONE_LABELS, start=1):
        ttk.Label(table, text=zone, style="CardSubtitle.TLabel").grid(row=0, column=c, padx=2, pady=4, sticky="ew")
        table.columnconfigure(c, weight=1)
    vars_map = _ensure_vars(gui_module, gui)
    for r, a in enumerate(ZONE_LABELS, start=1):
        ttk.Label(table, text=a, style="CardSubtitle.TLabel").grid(row=r, column=0, padx=4, pady=2, sticky="ew")
        for c, b in enumerate(ZONE_LABELS, start=1):
            entry = ttk.Entry(table, textvariable=vars_map[(a, b)], width=8, justify="center")
            entry.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
            if a == b:
                entry.configure(state="disabled")
            else:
                entry.bind("<FocusOut>", lambda _e, za=a, zb=b: _mirror(gui, za, zb))
                entry.bind("<Return>", lambda _e, za=a, zb=b: (_mirror(gui, za, zb), "break")[-1])
    ttk.Label(parent, text="The matrix is symmetric; diagonal cells are fixed at 0 V.", style="Muted.TLabel", wraplength=1100).pack(anchor="w", fill=x, pady=(10, 0))


def _mirror(gui: Any, a: str, b: str) -> None:
    vars_map = getattr(gui, "voltage_zone_matrix_vars", {})
    if (a, b) not in vars_map or (b, a) not in vars_map:
        return
    v = valid_voltage(vars_map[(a, b)].get(), _legacy_voltage(gui))
    vars_map[(a, b)].set(f"{v:g}")
    vars_map[(b, a)].set(f"{v:g}")


def _reset_matrix(gui_module: Any, gui: Any, voltage: float) -> None:
    vars_map = _ensure_vars(gui_module, gui)
    v = valid_voltage(voltage)
    for a in ZONE_LABELS:
        for b in ZONE_LABELS:
            vars_map[(a, b)].set("0" if a == b else f"{v:g}")
    _apply_matrix(gui_module, gui)


def _refresh_zone_comboboxes(gui_module: Any, gui: Any) -> None:
    ttk = gui_module.ttk
    mixed = getattr(gui_module, "_MIXED_ZONE_SELECTION", "<mixed - choose zone>")
    values_mixed = (mixed, "", *ZONE_LABELS)
    values_plain = ("", *ZONE_LABELS)

    def walk(widget):
        for child in getattr(widget, "winfo_children")():
            yield child
            yield from walk(child)

    try:
        widgets = list(walk(gui))
    except Exception:
        return
    for widget in widgets:
        if not isinstance(widget, ttk.Combobox):
            continue
        try:
            values = tuple(str(v) for v in widget.cget("values"))
        except Exception:
            continue
        if "Zone 1" in values and "Zone 2" in values:
            widget.configure(values=values_mixed if mixed in values else values_plain)


def _hide_old_zone_controls(gui: Any) -> None:
    def text(widget):
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
        label = text(widget)
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
                    for sibling in parent.grid_slaves(row=target_row):
                        sibling.destroy()
