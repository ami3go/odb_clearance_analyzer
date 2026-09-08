"""JSON settings profile helpers for ODB++ Clearance Analyzer."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AnalysisConfig

SETTINGS_SCHEMA_VERSION = 1
DEFAULT_SETTINGS_FILENAME = "analysis_settings.json"


def analysis_config_to_profile(
    config: AnalysisConfig,
    *,
    app_version: str = "",
    include_paths: bool = True,
    source: str = "analysis",
) -> dict[str, Any]:
    """Convert AnalysisConfig into a stable JSON-compatible settings profile."""

    data: dict[str, Any] = {
        "schema": "odb_clearance_analyzer_settings",
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "app_version": app_version,
        "source": source,
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "threshold_mm": float(config.threshold_mm),
            "include_none_net": bool(config.include_none_net),
            "layers": list(config.layers) if config.layers is not None else None,
            "top_critical_limit": int(config.top_critical_limit),
            "geometry_resolution": int(config.geometry_resolution),
            "precision_grid_mm": config.precision_grid_mm,
            "debug_limit": int(config.debug_limit),
            "debug_probe_radius_mm": float(config.debug_probe_radius_mm),
            "effective_air_gap_matrix": bool(config.effective_air_gap_matrix),
            "cti": float(config.cti),
            "pollution_degree": int(config.pollution_degree),
            "altitude_m": float(config.altitude_m),
            "layer_roles": dict(config.layer_roles),
            "layer_pollution_degrees": {str(k): int(v) for k, v in dict(config.layer_pollution_degrees).items()},
            "external_conformal_coating": bool(config.external_conformal_coating),
            "metallic_particle_size_mm": float(config.metallic_particle_size_mm),
            "export_effective_max_voltage": bool(config.export_effective_max_voltage),
            "export_ipc2221a_max_voltage": bool(config.export_ipc2221a_max_voltage),
            "isolation_settings": dict(getattr(config, "isolation_settings", {}) or {}),
            "voltage_guessing": dict(getattr(config, "voltage_guessing", {}) or {"assignment_store_path": "net_voltage_assignments.json", "max_cell_voltage_v": 4.3, "galvanic_zone_voltage_v": 1000.0, "zone_to_zone_voltage_v": 1000.0, "galvanic_zones_supported": ["Zone 1", "Zone 2"]}),
        },
    }
    if include_paths:
        data["settings"]["odb_path"] = str(config.odb_path)
        data["settings"]["output_dir"] = str(config.output_dir)
    return data


def profile_to_analysis_config(profile: dict[str, Any], *, base_config: AnalysisConfig | None = None) -> AnalysisConfig:
    """Build AnalysisConfig from a settings profile.

    Missing values are taken from *base_config* when supplied; otherwise from
    AnalysisConfig defaults where possible.
    """

    if "settings" not in profile or not isinstance(profile["settings"], dict):
        raise ValueError("Invalid settings profile: missing 'settings' object")
    settings = profile["settings"]

    def get(name: str, default: Any) -> Any:
        return settings.get(name, default)

    if base_config is None:
        odb_path = Path(str(get("odb_path", "")))
        output_dir = Path(str(get("output_dir", "clearance_report")))
        base_config = AnalysisConfig(odb_path=odb_path, output_dir=output_dir)

    return AnalysisConfig(
        odb_path=Path(str(get("odb_path", str(base_config.odb_path)))),
        output_dir=Path(str(get("output_dir", str(base_config.output_dir)))),
        threshold_mm=float(get("threshold_mm", base_config.threshold_mm)),
        include_none_net=bool(get("include_none_net", base_config.include_none_net)),
        layers=get("layers", base_config.layers),
        top_critical_limit=int(get("top_critical_limit", base_config.top_critical_limit)),
        geometry_resolution=int(get("geometry_resolution", base_config.geometry_resolution)),
        precision_grid_mm=get("precision_grid_mm", base_config.precision_grid_mm),
        debug_limit=int(get("debug_limit", base_config.debug_limit)),
        debug_probe_radius_mm=float(get("debug_probe_radius_mm", base_config.debug_probe_radius_mm)),
        effective_air_gap_matrix=bool(get("effective_air_gap_matrix", base_config.effective_air_gap_matrix)),
        cti=float(get("cti", base_config.cti)),
        pollution_degree=int(get("pollution_degree", base_config.pollution_degree)),
        altitude_m=float(get("altitude_m", base_config.altitude_m)),
        layer_roles={str(k): str(v) for k, v in dict(get("layer_roles", base_config.layer_roles)).items()},
        layer_pollution_degrees={str(k): int(v) for k, v in dict(get("layer_pollution_degrees", base_config.layer_pollution_degrees)).items()},
        external_conformal_coating=bool(get("external_conformal_coating", base_config.external_conformal_coating)),
        metallic_particle_size_mm=float(get("metallic_particle_size_mm", base_config.metallic_particle_size_mm)),
        export_effective_max_voltage=bool(get("export_effective_max_voltage", base_config.export_effective_max_voltage)),
        export_ipc2221a_max_voltage=bool(get("export_ipc2221a_max_voltage", base_config.export_ipc2221a_max_voltage)),
        isolation_settings=dict(get("isolation_settings", getattr(base_config, "isolation_settings", {}))),
        voltage_guessing=dict(get("voltage_guessing", getattr(base_config, "voltage_guessing", {"assignment_store_path": "net_voltage_assignments.json", "max_cell_voltage_v": 4.3, "galvanic_zone_voltage_v": 1000.0, "zone_to_zone_voltage_v": 1000.0, "galvanic_zones_supported": ["Zone 1", "Zone 2"]}))),
    )


def write_settings_profile(path: Path, profile: dict[str, Any]) -> Path:
    """Write a settings profile as pretty JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_settings_profile(path: Path) -> dict[str, Any]:
    """Read and validate a JSON settings profile."""

    profile = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise ValueError("Settings profile must be a JSON object")
    if profile.get("schema") != "odb_clearance_analyzer_settings":
        raise ValueError("Unsupported settings profile schema")
    return profile
