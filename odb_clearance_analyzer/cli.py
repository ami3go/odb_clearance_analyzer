"""Command-line interface for ODB++ clearance analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyzer import ClearanceAnalyzer
from .models import AnalysisConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="odb-clearance-analyzer",
        description="Measure same-layer ODB++ copper net-to-net clearance, decode ODB++ feature attributes, and export reports.",
    )
    parser.add_argument("odb_path", type=Path, help="ODB++ archive (.zip, .tgz, .tar.gz, .tar) or extracted ODB++ directory")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("clearance_report"),
        help="Output directory for reports",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=0.15,
        help="Critical clearance threshold in mm. Default: 0.15.",
    )
    parser.add_argument(
        "--include-none",
        action="store_true",
        help="Include ODB++ $NONE$ copper in the analysis",
    )
    parser.add_argument(
        "--cti",
        type=float,
        default=175.0,
        help="CTI used for Effective max voltage estimate. Default: 175.",
    )
    parser.add_argument(
        "--pollution-degree",
        type=int,
        default=2,
        choices=[1, 2, 3, 4],
        help="Pollution degree used for Effective max voltage estimate. Default: 2.",
    )
    parser.add_argument(
        "--altitude-m",
        type=float,
        default=5500.0,
        help="Altitude above sea level in metres for clearance correction. Default: 5500.",
    )

    parser.add_argument(
        "--external-conformal-coating",
        action="store_true",
        help="IEC 60664-1: auto-assign external layers as pollution degree 2.",
    )
    parser.add_argument(
        "--metallic-particle-size-mm",
        type=float,
        default=0.0,
        help="IEC 60664-1 screening correction: subtract this particle size from external-layer spacing. Default: 0.",
    )
    parser.add_argument(
        "--layer-pollution-degree",
        action="append",
        default=[],
        metavar="LAYER=1|2|3|4",
        help="Override IEC 60664-1 pollution degree for one layer. May be repeated.",
    )
    parser.add_argument(
        "--layers",
        nargs="+",
        default=None,
        help="Optional list of signal layer names to analyze, e.g. F.CU B.CU",
    )
    parser.add_argument(
        "--geometry-resolution",
        type=int,
        default=16,
        help="Circle/oval approximation resolution. Higher is more accurate but slower.",
    )
    parser.add_argument(
        "--debug-limit",
        type=int,
        default=500,
        help="Maximum number of critical pairs to include in geometry debug diagnostics.",
    )
    parser.add_argument(
        "--effective-air-gap-matrix",
        action="store_true",
        help=(
            "Also calculate the full pair matrix using effective non-copper air gap: "
            "the closest-point line minus copper from intermediate nets on that line."
        ),
    )
    parser.add_argument(
        "--layer-role",
        action="append",
        default=[],
        metavar="LAYER=internal|external",
        help=(
            "Override IPC-2221A layer role for one layer. May be repeated, "
            "for example --layer-role F.CU=external --layer-role Inner1=internal."
        ),
    )
    parser.add_argument(
        "--export-effective-max-voltage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include Effective max voltage V column in exported CSV/XLSX/Markdown files. Default: true.",
    )
    parser.add_argument(
        "--export-ipc2221a-max-voltage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include IPC-2221A max voltage V column in exported CSV/XLSX/Markdown files. Default: true.",
    )
    return parser


def _parse_layer_roles(items: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Invalid --layer-role value {item!r}; expected LAYER=internal|external")
        layer, role = item.split("=", 1)
        role = role.strip().lower()
        if role not in {"internal", "external"}:
            raise ValueError(f"Invalid layer role {role!r}; use internal or external")
        roles[layer.strip()] = role
    return roles


def _parse_layer_pollution_degrees(items: list[str]) -> dict[str, int]:
    degrees: dict[str, int] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Invalid --layer-pollution-degree value {item!r}; expected LAYER=1|2|3|4")
        layer, value = item.split("=", 1)
        try:
            pd = int(value.strip())
        except Exception as exc:
            raise ValueError(f"Invalid pollution degree {value!r}; use 1, 2, 3 or 4") from exc
        if pd not in {1, 2, 3, 4}:
            raise ValueError(f"Invalid pollution degree {pd!r}; use 1, 2, 3 or 4")
        degrees[layer.strip()] = pd
    return degrees


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def progress(message: str) -> None:
        print(message, flush=True)

    config = AnalysisConfig(
        odb_path=args.odb_path,
        output_dir=args.output,
        threshold_mm=args.threshold,
        include_none_net=args.include_none,
        layers=args.layers,
        geometry_resolution=args.geometry_resolution,
        debug_limit=args.debug_limit,
        effective_air_gap_matrix=args.effective_air_gap_matrix,
        cti=args.cti,
        pollution_degree=args.pollution_degree,
        altitude_m=args.altitude_m,
        layer_roles=_parse_layer_roles(args.layer_role),
        layer_pollution_degrees=_parse_layer_pollution_degrees(args.layer_pollution_degree),
        external_conformal_coating=args.external_conformal_coating,
        metallic_particle_size_mm=max(0.0, args.metallic_particle_size_mm),
        export_effective_max_voltage=args.export_effective_max_voltage,
        export_ipc2221a_max_voltage=args.export_ipc2221a_max_voltage,
    )
    try:
        result = ClearanceAnalyzer(progress=progress).run(config)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("\nAnalysis summary")
    print("----------------")
    print(f"Measured pairs: {result.measurement_count}")
    print(f"Critical below {result.config.threshold_mm:.3f} mm: {result.critical_count}")
    if result.minimum_clearance_mm is not None:
        print(f"Minimum clearance: {result.minimum_clearance_mm:.6f} mm")
    print(f"Electrical settings: CTI={result.config.cti:g}, pollution degree={result.config.pollution_degree}, altitude={result.config.altitude_m:g} m")
    if result.config.layer_roles:
        print("Layer roles: " + ", ".join(f"{layer}={role}" for layer, role in result.config.layer_roles.items()))
    if result.config.layer_pollution_degrees:
        print("IEC layer pollution degrees: " + ", ".join(f"{layer}=PD{pd}" for layer, pd in result.config.layer_pollution_degrees.items()))
    print(f"External conformal coating: {result.config.external_conformal_coating}")
    print(f"Metallic particle size mm: {result.config.metallic_particle_size_mm:g}")
    print(f"Export Effective max voltage V: {result.config.export_effective_max_voltage}")
    print(f"Export IPC-2221A max voltage V: {result.config.export_ipc2221a_max_voltage}")
    if result.effective_air_gap_records:
        print(f"Effective Net-to-Net distance rows: {len(result.effective_air_gap_records)}")
    print("Reports:")
    for label, path in result.report_files.items():
        print(f"  {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
