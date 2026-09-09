"""Visible GUI integration for default Zone 1 and header action controls."""

from __future__ import annotations

import builtins
import sys
from typing import Any, Callable


_PATCHED_ATTR = "_zone1_default_gui_patch_installed_v4"
_IMPORT_HOOK_ATTR = "_odb_zone1_default_import_hook"
_ORIGINAL_INIT_ATTR = "_zone1_default_original_init"
_ORIGINAL_CREATE_TAB_ATTR = "_zone1_default_original_create_tab"
_ORIGINAL_SETTINGS_ATTR = "_zone1_default_original_settings"
_ORIGINAL_APPLY_SETTINGS_ATTR = "_zone1_default_original_apply_settings"
_ORIGINAL_MUTATOR_PREFIX = "_zone1_default_original_"
_CHECKBOX_TEXT = "Assign all unassigned nets to Zone 1 automatically"
_SETTING_KEY = "default_all_nets_to_zone_1"
_HEADER_ACTION_TEXTS = {"Run analysis", "Stop", "Open output", "Geometry viewer"}
_HEADER_RUN_STYLE = "HeaderRun.TButton"
_RUN_TEXT = "Run analysis"
_STOP_TEXT = "Stop"
_MODE_IDLE = "idle"
_MODE_RUNNING = "running"
_MODE_STOPPING = "stopping"


def main() -> None:
    """Launch the GUI after applying the visible GUI integrations."""

    from . import gui as gui_module

    _patch_gui_module(gui_module)
    gui_module.main()


def install_zone1_default_gui_patch() -> None:
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
    """Install robust visible GUI patches on ``ClearanceGui``."""

    cls = getattr(gui_module, "ClearanceGui", None)
    if cls is None:
        return

    # Always publish/refresh these methods, even if an older patch ran already.
    cls._default_all_nets_zone1_enabled = _make_default_enabled()
    cls._apply_default_zone1_to_unassigned_assignments = _make_apply_default_zone1(gui_module)
    cls._apply_default_all_nets_zone1_setting = _make_apply_checkbox_setting(gui_module)

    if not hasattr(cls, _ORIGINAL_INIT_ATTR):
        setattr(cls, _ORIGINAL_INIT_ATTR, cls.__init__)

        def patched_init(self: Any, *args: Any, **kwargs: Any):
            if not hasattr(self, "voltage_default_all_nets_zone1"):
                self.voltage_default_all_nets_zone1 = gui_module.BooleanVar(value=False)
            original_init = getattr(cls, _ORIGINAL_INIT_ATTR)
            original_init(self, *args, **kwargs)
            _add_checkbox_to_overview(gui_module, self)
            _move_main_controls_to_header(gui_module, self)

        cls.__init__ = patched_init

    if not hasattr(cls, _ORIGINAL_CREATE_TAB_ATTR):
        setattr(cls, _ORIGINAL_CREATE_TAB_ATTR, cls._create_voltage_guessing_tab)

        def patched_create_tab(self: Any, parent: Any) -> None:
            original_create_tab = getattr(cls, _ORIGINAL_CREATE_TAB_ATTR)
            original_create_tab(self, parent)
            _add_checkbox_to_overview(gui_module, self)
            _move_main_controls_to_header(gui_module, self)

        cls._create_voltage_guessing_tab = patched_create_tab

    if not hasattr(cls, _ORIGINAL_SETTINGS_ATTR):
        setattr(cls, _ORIGINAL_SETTINGS_ATTR, cls._current_voltage_guessing_settings)

        def patched_settings(self: Any) -> dict[str, object]:
            original_settings = getattr(cls, _ORIGINAL_SETTINGS_ATTR)
            settings = dict(original_settings(self))
            settings[_SETTING_KEY] = self._default_all_nets_zone1_enabled()
            return settings

        cls._current_voltage_guessing_settings = patched_settings

    if not hasattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR):
        setattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR, cls._apply_voltage_guessing_settings)

        def patched_apply_settings(
            self: Any, settings: dict[str, object] | None, *args: Any, **kwargs: Any
        ) -> None:
            original_apply_settings = getattr(cls, _ORIGINAL_APPLY_SETTINGS_ATTR)
            original_apply_settings(self, settings, *args, **kwargs)
            values = dict(settings or {})
            raw = values.get(_SETTING_KEY, values.get("assign_all_nets_to_zone_1", None))
            if raw is not None:
                _ensure_checkbox_var(gui_module, self).set(_coerce_bool(raw))
            _add_checkbox_to_overview(gui_module, self)
            _move_main_controls_to_header(gui_module, self)

        cls._apply_voltage_guessing_settings = patched_apply_settings

    for method_name in (
        "_run_voltage_auto_detect",
        "_apply_voltage_safe_matches",
        "_apply_voltage_selected_suggestion",
        "_load_voltage_store_if_present",
    ):
        _wrap_assignment_mutator_once(gui_module, cls, method_name)

    setattr(cls, _PATCHED_ATTR, True)


