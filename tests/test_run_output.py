from datetime import datetime
from pathlib import Path

from odb_clearance_analyzer.models import AnalysisConfig
from odb_clearance_analyzer.run_output import create_timestamped_report_dir, prepare_timestamped_analysis_output


def test_create_timestamped_report_dir_creates_unique_run_folder(tmp_path):
    first = create_timestamped_report_dir(tmp_path, now=datetime(2026, 9, 8, 18, 22, 33))
    second = create_timestamped_report_dir(tmp_path, now=datetime(2026, 9, 8, 18, 22, 33))

    assert first == tmp_path.resolve() / "run_20260908_182233"
    assert second == tmp_path.resolve() / "run_20260908_182233_001"
    assert first.is_dir()
    assert second.is_dir()


def test_prepare_timestamped_analysis_output_keeps_assignment_store_at_common_root(tmp_path):
    config = AnalysisConfig(odb_path=tmp_path / "board.zip", output_dir=tmp_path)

    run_dir = prepare_timestamped_analysis_output(config)

    assert run_dir.parent == tmp_path.resolve()
    assert run_dir.name.startswith("run_")
    assert Path(config.voltage_guessing["assignment_store_path"]) == tmp_path.resolve() / "net_voltage_assignments.json"
    assert config.voltage_guessing["report_root_dir"] == str(tmp_path.resolve())
