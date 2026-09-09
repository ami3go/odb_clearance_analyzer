from types import SimpleNamespace

import pytest

tk = pytest.importorskip("tkinter")
from tkinter import messagebox, simpledialog  # noqa: E402

pytest.importorskip("shapely")
from shapely.geometry import box  # noqa: E402


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


def _fake_result():
    job = SimpleNamespace(
        signal_layers=["L1"],
        component_outlines=[],
        features_by_layer={},
        feature_net_map={},
        pcb_outline_geometry=box(-0.5, -0.5, 4.5, 1.5),
    )
    return SimpleNamespace(
        net_geometry_by_layer={
            "L1": {
                "NET_Z1": box(0.0, 0.0, 1.0, 1.0),
                "NET_Z2": box(1.5, 0.0, 2.5, 1.0),
                "NET_NO_ZONE": box(3.0, 0.0, 4.0, 1.0),
            }
        },
        via_geometry_by_layer={},
        job=job,
    )


def test_geometry_viewer_show_zones_colors_all_visible_nets_by_assignment(root):
    from odb_clearance_analyzer.geometry_viewer import GeometryViewer
    from odb_clearance_analyzer.gui_zone_visualization import ZONE_COLORS

    root._odb_zone_assignment_provider = lambda: {
        "NET_Z1": SimpleNamespace(net_name="NET_Z1", galvanic_zone="Zone 1"),
        "NET_Z2": SimpleNamespace(net_name="NET_Z2", galvanic_zone="Zone 2"),
    }

    viewer = GeometryViewer(root, _fake_result(), dark_theme=False)
    viewer.withdraw()
    root.update_idletasks()

    assert "Show zones" in _widget_texts(viewer)
    viewer.show_zones()
    root.update_idletasks()

    roles = {net: role for net, _geom, role in viewer.selected_geometries()}
    assert roles == {
        "NET_NO_ZONE": "zone:unassigned",
        "NET_Z1": "zone:Zone 1",
        "NET_Z2": "zone:Zone 2",
    }
    assert bool(viewer.show_other_nets_var.get()) is True
    assert bool(viewer.show_component_pads_var.get()) is False
    assert bool(viewer.show_points_var.get()) is False

    _fill_1, outline_1 = viewer._style_for_role("zone:Zone 1")
    _fill_2, outline_2 = viewer._style_for_role("zone:Zone 2")
    assert outline_1 == ZONE_COLORS["Zone 1"]
    assert outline_2 == ZONE_COLORS["Zone 2"]
    assert outline_1 != outline_2
    assert "Zone view:" in viewer.status_var.get()

    viewer.destroy()


def test_main_gui_has_show_zones_button(root):
    from odb_clearance_analyzer.gui import ClearanceGui

    gui = ClearanceGui(root)
    root.update_idletasks()

    assert hasattr(gui, "zone_visualization_button")
    assert "Show zones" in _widget_texts(gui)
