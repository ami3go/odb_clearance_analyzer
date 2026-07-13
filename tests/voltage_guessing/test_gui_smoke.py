"""GUI construction smoke test.

The v0.4.22 package shipped a startup crash (grid/pack mixing inside a
card frame) precisely because GUI construction was never executed in the
headless test environment. This test constructs the full ClearanceGui,
selects every notebook tab, and populates the voltage views, so any
geometry-manager or widget-construction error fails CI.

Skips automatically when tkinter or a display is unavailable; run under
Xvfb in headless environments (see docs).
"""

import sys

import pytest

tk = pytest.importorskip("tkinter")
from tkinter import messagebox, simpledialog  # noqa: E402


@pytest.fixture()
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:  # no display
        pytest.skip(f"No display available for Tk: {exc}")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture(autouse=True)
def _stub_modals(monkeypatch):
    """Modal dialogs block forever headless; record instead."""
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, name, lambda *a, **k: "ok")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "test")


def _walk_and_select_all_tabs(root) -> int:
    import tkinter.ttk as ttk

    count = 0
    stack = [root]
    while stack:
        widget = stack.pop()
        for child in widget.winfo_children():
            if isinstance(child, ttk.Notebook):
                for tab_id in child.tabs():
                    child.select(tab_id)
                    root.update_idletasks()
                    count += 1
            stack.append(child)
    return count


def test_gui_constructs_and_all_tabs_render(root):
    from odb_clearance_analyzer.gui import ClearanceGui

    gui = ClearanceGui(root)
    root.update_idletasks()
    tabs = _walk_and_select_all_tabs(root)
    assert tabs >= 15, f"expected all notebook tabs to render, got {tabs}"


def test_voltage_views_render_with_data(root):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service

    gui = ClearanceGui(root)
    pack = load_rule_pack()
    review_service.run_auto_detect(
        gui.voltage_store, ["GND", "3V3", "DC_LINK_800V", "L1", "MYSTERY"], pack
    )
    gui._refresh_voltage_views()
    root.update_idletasks()
    tree = gui.voltage_assignment_tree
    assert tree is not None and len(tree.get_children()) == 5
    kids = tree.get_children()
    tree.selection_set(kids[0])
    root.update_idletasks()
    gui._jump_to_voltage_assignment_from_viewer("GND")
    root.update_idletasks()


def test_voltage_assignment_bulk_edit_from_extended_selection(root):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service

    gui = ClearanceGui(root)
    pack = load_rule_pack()
    review_service.run_auto_detect(
        gui.voltage_store, ["GND", "3V3", "DC_LINK_800V", "L1", "MYSTERY"], pack
    )
    gui._refresh_voltage_views()
    root.update_idletasks()

    tree = gui.voltage_assignment_tree
    assert tree is not None
    tree.selection_set("L1", "MYSTERY")
    gui._on_voltage_assignment_selected()
    assert "2 selected" in gui.voltage_selected_net.get()

    gui.voltage_final_class.set("HIGH_VOLTAGE")
    gui.voltage_final_voltage.set("120")
    gui.voltage_review_state.set("Reviewed")
    gui.voltage_notes.set("bulk selected in All Assignments")
    gui._apply_voltage_manual_override()

    for net in ("L1", "MYSTERY"):
        assignment = gui.voltage_store.assignments[net]
        assert assignment.source == "manual"
        assert assignment.final_class == "HIGH_VOLTAGE"
        assert assignment.final_voltage_v == 120.0
        assert assignment.review_state == "Reviewed"
    assert gui.voltage_store.undo_stack[-1].operation == "manual_bulk_edit"
