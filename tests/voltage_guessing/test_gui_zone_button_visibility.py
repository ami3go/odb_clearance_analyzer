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


def _widget_texts(widget):
    texts = []
    try:
        text = widget.cget("text")
    except Exception:
        text = ""
    if text:
        texts.append(str(text))
    for child in getattr(widget, "winfo_children", lambda: [])():
        texts.extend(_widget_texts(child))
    return texts


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


def _buttons_in(parent):
    from tkinter import ttk

    return [widget for widget in getattr(parent, "winfo_children", lambda: [])() if isinstance(widget, ttk.Button)]


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


def test_main_header_buttons_share_one_visible_style_and_header_has_no_version(root):
    from odb_clearance_analyzer import __version__
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.gui_zone_button_visibility import APP_HEADER_TITLE, HEADER_BUTTON_STYLE

    gui = ClearanceGui(root)
    root.update_idletasks()

    assert root.title() == f"ODB++ Clearance Analyzer {__version__}"
    assert APP_HEADER_TITLE in _widget_texts(gui)
    assert f"{APP_HEADER_TITLE} {__version__}" not in _widget_texts(gui)

    header_buttons = {str(button.cget("text")): str(button.cget("style")) for button in _buttons_in(gui._header_control_row)}
    assert header_buttons["Run analysis"] == HEADER_BUTTON_STYLE
    assert header_buttons["Open output"] == HEADER_BUTTON_STYLE
    assert header_buttons["Geometry viewer"] == HEADER_BUTTON_STYLE
    assert header_buttons["Show zones"] == HEADER_BUTTON_STYLE
    assert len(set(header_buttons.values())) == 1


def test_geometry_viewer_show_zones_button_uses_normal_viewer_button_style(root):
    from odb_clearance_analyzer.geometry_viewer import GeometryViewer
    from odb_clearance_analyzer.gui_zone_button_visibility import VIEWER_BUTTON_STYLE

    viewer = GeometryViewer(root, _fake_result(), dark_theme=False)
    viewer.withdraw()
    root.update_idletasks()

    button = _find_button(viewer, "Show zones")
    assert button is not None
    assert str(button.cget("style")) == VIEWER_BUTTON_STYLE

    viewer.destroy()