def _make_default_enabled() -> Callable[[Any], bool]:
    def default_enabled(self: Any) -> bool:
        var = getattr(self, "voltage_default_all_nets_zone1", None)
        try:
            return bool(var.get())
        except Exception:
            return False

    return default_enabled


def _make_apply_default_zone1(gui_module: Any) -> Callable[[Any], int]:
    def apply_default_zone1(self: Any) -> int:
        if not self._default_all_nets_zone1_enabled():
            return 0
        store = getattr(self, "voltage_store", None)
        assignments = getattr(store, "assignments", {}) if store is not None else {}
        if not assignments:
            return 0
        blank_nets = [
            net
            for net, assignment in sorted(assignments.items())
            if not gui_module.normalize_galvanic_zone(getattr(assignment, "galvanic_zone", ""))
        ]
        if not blank_nets:
            return 0
        return gui_module.review_service.apply_galvanic_zone_bulk(
            store, blank_nets, galvanic_zone=gui_module.GALVANIC_ZONE_1
        )

    return apply_default_zone1


def _make_apply_checkbox_setting(gui_module: Any) -> Callable[[Any], None]:
    def apply_checkbox_setting(self: Any) -> None:
        _add_checkbox_to_overview(gui_module, self)
        changed = self._apply_default_zone1_to_unassigned_assignments()
        _save_zone1_default_state(self)
        if hasattr(self, "_refresh_voltage_views"):
            self._refresh_voltage_views()
        elif hasattr(self, "_refresh_voltage_overview"):
            self._refresh_voltage_overview()
        if hasattr(self, "_append_log"):
            if self._default_all_nets_zone1_enabled():
                self._append_log(
                    f"Voltage Guessing: default Zone 1 is enabled; assigned Zone 1 to {changed} net(s) with blank galvanic zone."
                )
            else:
                self._append_log(
                    "Voltage Guessing: default Zone 1 assignment is disabled; existing zones were not changed."
                )

    return apply_checkbox_setting


def _wrap_assignment_mutator_once(gui_module: Any, cls: Any, method_name: str) -> None:
    original_attr = _ORIGINAL_MUTATOR_PREFIX + method_name
    if hasattr(cls, original_attr):
        return
    original = getattr(cls, method_name, None)
    if not callable(original):
        return
    setattr(cls, original_attr, original)

    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        _add_checkbox_to_overview(gui_module, self)
        _move_main_controls_to_header(gui_module, self)
        changed = self._apply_default_zone1_to_unassigned_assignments()
        if changed:
            _save_zone1_default_state(self)
            if hasattr(self, "_refresh_voltage_views"):
                self._refresh_voltage_views()
            if hasattr(self, "_append_log"):
                self._append_log(
                    f"Voltage Guessing: default Zone 1 applied to {changed} net(s) with blank galvanic zone."
                )
        return result

    setattr(cls, method_name, wrapped)


def _save_zone1_default_state(gui: Any) -> None:
    if hasattr(gui, "_sync_voltage_settings_to_store"):
        gui._sync_voltage_settings_to_store()
    store = getattr(gui, "voltage_store", None)
    settings = getattr(store, "settings", None) if store is not None else None
    if isinstance(settings, dict):
        settings[_SETTING_KEY] = gui._default_all_nets_zone1_enabled()
    assignments = getattr(store, "assignments", {}) if store is not None else {}
    if assignments and hasattr(gui, "_save_voltage_store_safely"):
        gui._save_voltage_store_safely()
    elif hasattr(gui, "_save_voltage_settings_safely"):
        gui._save_voltage_settings_safely()


def _ensure_checkbox_var(gui_module: Any, gui: Any):
    if not hasattr(gui, "voltage_default_all_nets_zone1"):
        gui.voltage_default_all_nets_zone1 = gui_module.BooleanVar(value=False)
    return gui.voltage_default_all_nets_zone1


def _widget_texts(widget: Any) -> list[str]:
    texts: list[str] = []
    try:
        text = widget.cget("text")
    except Exception:
        text = ""
    if text:
        texts.append(str(text))
    try:
        children = list(widget.winfo_children())
    except Exception:
        children = []
    for child in children:
        texts.extend(_widget_texts(child))
    return texts


def _find_voltage_overview_tab(gui: Any) -> Any | None:
    notebook = getattr(gui, "voltage_notebook", None)
    if notebook is None:
        return None
    try:
        tabs = notebook.tabs()
        if not tabs:
            return None
        return notebook.nametowidget(tabs[0])
    except Exception:
        return None


