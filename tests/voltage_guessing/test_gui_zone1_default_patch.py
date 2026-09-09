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


def test_default_zone1_checkbox_visible_and_applies_only_to_blank_zones(root, tmp_path):
    from odb_clearance_analyzer.gui import ClearanceGui
    from odb_clearance_analyzer.voltage_guessing import load_rule_pack, review_service
    from odb_clearance_analyzer.voltage_guessing.galvanic_zones import GALVANIC_ZONE_1, GALVANIC_ZONE_2

    gui = ClearanceGui(root)
    gui.output_dir.set(str(tmp_path))

    assert "Assign all unassigned nets to Zone 1 automatically" in _widget_texts(gui)
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


def test_main_action_buttons_are_in_header_with_combined_run_stop_button(root):
    from odb_clearance_analyzer.gui import ClearanceGui

    gui = ClearanceGui(root)

    assert getattr(gui, "_main_control_buttons_in_header", False) is True
    assert getattr(gui, "_header_control_row", None) is not None
    assert getattr(gui, "run_stop_button", None) is not None
    assert gui.run_stop_button.master is gui._header_control_row
    assert gui.run_button.master is gui._header_control_row
    assert gui.stop_button.master is gui._header_control_row
    assert str(gui.run_stop_button.cget("style")) == "HeaderRun.TButton"
    assert str(gui.run_stop_button.cget("text")) == "Run analysis"

    texts = _widget_texts(gui)
    assert texts.count("Run analysis") == 1
    assert texts.count("Stop") == 0
    assert texts.count("Open output") == 1
    assert texts.count("Geometry viewer") == 1

    # Old two-button state updates must drive the same visible button.
    gui.run_button.configure(state="disabled")
    gui.stop_button.configure(state="normal")
    assert str(gui.run_stop_button.cget("text")) == "Stop"
    assert str(gui.run_stop_button.cget("style")) == "Danger.TButton"
    assert str(gui.run_stop_button.cget("state")) == "normal"

    # Pressing Stop disables the same button while cancellation is requested.
    gui.stop_button.configure(state="disabled")
    assert str(gui.run_stop_button.cget("text")) == "Stop"
    assert str(gui.run_stop_button.cget("state")) == "disabled"

    # Finishing analysis returns the same button to Run mode.
    gui.run_button.configure(state="normal")
    assert str(gui.run_stop_button.cget("text")) == "Run analysis"
    assert str(gui.run_stop_button.cget("style")) == "HeaderRun.TButton"
    assert str(gui.run_stop_button.cget("state")) == "normal"
