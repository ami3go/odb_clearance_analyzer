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


def test_zone_matrix_top_duplicate_cells_are_masked(root):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.gui_multi_zone import ZONE_LABELS, ZONE_MATRIX_KEY
    from odb_clearance_analyzer.gui_zone_matrix_mask import MASK_TEXT

    gui = ClearanceGui(root)
    root.update_idletasks()

    assert hasattr(gui, "voltage_zone_matrix_masked_duplicate_entries")
    assert hasattr(gui, "voltage_zone_matrix_editable_entries")
    assert hasattr(gui, "voltage_zone_matrix_diagonal_entries")
    assert len(gui.voltage_zone_matrix_masked_duplicate_entries) == 45
    assert len(gui.voltage_zone_matrix_editable_entries) == 45
    assert len(gui.voltage_zone_matrix_diagonal_entries) == 10

    for (row, col), entry in gui.voltage_zone_matrix_masked_duplicate_entries.items():
        assert row < col
        assert str(entry.cget("state")) == "disabled"
        assert str(entry.get()) == MASK_TEXT

    for (row, col), entry in gui.voltage_zone_matrix_editable_entries.items():
        assert row > col
        assert str(entry.cget("state")) == "normal"

    for (row, col), entry in gui.voltage_zone_matrix_diagonal_entries.items():
        assert row == col
        assert str(entry.cget("state")) == "disabled"
        assert str(entry.get()) == "0"

    # Masking is visual only. The underlying matrix variables remain complete
    # and symmetric for resolver/export code. With top cells masked, the lower
    # triangle is the editable source of truth.
    gui.voltage_zone_matrix_vars[("Zone 4", "Zone 1")].set("640")
    settings = gui._current_voltage_guessing_settings()
    assert settings[ZONE_MATRIX_KEY]["Zone 1"]["Zone 4"] == 640.0
    assert settings[ZONE_MATRIX_KEY]["Zone 4"]["Zone 1"] == 640.0
    assert len(settings[ZONE_MATRIX_KEY]) == len(ZONE_LABELS)


def test_report_resolver_uses_visible_lower_triangle_zone_matrix_value(root):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.gui_multi_zone import ZONE_MATRIX_KEY
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service
    from odb_clearance_analyzer.voltage_guessing.requirements import (
        REQUIREMENT_SOURCE_GALVANIC_ZONE,
        VoltageRequirementResolver,
    )

    gui = ClearanceGui(root)
    root.update_idletasks()

    # The top cell is masked in the UI. The user-visible editable cell is the
    # lower-triangle mirror, and this is the value reports must receive.
    gui.voltage_zone_matrix_vars[("Zone 4", "Zone 1")].set("640")
    settings = gui._current_voltage_guessing_settings()
    assert settings[ZONE_MATRIX_KEY]["Zone 1"]["Zone 4"] == 640.0
    assert settings[ZONE_MATRIX_KEY]["Zone 4"]["Zone 1"] == 640.0

    pack = load_rule_pack()
    review_service.run_auto_detect(gui.voltage_store, ["NET_A", "NET_B"], pack)
    gui.voltage_store.assignments["NET_A"].galvanic_zone = "Zone 1"
    gui.voltage_store.assignments["NET_B"].galvanic_zone = "Zone 4"

    requirement = VoltageRequirementResolver(gui.voltage_store.assignments, settings).resolve("NET_A", "NET_B")
    assert requirement.requirement_source == REQUIREMENT_SOURCE_GALVANIC_ZONE
    assert requirement.zone_a == "Zone 1"
    assert requirement.zone_b == "Zone 4"
    assert requirement.required_voltage_v == 640.0