def _find_workflow_card(overview_tab: Any) -> Any:
    try:
        children = list(overview_tab.winfo_children())
    except Exception:
        return overview_tab
    for child in children:
        if "Voltage assignment workflow" in _widget_texts(child):
            return child
    return children[1] if len(children) > 1 else overview_tab


def _add_checkbox_to_overview(gui_module: Any, gui: Any) -> None:
    if getattr(gui, "_zone1_default_control_added", False):
        return
    overview_tab = _find_voltage_overview_tab(gui)
    if overview_tab is None:
        return
    if _CHECKBOX_TEXT in _widget_texts(overview_tab):
        gui._zone1_default_control_added = True
        return

    ttk = gui_module.ttk
    x_fill = getattr(gui_module, "X", "x")
    left = getattr(gui_module, "LEFT", "left")
    workflow = _find_workflow_card(overview_tab)
    row = ttk.Frame(workflow, style="Card.TFrame")

    pack_options: dict[str, Any] = {"anchor": "w", "fill": x_fill, "pady": (10, 0)}
    try:
        workflow_children = list(workflow.winfo_children())
        # Put the checkbox where the user is already looking: directly above
        # the existing "Max cell voltage" row in the workflow card.
        for child in workflow_children:
            if "Max cell voltage" in _widget_texts(child):
                pack_options["before"] = child
                break
    except Exception:
        pass
    row.pack(**pack_options)

    ttk.Checkbutton(
        row,
        text=_CHECKBOX_TEXT,
        variable=_ensure_checkbox_var(gui_module, gui),
        command=gui._apply_default_all_nets_zone1_setting,
    ).pack(side=left, padx=(0, 10))
    ttk.Label(
        row,
        text="Checked: blank galvanic-zone fields are filled with Zone 1 after Auto-detect/import. Manual Zone 2 choices are preserved.",
        style="Muted.TLabel",
        wraplength=900,
    ).pack(side=left)
    gui._zone1_default_control_added = True


def _safe_widget_text(widget: Any) -> str:
    try:
        return str(widget.cget("text") or "")
    except Exception:
        return ""


def _safe_widget_state(widget: Any, default: str = "normal") -> str:
    try:
        return str(widget.cget("state") or default)
    except Exception:
        return default


def _remove_original_action_buttons(gui: Any) -> None:
    """Remove the old action buttons from the input/options card.

    The options row should keep checkboxes such as Include $NONE$, Effective
    Net-to-Net distance, and Dark theme. Only the four action buttons are
    removed and recreated in the app header.
    """

    run_button = getattr(gui, "run_button", None)
    try:
        original_parent = run_button.master
    except Exception:
        return

    try:
        children = list(original_parent.winfo_children())
    except Exception:
        children = []
    for child in children:
        if _safe_widget_text(child) in _HEADER_ACTION_TEXTS:
            try:
                child.destroy()
            except Exception:
                pass


def _configure_header_button_styles(gui_module: Any, gui: Any) -> None:
    """Create a high-contrast Run button style for the purple app header."""

    ttk = gui_module.ttk
    colors = getattr(gui_module, "MATERIAL_COLORS", {}) or {}
    try:
        style = ttk.Style(getattr(gui, "master", None))
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
        _HEADER_RUN_STYLE,
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
        _HEADER_RUN_STYLE,
        background=[
            ("active", active_background),
            ("pressed", active_background),
            ("disabled", disabled_background),
        ],
        foreground=[("disabled", disabled_foreground)],
    )


def _set_run_stop_button_mode(gui: Any, mode: str) -> None:
    """Render the one visible run/stop button for the requested analysis state."""

    button = getattr(gui, "run_stop_button", None)
    if button is None:
        return
    if mode not in {_MODE_IDLE, _MODE_RUNNING, _MODE_STOPPING}:
        mode = _MODE_IDLE
    gui._run_stop_mode = mode

    if mode == _MODE_IDLE:
        button.configure(
            text=_RUN_TEXT,
            style=_HEADER_RUN_STYLE,
            command=gui._start_analysis,
            state="normal",
        )
    elif mode == _MODE_RUNNING:
        button.configure(
            text=_STOP_TEXT,
            style="Danger.TButton",
            command=gui._stop_analysis,
            state="normal",
        )
    else:
        button.configure(
            text=_STOP_TEXT,
            style="Danger.TButton",
            command=gui._stop_analysis,
            state="disabled",
        )


