import pytest

tk = pytest.importorskip("tkinter")
from tkinter import messagebox, simpledialog  # noqa: E402


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


def test_zones_tab_can_reset_matrix_to_user_entered_value(root):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.gui_multi_zone import ZONE_LABELS, ZONE_MATRIX_KEY
    from odb_clearance_analyzer.gui_zone_reset_value import reset_matrix_to_entered_value

    gui = ClearanceGui(root)
    root.update_idletasks()

    assert hasattr(gui, "voltage_zone_reset_value")
    assert hasattr(gui, "voltage_zone_reset_value_row")
    texts = _widget_texts(gui.voltage_zone_reset_value_row)
    assert "Reset voltage, V" in texts
    assert "Reset all to value" in texts

    gui.voltage_zone_reset_value.set("425")
    reset_matrix_to_entered_value(__import__("odb_clearance_analyzer.gui", fromlist=["dummy"]), gui)

    for zone_a in ZONE_LABELS:
        for zone_b in ZONE_LABELS:
            expected = "0" if zone_a == zone_b else "425"
            assert str(gui.voltage_zone_matrix_vars[(zone_a, zone_b)].get()) == expected

    settings = gui._current_voltage_guessing_settings()
    matrix = settings[ZONE_MATRIX_KEY]
    assert settings["galvanic_zone_voltage_v"] == 425.0
    assert matrix["Zone 1"]["Zone 2"] == 425.0
    assert matrix["Zone 1"]["Zone 10"] == 425.0
    assert matrix["Zone 10"]["Zone 1"] == 425.0
    assert matrix["Zone 5"]["Zone 5"] == 0.0
