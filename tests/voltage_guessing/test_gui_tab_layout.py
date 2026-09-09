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


def _tab_texts(notebook):
    return [str(notebook.tab(tab_id, "text")) for tab_id in notebook.tabs()]


def _is_descendant_of(widget, ancestor):
    current = widget
    while current is not None:
        if current is ancestor:
            return True
        current = getattr(current, "master", None)
    return False


def test_main_report_tabs_are_reordered_and_debug_tabs_are_grouped(root):
    from odb_clearance_analyzer.gui import ClearanceGui

    gui = ClearanceGui(root)
    root.update_idletasks()

    main_tabs = _tab_texts(gui.notebook)
    assert main_tabs[:5] == [
        "Summary",
        "Settings",
        "Voltage Guessing",
        "IEC 60664-1",
        "IPC-2221A",
    ]
    assert main_tabs[-1] == "Debug"
    assert "Log" not in main_tabs
    assert "Feature attributes" not in main_tabs
    assert "Debug zero/overlap" not in main_tabs

    assert getattr(gui, "debug_notebook", None) is not None
    assert _tab_texts(gui.debug_notebook) == ["Log", "Feature attributes", "Debug zero"]

    # The nested tabs must contain the real live widgets used by refresh/log code,
    # not empty placeholder frames.
    assert _is_descendant_of(gui.log, gui.debug_notebook)
    assert _is_descendant_of(gui.feature_attr_tree, gui.debug_notebook)
    assert _is_descendant_of(gui.debug_tree, gui.debug_notebook)

    gui._append_log("nested debug log smoke")
    assert len(gui.log.get_children()) == 1
    assert gui.log.item(gui.log.get_children()[0], "values")[0].endswith("nested debug log smoke")
