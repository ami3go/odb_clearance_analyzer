"""Net-to-net copper clearance analysis engine."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from .geometry import safe_union
from .models import (
    AnalysisCancelled,
    AnalysisConfig,
    AnalysisResult,
    EffectiveAirGapRecord,
    FeatureDebugHit,
    GeometryDebugRecord,
    MeasurementRecord,
    PerNetMinimum,
    ProgressCallback,
)
from .odb_parser import OdbParser
from .reports import ReportWriter
from .layer_rules import guess_layer_roles, normalize_layer_role
from .voltage_estimator import estimate_effective_max_voltage, estimate_ipc2221a_max_voltage


class ClearanceAnalyzer:
    """Analyze minimum same-layer copper spacing between all net pairs in an ODB++ job."""

    def __init__(self, progress: ProgressCallback | None = None, cancel_check=None):
        self.progress = progress or (lambda _message: None)
        self.cancel_check = cancel_check or (lambda: False)

    def _check_cancelled(self) -> None:
        """Raise AnalysisCancelled when the caller requested cooperative stop."""

        try:
            should_cancel = bool(self.cancel_check())
        except Exception:
            should_cancel = False
        if should_cancel:
            raise AnalysisCancelled("Analysis stopped by user.")

    def run(self, config: AnalysisConfig, write_reports: bool = True) -> AnalysisResult:
        """Run analysis and optionally write CSV/XLSX/Markdown reports."""

        config.output_dir = Path(config.output_dir).expanduser().resolve()
        config.output_dir.mkdir(parents=True, exist_ok=True)

        parser = OdbParser(geometry_resolution=config.geometry_resolution, progress=self.progress)
        try:
            job = parser.parse(config.odb_path)
            self._check_cancelled()
            selected_layers = config.layers or job.signal_layers
            selected_layers = [layer for layer in selected_layers if layer in job.features_by_layer]
            if not selected_layers:
                raise RuntimeError("No selected signal layers contain parsed feature geometry.")

            inferred_roles = guess_layer_roles(selected_layers)
            layer_roles = {
                layer: normalize_layer_role(config.layer_roles.get(layer, inferred_roles.get(layer, "external")))
                for layer in selected_layers
            }
            config.layer_roles = layer_roles
            if not config.layer_pollution_degrees:
                config.layer_pollution_degrees = {
                    layer: self._default_iec_pollution_degree(config, layer, role)
                    for layer, role in layer_roles.items()
                }
            else:
                config.layer_pollution_degrees = {
                    layer: min(4, max(1, int(config.layer_pollution_degrees.get(layer, self._default_iec_pollution_degree(config, layer, role)))))
                    for layer, role in layer_roles.items()
                }
            self.progress(
                "Layer roles: "
                + ", ".join(f"{layer}={role}" for layer, role in layer_roles.items())
            )
            self.progress(
                "IEC 60664-1 layer pollution degrees: "
                + ", ".join(f"{layer}=PD{pd}" for layer, pd in config.layer_pollution_degrees.items())
            )

            self._check_cancelled()
            self.progress("Building per-net copper geometry")
            net_geometry_by_layer, via_geometry_by_layer, layer_net_counts, skipped_features = self._build_net_geometry(
                job=job,
                layers=selected_layers,
                include_none_net=config.include_none_net,
                precision_grid_mm=config.precision_grid_mm,
                geometry_resolution=config.geometry_resolution,
            )

            self._check_cancelled()
            self.progress("Measuring minimum same-layer net-to-net clearances")
            measurements = self._measure_all_layers(net_geometry_by_layer, config=config)
            measurements.sort(key=lambda rec: (rec.clearance_mm, rec.layer, rec.net_a, rec.net_b))

            effective_air_gap_records = []
            if config.effective_air_gap_matrix:
                self.progress("Calculating Effective Net-to-Net distance matrix")
                effective_air_gap_records = self._measure_effective_air_gap_matrix(
                    net_geometry_by_layer=net_geometry_by_layer,
                    measurements=measurements,
                    config=config,
                )

            self._check_cancelled()
            critical = [m for m in measurements if m.clearance_mm < config.threshold_mm]
            critical.sort(key=lambda rec: rec.clearance_mm)
            per_net = self._build_per_net_minimum(measurements)

            self.progress("Building geometry debug diagnostics")
            geometry_debug_records = self._build_geometry_debug_records(
                job=job,
                net_geometry_by_layer=net_geometry_by_layer,
                records=critical[: config.debug_limit],
                probe_radius_mm=config.debug_probe_radius_mm,
            )

            result = AnalysisResult(
                config=config,
                job=job,
                measurements=measurements,
                per_net_minimum=per_net,
                critical_measurements=critical,
                layer_net_counts=layer_net_counts,
                geometry_debug_records=geometry_debug_records,
                effective_air_gap_records=effective_air_gap_records,
                skipped_features=skipped_features,
                warnings=[*parser.warnings],
                net_geometry_by_layer=net_geometry_by_layer,
                via_geometry_by_layer=via_geometry_by_layer,
            )

            if write_reports:
                self.progress("Writing reports")
                writer = ReportWriter(progress=self.progress)
                writer.write_all(result)

            self.progress("Analysis completed")
            return result
        finally:
            parser.close()

    def _build_net_geometry(
        self,
        job,
        layers: list[str],
        include_none_net: bool,
        precision_grid_mm: float | None,
        geometry_resolution: int,
    ):
        skipped_features: dict[str, int] = defaultdict(int)
        composited_negative_features: dict[str, int] = defaultdict(int)
        net_geometry_by_layer: dict[str, dict[str, object]] = {}
        via_geometry_by_layer: dict[str, dict[str, object]] = {}
        layer_net_counts: dict[str, int] = {}

        for layer in layers:
            self._check_cancelled()
            self.progress(f"Compositing copper geometry on {layer}")
            by_net: dict[str, object] = {}
            pending_positive_by_net: dict[str, list[object]] = defaultdict(list)
            features = job.features_by_layer.get(layer, [])

            def flush_pending_positive() -> None:
                """Union pending positive copper into the current layer framebuffer."""

                for net, geoms in list(pending_positive_by_net.items()):
                    positive_geom = safe_union(geoms, precision_grid_mm=precision_grid_mm)
                    if positive_geom is None or positive_geom.is_empty:
                        skipped_features[layer] += len(geoms)
                        continue
                    existing = by_net.get(net)
                    if existing is None:
                        by_net[net] = positive_geom
                    else:
                        by_net[net] = safe_union(
                            [existing, positive_geom],
                            precision_grid_mm=precision_grid_mm,
                        )
                pending_positive_by_net.clear()

            for feature_idx, feature in enumerate(features, start=1):
                if feature_idx % 1000 == 0:
                    self._check_cancelled()
                if feature.geometry is None or getattr(feature.geometry, "is_empty", True):
                    skipped_features[layer] += 1
                    continue

                polarity = feature.polarity.upper()
                if polarity == "P":
                    net = job.feature_net_map.get((layer.lower(), feature.index), "$NONE$")
                    if net == "$NONE$" and not include_none_net:
                        continue
                    pending_positive_by_net[net].append(feature.geometry)
                    continue

                # Negative/clear polarity features are copper-removal operations.
                # Earlier versions skipped them, which made large copper pours look
                # solid under anti-pads and produced false 0 mm overlaps to pads on
                # other nets. Apply them in file order to the copper accumulated so
                # far, matching CAM/Gerber-style polarity compositing closely enough
                # for clearance analysis. Positive features that appear after the
                # cutout remain copper, as they should.
                flush_pending_positive()
                composited_negative_features[layer] += 1
                for net_i, (net, geom) in enumerate(list(by_net.items()), start=1):
                    if net_i % 250 == 0:
                        self._check_cancelled()
                    try:
                        cut = geom.difference(feature.geometry)
                        if precision_grid_mm:
                            try:
                                from shapely import set_precision

                                cut = set_precision(cut, precision_grid_mm)
                            except Exception:
                                pass
                        if cut is None or cut.is_empty:
                            by_net.pop(net, None)
                        else:
                            if not cut.is_valid:
                                cut = cut.buffer(0)
                            by_net[net] = cut
                    except Exception:
                        skipped_features[layer] += 1

            flush_pending_positive()

            # Project plated through/blind via pad geometry onto this copper layer.
            # Some ODB++ exports put via holes in a separate DRILL layer and only
            # reference them from EDA data with FID H records.  Without this pass
            # the viewer can look like it has no vias, especially on internal
            # layers, and clearance around vias can be missed.
            via_by_net_for_layer = self._build_projected_via_geometry_for_layer(
                job=job,
                layer=layer,
                selected_layers=layers,
                include_none_net=include_none_net,
                precision_grid_mm=precision_grid_mm,
                geometry_resolution=geometry_resolution,
            )
            if via_by_net_for_layer:
                via_geometry_by_layer[layer] = via_by_net_for_layer
                self.progress(f"{layer}: projected plated vias for {len(via_by_net_for_layer)} net(s)")
            for net_i, (net, via_geom) in enumerate(via_by_net_for_layer.items(), start=1):
                if net_i % 250 == 0:
                    self._check_cancelled()
                if via_geom is None or getattr(via_geom, "is_empty", True):
                    continue
                existing = by_net.get(net)
                if existing is None:
                    by_net[net] = via_geom
                else:
                    by_net[net] = safe_union([existing, via_geom], precision_grid_mm=precision_grid_mm)

            # Final repair/pass after ordered compositing.
            repaired_by_net: dict[str, object] = {}
            for net_i, (net, geom) in enumerate(by_net.items(), start=1):
                if net_i % 250 == 0:
                    self._check_cancelled()
                repaired = safe_union([geom], precision_grid_mm=precision_grid_mm)
                if repaired is None or repaired.is_empty:
                    continue
                repaired_by_net[net] = repaired

            net_geometry_by_layer[layer] = repaired_by_net
            layer_net_counts[layer] = len(repaired_by_net)
            if composited_negative_features[layer]:
                self.progress(
                    f"{layer}: applied {composited_negative_features[layer]} negative/cutout features"
                )

        combined_skipped = dict(skipped_features)
        for layer, count in composited_negative_features.items():
            combined_skipped[f"{layer} negative/cutout features applied"] = count
        return net_geometry_by_layer, via_geometry_by_layer, layer_net_counts, combined_skipped

    def _drill_span_layers(self, job, drill) -> list[str]:
        """Return signal layers connected by one plated drill layer."""

        signal_layers = list(job.signal_layers)
        if not signal_layers:
            return []
        start = getattr(drill, "start_layer", None)
        end = getattr(drill, "end_layer", None)
        if start in signal_layers and end in signal_layers:
            i1 = signal_layers.index(start)
            i2 = signal_layers.index(end)
            lo, hi = sorted((i1, i2))
            return signal_layers[lo : hi + 1]
        # If span metadata is absent, assume plated drill connects all selected
        # copper layers. This is safer for viewer/debugging than hiding vias.
        return signal_layers

    def _build_projected_via_geometry_for_layer(
        self,
        job,
        layer: str,
        selected_layers: list[str],
        include_none_net: bool,
        precision_grid_mm: float | None,
        geometry_resolution: int,
    ) -> dict[str, object]:
        """Build plated-via copper pads that should appear on one signal layer."""

        via_by_net: dict[str, list[object]] = defaultdict(list)
        selected = set(selected_layers)
        for drill in getattr(job, "drill_layers", []):
            self._check_cancelled()
            span = [name for name in self._drill_span_layers(job, drill) if name in selected]
            if layer not in span:
                continue
            for feature_idx, feature in enumerate(job.drill_features_by_layer.get(drill.name, []), start=1):
                if feature_idx % 1000 == 0:
                    self._check_cancelled()
                if feature.geometry is None or getattr(feature.geometry, "is_empty", True):
                    continue
                if feature.polarity.upper() != "P":
                    continue
                net = job.feature_net_map.get((drill.name.lower(), feature.index), "$NONE$")
                if net == "$NONE$" and not include_none_net:
                    continue
                via_geom = self._via_pad_geometry_from_drill_feature(feature, geometry_resolution)
                if via_geom is not None and not via_geom.is_empty:
                    via_by_net[net].append(via_geom)

        merged: dict[str, object] = {}
        for net_i, (net, geoms) in enumerate(via_by_net.items(), start=1):
            if net_i % 250 == 0:
                self._check_cancelled()
            geom = safe_union(geoms, precision_grid_mm=precision_grid_mm)
            if geom is not None and not geom.is_empty:
                merged[net] = geom
        return merged

    def _via_pad_geometry_from_drill_feature(self, feature, geometry_resolution: int):
        """Infer copper pad geometry for a plated drill/via feature.

        Drill layers often store the hole diameter as the feature symbol.  When
        the feature attribute `.geometry` contains a via pad name such as
        `VIA_ROUNDD700000`, use that copper diameter instead.  If no pad-size
        attribute is available, fall back to the drill feature geometry so the
        viewer at least shows the via location.
        """

        geom = feature.geometry
        if geom is None or getattr(geom, "is_empty", True):
            return None
        center = geom.centroid
        diameter = self._via_pad_diameter_from_attributes(feature)
        if diameter is None:
            try:
                minx, miny, maxx, maxy = geom.bounds
                diameter = max(float(maxx - minx), float(maxy - miny))
            except Exception:
                diameter = None
        if diameter is None or diameter <= 0:
            return geom
        return Point(float(center.x), float(center.y)).buffer(diameter / 2.0, resolution=geometry_resolution)

    def _via_pad_diameter_from_attributes(self, feature) -> float | None:
        import re

        candidates = []
        try:
            candidates.extend(str(v) for v in feature.decoded_attributes.values())
        except Exception:
            pass
        candidates.append(feature.raw_attributes or "")
        candidates.append(feature.symbol_name or "")
        for text in candidates:
            # KiCad ODB++ text often uses VIA_ROUNDD700000 for a 0.700000 mm via pad.
            match = re.search(r"ROUND(?:D)?([0-9]{4,})", text, flags=re.IGNORECASE)
            if match:
                value = float(match.group(1))
                # Six-digit values are normally millimetres scaled by 1e6.
                if value >= 10000:
                    return value / 1_000_000.0
                return value * 0.001
            # Also accept generic r700/r700.0 style symbols.
            match = re.fullmatch(r"r([0-9.]+)", text.strip(), flags=re.IGNORECASE)
            if match:
                return float(match.group(1)) * 0.001
        return None

    def _default_iec_pollution_degree(self, config: AnalysisConfig, layer: str, role: str) -> int:
        """Return default IEC 60664-1 pollution degree for one layer.

        Internal layers default to PD1. External layers use the configured
        external/base pollution degree, unless external conformal coating is
        selected, in which case they default to PD2.
        """

        normalized_role = normalize_layer_role(role)
        if normalized_role == "internal":
            return 1
        if bool(getattr(config, "external_conformal_coating", False)):
            return 2
        try:
            return min(4, max(1, int(getattr(config, "pollution_degree", 2))))
        except Exception:
            return 2

    def _iec_pollution_degree_for_layer(self, config: AnalysisConfig, layer: str) -> int:
        """Return sanitized IEC 60664-1 pollution degree for one layer."""

        try:
            pd = int(config.layer_pollution_degrees.get(layer, config.pollution_degree))
        except Exception:
            pd = int(config.pollution_degree or 2)
        return min(4, max(1, pd))

    def _iec_effective_spacing_for_layer(self, config: AnalysisConfig, layer: str, spacing_mm: float) -> float:
        """Apply external-layer metallic-particle correction to measured spacing.

        Metallic particle size is treated conservatively: on external layers it
        reduces the effective available spacing, because a conductive particle can
        partially bridge the gap. Internal layers are not adjusted.
        """

        spacing = max(0.0, float(spacing_mm))
        role = str(config.layer_roles.get(layer, "external")).lower()
        if role == "internal":
            return spacing
        try:
            particle = max(0.0, float(config.metallic_particle_size_mm))
        except Exception:
            particle = 0.0
        return max(0.0, spacing - particle)

    def _measure_all_layers(
        self, net_geometry_by_layer: dict[str, dict[str, object]], config: AnalysisConfig | None = None
    ) -> list[MeasurementRecord]:
        if config is None:
            layer_roles = guess_layer_roles(list(net_geometry_by_layer.keys()))
            cti = 175.0
            pollution_degree = 2
            altitude_m = 5500.0
        else:
            layer_roles = config.layer_roles or guess_layer_roles(list(net_geometry_by_layer.keys()))
            cti = config.cti
            pollution_degree = config.pollution_degree
            altitude_m = config.altitude_m
        records: list[MeasurementRecord] = []
        for layer, by_net in net_geometry_by_layer.items():
            self._check_cancelled()
            nets = sorted(by_net.keys())
            total = len(nets) * (len(nets) - 1) // 2
            self.progress(f"Measuring {layer}: {len(nets)} nets, {total} pairs")
            pair_counter = 0
            for net_a, net_b in combinations(nets, 2):
                if pair_counter % 1000 == 0:
                    self._check_cancelled()
                geom_a = by_net[net_a]
                geom_b = by_net[net_b]
                try:
                    dist = float(geom_a.distance(geom_b))
                    point_a, point_b = nearest_points(geom_a, geom_b)
                    record = MeasurementRecord(
                        layer=layer,
                        net_a=net_a,
                        net_b=net_b,
                        clearance_mm=dist,
                        x_a_mm=point_a.x,
                        y_a_mm=point_a.y,
                        x_b_mm=point_b.x,
                        y_b_mm=point_b.y,
                        effective_max_voltage_v=estimate_effective_max_voltage(
                            self._iec_effective_spacing_for_layer(config, layer, dist) if config is not None else dist,
                            cti=cti,
                            pollution_degree=self._iec_pollution_degree_for_layer(config, layer) if config is not None else pollution_degree,
                            altitude_m=altitude_m,
                        ),
                        ipc2221a_max_voltage_v=estimate_ipc2221a_max_voltage(
                            dist,
                            layer_role=layer_roles.get(layer, "external"),
                            altitude_m=altitude_m,
                        ),
                    )
                    records.append(record)
                except Exception:
                    # Continue measuring other pairs; bad geometries are rare but can occur in imported jobs.
                    continue
                pair_counter += 1
                if pair_counter and pair_counter % 10000 == 0:
                    self.progress(f"{layer}: measured {pair_counter}/{total} pairs")
        return records


    def _measure_effective_air_gap_matrix(
        self,
        net_geometry_by_layer: dict[str, dict[str, object]],
        measurements: list[MeasurementRecord],
        config: AnalysisConfig | None = None,
    ) -> list[EffectiveAirGapRecord]:
        """Calculate effective straight-line non-copper gap for every measured pair.

        For each already-measured closest-point segment from Net A to Net B, this
        method intersects that line with the union of all copper on the same
        layer. Copper belonging to Net A and Net B is removed from the blocked
        length, then the remaining copper length is subtracted from the direct
        clearance. The result is a diagnostic "sum of air gaps" along that
        straight line when an intermediate copper island lies between the nets.

        This is not a routed creepage algorithm and it does not search around
        obstacles; it answers the practical question: "on the shortest line
        between these nets, how much of the line is non-copper?"
        """

        if config is None:
            layer_roles = guess_layer_roles(list(net_geometry_by_layer.keys()))
            cti = 175.0
            pollution_degree = 2
            altitude_m = 5500.0
        else:
            layer_roles = config.layer_roles or guess_layer_roles(list(net_geometry_by_layer.keys()))
            cti = config.cti
            pollution_degree = config.pollution_degree
            altitude_m = config.altitude_m

        by_layer_records: dict[str, list[MeasurementRecord]] = defaultdict(list)
        for rec in measurements:
            by_layer_records[rec.layer].append(rec)

        records: list[EffectiveAirGapRecord] = []
        tolerance = 1e-9
        for layer, layer_records in by_layer_records.items():
            self._check_cancelled()
            by_net = net_geometry_by_layer.get(layer, {})
            all_copper = safe_union(list(by_net.values()))
            if all_copper is None or getattr(all_copper, "is_empty", True):
                continue
            self.progress(f"Effective Net-to-Net distance {layer}: {len(layer_records)} pairs")
            for idx, rec in enumerate(layer_records, start=1):
                if idx % 1000 == 0:
                    self._check_cancelled()
                geom_a = by_net.get(rec.net_a)
                geom_b = by_net.get(rec.net_b)
                if geom_a is None or geom_b is None:
                    continue
                effective_gap = rec.clearance_mm
                blocked_len = 0.0
                blocker_nets_text = ""
                copper_on_path = False
                try:
                    if rec.x_a_mm is not None and rec.y_a_mm is not None and rec.x_b_mm is not None and rec.y_b_mm is not None:
                        line = LineString([(rec.x_a_mm, rec.y_a_mm), (rec.x_b_mm, rec.y_b_mm)])
                        line_len = float(line.length)
                        if line_len > tolerance:
                            pair_union = safe_union([geom_a, geom_b])
                            copper_on_line = line.intersection(all_copper)
                            pair_on_line = line.intersection(pair_union) if pair_union is not None else None
                            copper_len = float(getattr(copper_on_line, "length", 0.0) or 0.0)
                            pair_len = float(getattr(pair_on_line, "length", 0.0) or 0.0) if pair_on_line is not None else 0.0
                            blocked_len = max(0.0, min(line_len, copper_len - pair_len))
                            effective_gap = max(0.0, line_len - blocked_len)
                            copper_on_path = blocked_len > max(1e-6, line_len * 1e-6)
                            if copper_on_path:
                                blocker_nets_text = self._find_blocker_nets_on_line(
                                    line=line,
                                    by_net=by_net,
                                    exclude={rec.net_a, rec.net_b},
                                )
                except Exception:
                    effective_gap = rec.clearance_mm
                    blocked_len = 0.0
                    copper_on_path = False

                records.append(
                    EffectiveAirGapRecord(
                        layer=rec.layer,
                        net_a=rec.net_a,
                        net_b=rec.net_b,
                        direct_clearance_mm=rec.clearance_mm,
                        effective_air_gap_mm=effective_gap,
                        copper_blocked_length_mm=blocked_len,
                        copper_on_path=copper_on_path,
                        blocker_nets=blocker_nets_text,
                        effective_max_voltage_v=estimate_effective_max_voltage(
                            self._iec_effective_spacing_for_layer(config, rec.layer, effective_gap) if config is not None else effective_gap,
                            cti=cti,
                            pollution_degree=self._iec_pollution_degree_for_layer(config, rec.layer) if config is not None else pollution_degree,
                            altitude_m=altitude_m,
                        ),
                        ipc2221a_max_voltage_v=estimate_ipc2221a_max_voltage(
                            effective_gap,
                            layer_role=layer_roles.get(rec.layer, "external"),
                            altitude_m=altitude_m,
                        ),
                        x_a_mm=rec.x_a_mm,
                        y_a_mm=rec.y_a_mm,
                        x_b_mm=rec.x_b_mm,
                        y_b_mm=rec.y_b_mm,
                    )
                )
                if idx % 10000 == 0:
                    self.progress(f"{layer}: Effective Net-to-Net distance rows {idx}/{len(layer_records)}")
        records.sort(key=lambda rec: (rec.effective_air_gap_mm, rec.layer, rec.net_a, rec.net_b))
        return records

    def _find_blocker_nets_on_line(
        self,
        line: LineString,
        by_net: dict[str, object],
        exclude: set[str],
        limit: int = 12,
    ) -> str:
        """Return a compact list of other nets whose copper intersects the pair line."""

        names: list[str] = []
        minx, miny, maxx, maxy = line.bounds
        for net_i, (net, geom) in enumerate(by_net.items(), start=1):
            if net_i % 250 == 0:
                self._check_cancelled()
            if net in exclude or geom is None or getattr(geom, "is_empty", True):
                continue
            try:
                gx1, gy1, gx2, gy2 = geom.bounds
                if gx2 < minx or gx1 > maxx or gy2 < miny or gy1 > maxy:
                    continue
                inter = line.intersection(geom)
                if getattr(inter, "is_empty", True):
                    continue
                if float(getattr(inter, "length", 0.0) or 0.0) > 1e-9 or geom.distance(line) < 1e-9:
                    names.append(net)
                    if len(names) >= limit:
                        break
            except Exception:
                continue
        extra = "" if len(names) < limit else " ..."
        return ", ".join(names) + extra


    def _build_geometry_debug_records(
        self,
        job,
        net_geometry_by_layer: dict[str, dict[str, object]],
        records: list[MeasurementRecord],
        probe_radius_mm: float,
    ) -> list[GeometryDebugRecord]:
        """Create diagnostics linking critical measurements back to source features.

        A 0 mm Shapely distance only means the two reconstructed net geometries
        touch/intersect after compositing. This debug layer explains whether it
        is a point touch, area overlap, or likely artifact by showing original
        ODB++ features close to the reported point plus negative/cutout features
        near the same location.
        """

        feature_index = self._index_features_by_layer_and_net(job)
        debug: list[GeometryDebugRecord] = []
        for rec_i, rec in enumerate(records, start=1):
            if rec_i % 250 == 0:
                self._check_cancelled()
            by_net = net_geometry_by_layer.get(rec.layer, {})
            geom_a = by_net.get(rec.net_a)
            geom_b = by_net.get(rec.net_b)
            if geom_a is None or geom_b is None:
                continue

            relation = self._geometry_relation(geom_a, geom_b)
            intersection_area = None
            intersection_length = None
            zero_kind = "nonzero_clearance"
            notes: list[str] = []
            try:
                inter = geom_a.intersection(geom_b)
                if not inter.is_empty:
                    intersection_area = float(getattr(inter, "area", 0.0))
                    intersection_length = float(getattr(inter, "length", 0.0))
                    if intersection_area > 1e-12:
                        zero_kind = "area_overlap"
                        notes.append("Area overlap means the reconstructed copper bodies physically overlap; this is usually a parser/compositing issue unless the PCB really shorts these nets.")
                    else:
                        zero_kind = "touching_boundary"
                        notes.append("Zero distance with no area overlap usually means two reconstructed boundaries touch exactly.")
            except Exception as exc:
                notes.append(f"Could not calculate intersection: {exc}")

            point_a = self._make_point(rec.x_a_mm, rec.y_a_mm)
            point_b = self._make_point(rec.x_b_mm, rec.y_b_mm)
            mid_point = self._midpoint(point_a, point_b)
            if rec.clearance_mm == 0 and rec.x_a_mm == rec.x_b_mm and rec.y_a_mm == rec.y_b_mm:
                notes.append("Point A equals Point B: Shapely found touching or overlapping reconstructed geometry, not an original track coordinate.")

            hits_a = self._feature_hits_near_point(
                feature_index.get((rec.layer, rec.net_a), []), point_a or mid_point, probe_radius_mm, rec.net_a
            )
            hits_b = self._feature_hits_near_point(
                feature_index.get((rec.layer, rec.net_b), []), point_b or mid_point, probe_radius_mm, rec.net_b
            )
            negative_hits = self._feature_hits_near_point(
                feature_index.get((rec.layer, "__NEGATIVE__"), []), mid_point or point_a or point_b, max(probe_radius_mm, 0.01), "__NEGATIVE__"
            )
            if not negative_hits and rec.clearance_mm == 0:
                notes.append("No negative/cutout feature found near the reported point. If this is a pad inside a pour, the ODB++ export may not contain the isolation cutout, or the parser may not support the cutout feature type.")
            if not hits_a:
                notes.append(f"No original positive feature for {rec.net_a} was found near Point A within {probe_radius_mm:g} mm.")
            if not hits_b:
                notes.append(f"No original positive feature for {rec.net_b} was found near Point B within {probe_radius_mm:g} mm.")

            debug.append(
                GeometryDebugRecord(
                    layer=rec.layer,
                    net_a=rec.net_a,
                    net_b=rec.net_b,
                    clearance_mm=rec.clearance_mm,
                    x_a_mm=rec.x_a_mm,
                    y_a_mm=rec.y_a_mm,
                    x_b_mm=rec.x_b_mm,
                    y_b_mm=rec.y_b_mm,
                    relation=relation,
                    intersection_area_mm2=intersection_area,
                    intersection_length_mm=intersection_length,
                    geom_a_type=getattr(geom_a, "geom_type", type(geom_a).__name__),
                    geom_b_type=getattr(geom_b, "geom_type", type(geom_b).__name__),
                    geom_a_bounds_mm=self._bounds_text(geom_a),
                    geom_b_bounds_mm=self._bounds_text(geom_b),
                    zero_clearance_kind=zero_kind,
                    feature_hits_a=hits_a,
                    feature_hits_b=hits_b,
                    negative_hits=negative_hits,
                    notes=" ".join(notes),
                )
            )
        return debug

    def _index_features_by_layer_and_net(self, job) -> dict[tuple[str, str], list[object]]:
        index: dict[tuple[str, str], list[object]] = defaultdict(list)
        for layer, features in job.features_by_layer.items():
            for feature_idx, feature in enumerate(features, start=1):
                if feature_idx % 1000 == 0:
                    self._check_cancelled()
                if feature.geometry is None or getattr(feature.geometry, "is_empty", True):
                    continue
                if feature.polarity.upper() == "P":
                    net = job.feature_net_map.get((layer.lower(), feature.index), "$NONE$")
                    index[(layer, net)].append(feature)
                else:
                    index[(layer, "__NEGATIVE__")].append(feature)
        return index

    def _feature_hits_near_point(
        self,
        features: list[object],
        point: Point | None,
        probe_radius_mm: float,
        net: str,
        limit: int = 5,
    ) -> list[FeatureDebugHit]:
        if point is None:
            return []
        probe = point.buffer(probe_radius_mm) if probe_radius_mm > 0 else point
        hits: list[tuple[float, object, bool]] = []
        for feature in features:
            geom = getattr(feature, "geometry", None)
            if geom is None or getattr(geom, "is_empty", True):
                continue
            try:
                dist = float(geom.distance(point))
                intersects_probe = bool(geom.intersects(probe))
            except Exception:
                continue
            if intersects_probe or dist <= max(probe_radius_mm, 1e-9):
                hits.append((dist, feature, intersects_probe))
        hits.sort(key=lambda item: (item[0], getattr(item[1], "index", 0)))
        return [self._feature_debug_hit(feature, net, dist, intersects_probe) for dist, feature, intersects_probe in hits[:limit]]

    def _feature_debug_hit(self, feature, net: str, distance: float, intersects_probe: bool) -> FeatureDebugHit:
        geom = feature.geometry
        area = None
        try:
            area = float(getattr(geom, "area", 0.0))
        except Exception:
            pass
        return FeatureDebugHit(
            layer=feature.layer,
            net=net,
            feature_index=feature.index,
            feature_kind=feature.kind,
            polarity=feature.polarity,
            symbol_name=feature.symbol_name,
            distance_to_point_mm=distance,
            intersects_probe=intersects_probe,
            bounds_mm=self._bounds_text(geom),
            area_mm2=area,
            raw_attributes=feature.raw_attributes,
            decoded_attributes=feature.decoded_attributes_text,
            raw_feature=self._one_line(feature.raw),
        )

    def _geometry_relation(self, geom_a, geom_b) -> str:
        try:
            if geom_a.equals(geom_b):
                return "equal"
            if geom_a.overlaps(geom_b):
                return "overlaps"
            if geom_a.crosses(geom_b):
                return "crosses"
            if geom_a.touches(geom_b):
                return "touches"
            if geom_a.intersects(geom_b):
                return "intersects"
            return "disjoint"
        except Exception:
            return "unknown"

    def _make_point(self, x: float | None, y: float | None) -> Point | None:
        if x is None or y is None:
            return None
        return Point(float(x), float(y))

    def _midpoint(self, point_a: Point | None, point_b: Point | None) -> Point | None:
        if point_a is None and point_b is None:
            return None
        if point_a is None:
            return point_b
        if point_b is None:
            return point_a
        return Point((point_a.x + point_b.x) / 2.0, (point_a.y + point_b.y) / 2.0)

    def _bounds_text(self, geom) -> str:
        try:
            minx, miny, maxx, maxy = geom.bounds
            return f"({minx:.6f},{miny:.6f})-({maxx:.6f},{maxy:.6f})"
        except Exception:
            return ""

    def _one_line(self, text: str, limit: int = 500) -> str:
        compact = " ".join(text.split())
        if len(compact) > limit:
            return compact[: limit - 3] + "..."
        return compact

    def _build_per_net_minimum(self, measurements: list[MeasurementRecord]) -> list[PerNetMinimum]:
        best: dict[str, PerNetMinimum] = {}
        for rec in measurements:
            candidate_a = PerNetMinimum(
                net=rec.net_a,
                min_clearance_mm=rec.clearance_mm,
                layer=rec.layer,
                other_net=rec.net_b,
                x_this_mm=rec.x_a_mm,
                y_this_mm=rec.y_a_mm,
                x_other_mm=rec.x_b_mm,
                y_other_mm=rec.y_b_mm,
                effective_max_voltage_v=rec.effective_max_voltage_v,
                ipc2221a_max_voltage_v=rec.ipc2221a_max_voltage_v,
            )
            candidate_b = PerNetMinimum(
                net=rec.net_b,
                min_clearance_mm=rec.clearance_mm,
                layer=rec.layer,
                other_net=rec.net_a,
                x_this_mm=rec.x_b_mm,
                y_this_mm=rec.y_b_mm,
                x_other_mm=rec.x_a_mm,
                y_other_mm=rec.y_a_mm,
                effective_max_voltage_v=rec.effective_max_voltage_v,
                ipc2221a_max_voltage_v=rec.ipc2221a_max_voltage_v,
            )
            for candidate in (candidate_a, candidate_b):
                current = best.get(candidate.net)
                if current is None or candidate.min_clearance_mm < current.min_clearance_mm:
                    best[candidate.net] = candidate
        return sorted(best.values(), key=lambda item: (item.min_clearance_mm, item.net))
