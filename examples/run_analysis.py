"""Minimal API example for ODB++ clearance analysis."""

from pathlib import Path

from odb_clearance_analyzer import AnalysisConfig, ClearanceAnalyzer


def main() -> None:
    config = AnalysisConfig(
        odb_path=Path("Reistor_switch-odb.zip"),
        output_dir=Path("clearance_report"),
        threshold_mm=0.6,
    )
    result = ClearanceAnalyzer(progress=print).run(config)
    print(f"Measured pairs: {result.measurement_count}")
    print(f"Critical pairs: {result.critical_count}")
    print(f"Minimum clearance: {result.minimum_clearance_mm:.6f} mm")


if __name__ == "__main__":
    main()
