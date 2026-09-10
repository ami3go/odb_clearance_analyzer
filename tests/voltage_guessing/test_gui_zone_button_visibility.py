from types import SimpleNamespace

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


def _walk(widget):
    try:
        children = list(widget.winfo_children())
    except Exception:
        children = []
    for child in children:
        yield child
        yield from _walk(child)


def _find_button(root, text):
    from tkinter import ttk

    for widget in _walk(root):
        if isinstance(widget, ttk.Button):
            try:
                if str(widget.cget("text")) == text:
                    return widget
            except Exception:
                pass
    return None


def _fake_result():
    job = SimpleNamespace(
        signal_layers=["L1"],
        component_outlines=[],
        features_by_layer={},
        feature_net_map={},
        pcb_outline_geometry=None,
    )
    return SimpleNamespace(
        net_geometry_by_layer={"L1": {}},
        via_geometry_by_layer={},
        job=job,
    )


def test_main_header_show_zones_button_uses_visible_contrast_style(root):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.gui_zone_button_visibility import ZONE_HEADER_BUTTON_STYLE

    gui = ClearanceGui(root)
    root.update_idletasks()

    button = getattr(gui, "zone_visualization_button", None)
    assert button is not None
    assert str(button.cget("text")) == "Show zones"
    assert str(button.cget("style")) == ZONE_HEADER_BUTTON_STYLE
    assert str(button.cget("style")) != "Primary.TButton"


def test_geometry_viewer_show_zones_button_uses_visible_viewer_style(root):
    from odb_clearance_analyzer.geometry_viewer import GeometryViewer
    from odb_clearance_analyzer.gui_zone_button_visibility import ZONE_VIEWER_BUTTON_STYLE

    viewer = GeometryViewer(root, _fake_result(), dark_theme=False)
    viewer.withdraw()
    root.update_idletasks()

    button = _find_button(viewer, "Show zones")
    assert button is not None
    assert str(button.cget("style")) == ZONE_VIEWER_BUTTON_STYLE

    viewer.destroy()
