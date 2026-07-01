"""Shared data models for the ODB++ clearance analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


ProgressCallback = Callable[[str], None]


class AnalysisCancelled(RuntimeError):
    """Raised when a GUI/CLI caller requests cooperative cancellation."""


@dataclass(frozen=True)
class SymbolDef:
    """Parsed ODB++ aperture/symbol definition.

    ODB++ symbol dimensions are normally expressed in micrometres even when file
    coordinates use millimetres. The parser converts these dimensions to mm.
    """

    index: int
    raw_name: str
    kind: str
    width_mm: float
    height_mm: float | None = None
    radius_mm: float | None = None

    @property
    def diameter_mm(self) -> float:
        return self.width_mm


@dataclass(frozen=True)
class FeatureRecord:
    """Single ODB++ feature record from a physical layer.

    `raw_attributes` stores the ODB++ feature attribute suffix exactly as found
    after the semicolon, for example `0=5,3=0.3`. `decoded_attributes` maps the
    attribute IDs through the feature-file `@` attribute-name table and resolves
    integer values through the `&` text-string table where possible.
    """

    layer: str
    index: int
    kind: str
    polarity: str
    symbol_name: str | None
    raw: str
    geometry: object | None
    raw_attributes: str = ""
    decoded_attributes: dict[str, str] = field(default_factory=dict)

    @property
    def decoded_attributes_text(self) -> str:
        """Return decoded attributes as a stable, human-readable string."""

        if not self.decoded_attributes:
            return ""
        return ", ".join(f"{key}={value}" for key, value in self.decoded_attributes.items())


@dataclass(frozen=True)
class NetInfo:
    """Net metadata from steps/<step>/eda/data."""

    net_number: int
    net_name: str


@dataclass(frozen=True)
class FeatureAttributeRecord:
    """One feature row with raw and decoded ODB++ attributes."""

    layer: str
    feature_index: int
    net: str
    feature_kind: str
    polarity: str
    symbol_name: str | None
    raw_attributes: str
    decoded_attributes: str
    raw_feature: str

    def as_row(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "feature_index": self.feature_index,
            "net": self.net,
            "feature_kind": self.feature_kind,
            "polarity": self.polarity,
            "symbol_name": self.symbol_name,
            "raw_attributes": self.raw_attributes,
            "decoded_attributes": self.decoded_attributes,
            "raw_feature": self.raw_feature,
        }


@dataclass(frozen=True)
class DrillLayerInfo:
    """ODB++ plated drill layer span information.

    `start_layer` and `end_layer` identify the copper layers connected by the
    drill layer when the exporter provides START_NAME/END_NAME in matrix/matrix.
    Through vias normally span from the first to the last signal layer.
    """

    name: str
    start_layer: str | None = None
    end_layer: str | None = None


@dataclass(frozen=True)
class ComponentOutlineRecord:
    """Estimated component contour and reference designator for geometry viewer overlay."""

    refdes: str
    side: str
    geometry: object
    center_x_mm: float
    center_y_mm: float
    source_layer: str
    source: str = "fab/courtyard"


@dataclass
class OdbJob:
    """Extracted ODB++ job metadata and geometry."""

    root: Path
    step_name: str
    signal_layers: list[str]
    nets_by_number: dict[int, str]
    feature_net_map: dict[tuple[str, int], str]
    features_by_layer: dict[str, list[FeatureRecord]]
    drill_layers: list[DrillLayerInfo] = field(default_factory=list)
    drill_features_by_layer: dict[str, list[FeatureRecord]] = field(default_factory=dict)
    pcb_outline_geometry: object | None = field(default=None, repr=False)
    pcb_outline_source: str | None = None
    component_outlines: list[ComponentOutlineRecord] = field(default_factory=list)
    source_path: Path | None = None

    @property
    def named_nets(self) -> set[str]:
        return {name for name in self.nets_by_number.values() if name != "$NONE$"}

    def iter_feature_attributes(self, include_empty: bool = False) -> Iterable[FeatureAttributeRecord]:
        """Yield decoded feature attribute rows for reports and GUI display."""

        for layer, features in self.features_by_layer.items():
            for feature in features:
                if not include_empty and not feature.raw_attributes and not feature.decoded_attributes:
                    continue
                net = self.feature_net_map.get((layer.lower(), feature.index), "$NONE$")
                yield FeatureAttributeRecord(
                    layer=layer,
                    feature_index=feature.index,
                    net=net,
                    feature_kind=feature.kind,
                    polarity=feature.polarity,
                    symbol_name=feature.symbol_name,
                    raw_attributes=feature.raw_attributes,
                    decoded_attributes=feature.decoded_attributes_text,
                    raw_feature=feature.raw,
                )


@dataclass
class AnalysisConfig:
    """Configuration for one net-to-net clearance analysis run."""

    odb_path: Path
    output_dir: Path
    threshold_mm: float = 0.15
    include_none_net: bool = False
    layers: list[str] | None = None
    top_critical_limit: int = 1000
    geometry_resolution: int = 16
    precision_grid_mm: float | None = 0.000001
    debug_limit: int = 500
    debug_probe_radius_mm: float = 0.002
    effective_air_gap_matrix: bool = False
    cti: float = 175.0
    pollution_degree: int = 2
    altitude_m: float = 5500.0
    layer_roles: dict[str, str] = field(default_factory=dict)
    layer_pollution_degrees: dict[str, int] = field(default_factory=dict)
    external_conformal_coating: bool = False
    metallic_particle_size_mm: float = 0.0
    export_effective_max_voltage: bool = True
    export_ipc2221a_max_voltage: bool = True




@dataclass(frozen=True)
class EffectiveAirGapRecord:
    """Pairwise effective straight-line non-copper gap between two nets.

    `direct_clearance_mm` is the ordinary Shapely copper-to-copper spacing.
    `effective_air_gap_mm` measures the same closest-point line but subtracts
    copper occupied by any *other* net along that line. This is useful when the
    user wants to know how much non-copper distance exists between two nets if
    intermediate copper islands/pours split the line-of-sight path.

    It is still a straight-line diagnostic, not a full IEC creepage path solver.
    """

    layer: str
    net_a: str
    net_b: str
    direct_clearance_mm: float
    effective_air_gap_mm: float
    copper_blocked_length_mm: float
    copper_on_path: bool
    blocker_nets: str = ""
    effective_max_voltage_v: float | None = None
    ipc2221a_max_voltage_v: float | None = None
    x_a_mm: float | None = None
    y_a_mm: float | None = None
    x_b_mm: float | None = None
    y_b_mm: float | None = None

    def as_row(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "net_a": self.net_a,
            "net_b": self.net_b,
            "direct_clearance_mm": self.direct_clearance_mm,
            "effective_air_gap_mm": self.effective_air_gap_mm,
            "copper_blocked_length_mm": self.copper_blocked_length_mm,
            "copper_on_path": self.copper_on_path,
            "blocker_nets": self.blocker_nets,
            "effective_max_voltage_v": self.effective_max_voltage_v,
            "ipc2221a_max_voltage_v": self.ipc2221a_max_voltage_v,
            "x_a_mm": self.x_a_mm,
            "y_a_mm": self.y_a_mm,
            "x_b_mm": self.x_b_mm,
            "y_b_mm": self.y_b_mm,
        }


@dataclass(frozen=True)
class MeasurementRecord:
    """Minimum spacing between two nets on one copper layer."""

    layer: str
    net_a: str
    net_b: str
    clearance_mm: float
    x_a_mm: float | None = None
    y_a_mm: float | None = None
    x_b_mm: float | None = None
    y_b_mm: float | None = None
    effective_max_voltage_v: float | None = None
    ipc2221a_max_voltage_v: float | None = None

    def as_row(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "net_a": self.net_a,
            "net_b": self.net_b,
            "clearance_mm": self.clearance_mm,
            "x_a_mm": self.x_a_mm,
            "y_a_mm": self.y_a_mm,
            "x_b_mm": self.x_b_mm,
            "y_b_mm": self.y_b_mm,
            "effective_max_voltage_v": self.effective_max_voltage_v,
            "ipc2221a_max_voltage_v": self.ipc2221a_max_voltage_v,
        }


@dataclass(frozen=True)
class PerNetMinimum:
    """Worst minimum clearance involving one net."""

    net: str
    min_clearance_mm: float
    layer: str
    other_net: str
    x_this_mm: float | None = None
    y_this_mm: float | None = None
    x_other_mm: float | None = None
    y_other_mm: float | None = None
    effective_max_voltage_v: float | None = None
    ipc2221a_max_voltage_v: float | None = None

    def as_row(self) -> dict[str, object]:
        return {
            "net": self.net,
            "min_clearance_mm": self.min_clearance_mm,
            "layer": self.layer,
            "other_net": self.other_net,
            "x_this_mm": self.x_this_mm,
            "y_this_mm": self.y_this_mm,
            "x_other_mm": self.x_other_mm,
            "y_other_mm": self.y_other_mm,
            "effective_max_voltage_v": self.effective_max_voltage_v,
            "ipc2221a_max_voltage_v": self.ipc2221a_max_voltage_v,
        }


@dataclass(frozen=True)
class FeatureDebugHit:
    """Source ODB++ feature near one reported closest point.

    These records are intended for troubleshooting false 0 mm results.  The
    closest points reported by Shapely are generated geometry points, so this
    class links those points back to nearby/intersecting ODB++ feature lines.
    """

    layer: str
    net: str
    feature_index: int
    feature_kind: str
    polarity: str
    symbol_name: str | None
    distance_to_point_mm: float | None
    intersects_probe: bool
    bounds_mm: str
    area_mm2: float | None
    raw_attributes: str
    decoded_attributes: str
    raw_feature: str

    def compact(self) -> str:
        distance = "N/A" if self.distance_to_point_mm is None else f"{self.distance_to_point_mm:.6f}mm"
        symbol = self.symbol_name or ""
        attrs = self.decoded_attributes or self.raw_attributes
        return (
            f"#{self.feature_index} {self.feature_kind}/{self.polarity} {symbol} "
            f"d={distance} bounds={self.bounds_mm} attrs={attrs}"
        )


@dataclass(frozen=True)
class GeometryDebugRecord:
    """Diagnostic information for a critical/zero-clearance net-pair result."""

    layer: str
    net_a: str
    net_b: str
    clearance_mm: float
    x_a_mm: float | None
    y_a_mm: float | None
    x_b_mm: float | None
    y_b_mm: float | None
    relation: str
    intersection_area_mm2: float | None
    intersection_length_mm: float | None
    geom_a_type: str
    geom_b_type: str
    geom_a_bounds_mm: str
    geom_b_bounds_mm: str
    zero_clearance_kind: str
    feature_hits_a: list[FeatureDebugHit] = field(default_factory=list)
    feature_hits_b: list[FeatureDebugHit] = field(default_factory=list)
    negative_hits: list[FeatureDebugHit] = field(default_factory=list)
    notes: str = ""

    def as_row(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "net_a": self.net_a,
            "net_b": self.net_b,
            "clearance_mm": self.clearance_mm,
            "x_a_mm": self.x_a_mm,
            "y_a_mm": self.y_a_mm,
            "x_b_mm": self.x_b_mm,
            "y_b_mm": self.y_b_mm,
            "relation": self.relation,
            "intersection_area_mm2": self.intersection_area_mm2,
            "intersection_length_mm": self.intersection_length_mm,
            "geom_a_type": self.geom_a_type,
            "geom_b_type": self.geom_b_type,
            "geom_a_bounds_mm": self.geom_a_bounds_mm,
            "geom_b_bounds_mm": self.geom_b_bounds_mm,
            "zero_clearance_kind": self.zero_clearance_kind,
            "feature_hits_a": " | ".join(hit.compact() for hit in self.feature_hits_a),
            "feature_hits_b": " | ".join(hit.compact() for hit in self.feature_hits_b),
            "negative_hits_near_point": " | ".join(hit.compact() for hit in self.negative_hits),
            "notes": self.notes,
        }


@dataclass
class AnalysisResult:
    """Complete analysis output."""

    config: AnalysisConfig
    job: OdbJob
    measurements: list[MeasurementRecord]
    per_net_minimum: list[PerNetMinimum]
    critical_measurements: list[MeasurementRecord]
    layer_net_counts: dict[str, int]
    geometry_debug_records: list[GeometryDebugRecord] = field(default_factory=list)
    effective_air_gap_records: list[EffectiveAirGapRecord] = field(default_factory=list)
    skipped_features: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    report_files: dict[str, Path] = field(default_factory=dict)
    net_geometry_by_layer: dict[str, dict[str, object]] = field(default_factory=dict, repr=False)
    via_geometry_by_layer: dict[str, dict[str, object]] = field(default_factory=dict, repr=False)

    @property
    def named_net_count(self) -> int:
        return len({m.net_a for m in self.measurements} | {m.net_b for m in self.measurements})

    @property
    def measurement_count(self) -> int:
        return len(self.measurements)

    @property
    def critical_count(self) -> int:
        return len(self.critical_measurements)

    @property
    def feature_attribute_count(self) -> int:
        return sum(1 for _ in self.job.iter_feature_attributes(include_empty=False))

    @property
    def minimum_clearance_mm(self) -> float | None:
        if not self.measurements:
            return None
        return min(m.clearance_mm for m in self.measurements)

    def iter_report_paths(self) -> Iterable[Path]:
        return self.report_files.values()
