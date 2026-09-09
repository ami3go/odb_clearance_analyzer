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


def _is_descendant_of(widget, ancestor):
    current = widget
    while current is not None:
        if current is ancestor:
            return True
        current = getattr(current, "master", None)
    return False


def test_zones_tab_has_vertical_scroll_container(root):
    from odb_clearance_analyzer.gui import ClearanceGui

    gui = ClearanceGui(root)
    root.update_idletasks()

    assert hasattr(gui, "voltage_zones_scroll_canvas")
    assert hasattr(gui, "voltage_zones_vertical_scrollbar")
    assert hasattr(gui, "voltage_zones_scroll_body")
    assert isinstance(gui.voltage_zones_vertical_scrollbar, ttk.Scrollbar)
    assert str(gui.voltage_zones_vertical_scrollbar.cget("orient")) == "vertical"

    assert _is_descendant_of(gui.voltage_zone_matrix_table, gui.voltage_zones_scroll_body)
    assert _is_descendant_of(gui.voltage_zone_matrix_table, gui.voltage_zones_scroll_canvas)
    assert len(gui.voltage_zone_matrix_vars) == 100

    # Scrollbar must be wired to the canvas, not only present as decoration.
    yscroll = str(gui.voltage_zones_scroll_canvas.cget("yscrollcommand"))
    assert yscroll
    assert str(gui.voltage_zones_vertical_scrollbar.cget("command"))
