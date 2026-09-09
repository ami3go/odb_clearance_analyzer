import pytest

tk = pytest.importorskip("tkinter")
from tkinter import messagebox, simpledialog  # noqa: E402
from tkinter import ttk  # noqa: E402


@pytest.fixture()
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No display available for Tk: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture(autouse=True)
def _stub_modals(monkeypatch):
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, name, lambda *a, **k: "ok")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "test")


def _tab_texts(notebook):
    return [str(notebook.tab(tab_id, "text")) for tab_id in notebook.tabs()]


def _widget_texts(widget):
    texts = []
    try:
        text = widget.cget("text")
    except Exception:
        text = ""
    if text:
        texts.append(str(text))
    for child in widget.winfo_children():
        texts.extend(_widget_texts(child))
    return texts


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def test_voltage_guessing_zones_tab_has_10x10_live_matrix(root):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.gui_multi_zone import ZONE_MATRIX_KEY
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service
    from odb_clearance_analyzer.voltage_guessing.requirements import (
        REQUIREMENT_SOURCE_GALVANIC_ZONE,
        VoltageRequirementResolver,
    )

    gui = ClearanceGui(root)
    root.update_idletasks()

    voltage_tabs = _tab_texts(gui.voltage_notebook)
    assert "Zones" in voltage_tabs
    assert voltage_tabs.index("Zones") == 1
    assert len(gui.voltage_zone_matrix_vars) == 100
    assert str(gui.voltage_zone_matrix_vars[("Zone 1", "Zone 1")].get()) == "0"
    assert str(gui.voltage_zone_matrix_vars[("Zone 1", "Zone 10")].get()) == "1000"

    entries = [widget for widget in _walk(gui.voltage_zone_matrix_table) if isinstance(widget, ttk.Entry)]
    assert len(entries) == 100
    assert "Zone 1 ↔ Zone 2 working voltage, V" not in _widget_texts(gui)

    zone_comboboxes = []
    for widget in _walk(gui):
        if isinstance(widget, ttk.Combobox):
            values = tuple(str(v) for v in widget.cget("values"))
            if "Zone 1" in values:
                zone_comboboxes.append(values)
    assert zone_comboboxes
    assert all("Zone 10" in values for values in zone_comboboxes)

    gui.voltage_zone_matrix_vars[("Zone 1", "Zone 3")].set("750")
    gui._apply_zone_to_zone_voltage_setting()
    settings = gui._current_voltage_guessing_settings()
    assert settings[ZONE_MATRIX_KEY]["Zone 1"]["Zone 3"] == 750.0
    assert settings[ZONE_MATRIX_KEY]["Zone 3"]["Zone 1"] == 750.0

    pack = load_rule_pack()
    review_service.run_auto_detect(gui.voltage_store, ["NET_A", "NET_B"], pack)
    gui.voltage_store.assignments["NET_A"].galvanic_zone = "Zone 1"
    gui.voltage_store.assignments["NET_B"].galvanic_zone = "Zone 3"

    req = VoltageRequirementResolver(gui.voltage_store.assignments, settings).resolve("NET_A", "NET_B")
    assert req.requirement_source == REQUIREMENT_SOURCE_GALVANIC_ZONE
    assert req.zone_a == "Zone 1"
    assert req.zone_b == "Zone 3"
    assert req.required_voltage_v == 750.0
