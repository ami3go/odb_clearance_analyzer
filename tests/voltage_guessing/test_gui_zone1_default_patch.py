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


def test_default_zone1_checkbox_applies_only_to_blank_zones(root, tmp_path):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service
    from odb_clearance_analyzer.voltage_guessing.galvanic_zones import GALVANIC_ZONE_1, GALVANIC_ZONE_2

    gui = ClearanceGui(root)
    gui.output_dir.set(str(tmp_path))
    assert hasattr(gui, "voltage_default_all_nets_zone1")
    assert hasattr(gui, "_apply_default_all_nets_zone1_setting")

    pack = load_rule_pack()
    review_service.run_auto_detect(gui.voltage_store, ["GND", "3V3", "ISO_SIG"], pack)
    gui.voltage_store.assignments["ISO_SIG"].galvanic_zone = GALVANIC_ZONE_2

    gui.voltage_default_all_nets_zone1.set(True)
    gui._apply_default_all_nets_zone1_setting()

    assert gui.voltage_store.settings["default_all_nets_to_zone_1"] is True
    assert gui.voltage_store.assignments["GND"].galvanic_zone == GALVANIC_ZONE_1
    assert gui.voltage_store.assignments["3V3"].galvanic_zone == GALVANIC_ZONE_1
    assert gui.voltage_store.assignments["ISO_SIG"].galvanic_zone == GALVANIC_ZONE_2