class _RunStopButtonProxy:
    """Compatibility facade for old two-button GUI state transitions.

    The original GUI expects separate ``run_button`` and ``stop_button``
    objects.  The header now has one visible button.  This proxy converts the
    old state changes into the correct visible state:

    - ``run_button.configure(state='disabled')`` -> visible button becomes Stop.
    - ``stop_button.configure(state='normal')`` -> visible button remains Stop.
    - ``stop_button.configure(state='disabled')`` while running -> disabled Stop.
    - ``run_button.configure(state='normal')`` -> visible button becomes Run.
    """

    def __init__(self, gui: Any, button: Any, role: str):
        self._gui = gui
        self._button = button
        self._role = role

    @property
    def master(self) -> Any:
        return self._button.master

    def configure(self, *args: Any, **kwargs: Any) -> Any:
        state = kwargs.pop("state", None)
        if state is not None:
            self._apply_state(str(state))
        if kwargs:
            return self._button.configure(*args, **kwargs)
        if args:
            return self._button.configure(*args)
        return None

    config = configure

    def cget(self, option: str) -> Any:
        if option == "state":
            mode = getattr(self._gui, "_run_stop_mode", _MODE_IDLE)
            if self._role == "run":
                return "normal" if mode == _MODE_IDLE else "disabled"
            return "normal" if mode == _MODE_RUNNING else "disabled"
        return self._button.cget(option)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._button, name)

    def _apply_state(self, state: str) -> None:
        mode = getattr(self._gui, "_run_stop_mode", _MODE_IDLE)
        if self._role == "run":
            if state == "disabled":
                _set_run_stop_button_mode(self._gui, _MODE_RUNNING)
            elif state == "normal":
                _set_run_stop_button_mode(self._gui, _MODE_IDLE)
            else:
                self._button.configure(state=state)
            return

        if state == "normal":
            _set_run_stop_button_mode(self._gui, _MODE_RUNNING)
        elif state == "disabled":
            if mode == _MODE_RUNNING:
                _set_run_stop_button_mode(self._gui, _MODE_STOPPING)
            elif mode == _MODE_STOPPING:
                self._button.configure(state="disabled")
            else:
                _set_run_stop_button_mode(self._gui, _MODE_IDLE)
        else:
            self._button.configure(state=state)


def _move_main_controls_to_header(gui_module: Any, gui: Any) -> None:
    """Move analysis actions to the app header and combine Run/Stop into one button."""

    if getattr(gui, "_main_control_buttons_in_header", False):
        _configure_header_button_styles(gui_module, gui)
        if getattr(gui, "run_stop_button", None) is not None:
            _set_run_stop_button_mode(gui, getattr(gui, "_run_stop_mode", _MODE_IDLE))
        return

    progress = getattr(gui, "progress", None)
    old_run_button = getattr(gui, "run_button", None)
    old_stop_button = getattr(gui, "stop_button", None)
    if progress is None or old_run_button is None or old_stop_button is None:
        return

    try:
        status_panel = progress.master
        appbar = status_panel.master
    except Exception:
        return

    run_state = _safe_widget_state(old_run_button, "normal")
    stop_state = _safe_widget_state(old_stop_button, "disabled")
    _remove_original_action_buttons(gui)
    _configure_header_button_styles(gui_module, gui)

    ttk = gui_module.ttk
    left = getattr(gui_module, "LEFT", "left")
    x_fill = getattr(gui_module, "X", "x")

    try:
        appbar.columnconfigure(0, weight=1)
        appbar.columnconfigure(1, weight=0)
        appbar.columnconfigure(2, weight=1)
        status_panel.grid_configure(row=0, column=2, sticky="e", padx=(18, 0))
    except Exception:
        pass

    controls = ttk.Frame(appbar, style="AppBar.TFrame")
    try:
        controls.grid(row=0, column=1, sticky="e", padx=(18, 18))
    except Exception:
        controls.pack(side=left, padx=(18, 18), fill=x_fill)

    combined = ttk.Button(
        controls,
        text=_RUN_TEXT,
        style=_HEADER_RUN_STYLE,
        command=gui._start_analysis,
    )
    combined.pack(side=left, padx=(0, 6))
    gui.run_stop_button = combined
    gui.run_button = _RunStopButtonProxy(gui, combined, "run")
    gui.stop_button = _RunStopButtonProxy(gui, combined, "stop")

    initial_mode = _MODE_RUNNING if stop_state == "normal" or run_state == "disabled" else _MODE_IDLE
    _set_run_stop_button_mode(gui, initial_mode)

    ttk.Button(
        controls,
        text="Open output",
        command=gui._open_output_folder,
    ).pack(side=left, padx=(0, 6))
    ttk.Button(
        controls,
        text="Geometry viewer",
        command=gui._open_geometry_viewer_overview,
    ).pack(side=left)

    gui._header_control_row = controls
    gui._main_control_buttons_in_header = True


def _coerce_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return bool(value)
