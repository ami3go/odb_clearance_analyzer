"""Geometry viewer construction regressions."""

from pathlib import Path

import pytest


tk = pytest.importorskip("tkinter")
from tkinter import messagebox  # noqa: E402


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


def _sample_result(tmp_path):
    from shapely.geometry import box

    from odb_clearance_analyzer.models import AnalysisConfig, AnalysisResult, OdbJob

    job = OdbJob(
        root=tmp_path,
        step_name="pcb",
        signal_layers=["TOP"],
        nets_by_number={1: "GND", 2: "NET2"},
        feature_net_map={},
        features_by_layer={"TOP": []},
    )
    return AnalysisResult(
        config=AnalysisConfig(odb_path=tmp_path / "job.tgz", output_dir=tmp_path),
        job=job,
        measurements=[],
        per_net_minimum=[],
        critical_measurements=[],
        layer_net_counts={"TOP": 2},
        net_geometry_by_layer={"TOP": {"GND": box(0, 0, 1, 1), "NET2": box(2, 0, 3, 1)}},
    )


def test_geometry_viewer_constructs_with_voltage_assignment_button(root, tmp_path):
    from odb_clearance_analyzer.geometry_viewer import GeometryViewer

    jumped = []
    viewer = GeometryViewer(
        root,
        _sample_result(tmp_path),
        layer="TOP",
        net_a="GND",
        on_show_voltage_assignment=jumped.append,
    )
    root.update_idletasks()

    assert hasattr(viewer, "canvas")
    viewer._jump_to_voltage_assignment()
    assert jumped == ["GND"]

    viewer.destroy()
