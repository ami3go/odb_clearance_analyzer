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


def test_zone_to_zone_voltage_setting_persists_before_assignments(root, tmp_path):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing.assignment_store import assignment_store_path, load_assignment_store

    gui = ClearanceGui(root)
    gui.output_dir.set(str(tmp_path))
    gui.voltage_galvanic_zone_voltage.set(1500.0)

    gui._apply_zone_to_zone_voltage_setting()

    store = load_assignment_store(assignment_store_path(tmp_path))
    assert store.assignments == {}
    assert store.settings["galvanic_zone_voltage_v"] == 1500.0
    assert store.settings["zone_to_zone_voltage_v"] == 1500.0


def test_apply_zone_voltage_does_not_erase_unloaded_existing_store(root, tmp_path):
    """Regression: applying the zone-to-zone voltage with a fresh GUI must not
    atomically replace an existing (not-yet-loaded) project store with the
    empty in-memory store, destroying reviewed assignments."""
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service
    from odb_clearance_analyzer.voltage_guessing.assignment_store import (
        assignment_store_path,
        create_assignment_store,
        load_assignment_store,
        save_assignment_store_atomic,
    )
    from odb_clearance_analyzer.voltage_guessing.models import AssignmentStore  # noqa: F401

    # A previous session left reviewed assignments in the output folder.
    previous = create_assignment_store([], settings={"galvanic_zone_voltage_v": 800.0})
    pack = load_rule_pack()
    review_service.run_auto_detect(previous, ["GND", "3V3", "DC_LINK_800V"], pack)
    save_assignment_store_atomic(previous, assignment_store_path(tmp_path))

    # Fresh GUI: pick the folder, apply the setting before reading metadata.
    gui = ClearanceGui(root)
    gui.output_dir.set(str(tmp_path))
    gui.voltage_galvanic_zone_voltage.set(1500.0)
    gui._apply_zone_to_zone_voltage_setting()

    store = load_assignment_store(assignment_store_path(tmp_path))
    assert set(store.assignments) == {"GND", "3V3", "DC_LINK_800V"}, "existing assignments must survive"
    assert store.settings["galvanic_zone_voltage_v"] == 1500.0
    assert store.settings["zone_to_zone_voltage_v"] == 1500.0
    # The GUI keeps the value the user entered, not the stale on-disk 800 V.
    assert float(gui.voltage_galvanic_zone_voltage.get()) == 1500.0


def test_apply_zone_voltage_refuses_to_overwrite_unreadable_store(root, tmp_path):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing.assignment_store import assignment_store_path

    path = assignment_store_path(tmp_path)
    path.write_text("{not valid json", encoding="utf-8")

    gui = ClearanceGui(root)
    gui.output_dir.set(str(tmp_path))
    gui.voltage_galvanic_zone_voltage.set(1500.0)
    gui._apply_zone_to_zone_voltage_setting()

    assert path.read_text(encoding="utf-8") == "{not valid json", "unreadable store must not be replaced"


def test_clear_analysis_views_preserves_voltage_assignment_table(root):
    """Regression: analysis/geometry refresh must not make All Assignments blank.

    Voltage assignments are user review data, not transient analysis rows.  The
    old _clear_views() helper deleted the assignment tree; after a user assigned
    voltages, opened geometry, and returned to All Assignments, the backing
    store still existed but the table could be visually empty.
    """
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service

    gui = ClearanceGui(root)
    pack = load_rule_pack()
    review_service.run_auto_detect(gui.voltage_store, ["GND", "10V", "21V"], pack)
    gui._refresh_voltage_views()
    root.update_idletasks()

    tree = gui.voltage_assignment_tree
    assert tree is not None
    assert len(tree.get_children()) == 3

    gui._clear_views()
    root.update_idletasks()

    assert set(tree.get_children()) == {"GND", "10V", "21V"}
    assert set(gui.voltage_assignments) == {"GND", "10V", "21V"}
