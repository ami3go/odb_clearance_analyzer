"""ODB++ reader focused on net-assigned copper geometry."""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from shapely.geometry import Point

from .geometry import (
    safe_union,
    last_float_before_attributes,
    odb_pad_orientation_to_degrees,
    pad_geometry,
    parse_float,
    parse_symbol,
    arc_points,
    surface_geometry,
    track_geometry,
)
from .models import ComponentOutlineRecord, DrillLayerInfo, FeatureRecord, OdbJob, ProgressCallback, SymbolDef

_SIGNAL_TYPES = {"SIGNAL", "POWER_GROUND"}
class OdbParseError(RuntimeError):
    """Raised when an ODB++ job cannot be parsed."""


class OdbParser:
    """Parse ODB++ jobs exported as a directory or as a ZIP/TGZ/TAR archive.

    The parser currently targets ODB++ jobs that expose net-to-feature mapping in
    `steps/<step>/eda/data`, which is the layout used by KiCad's ODB++ export.
    Copper geometry is read from layer `features` files.
    """

    def __init__(self, geometry_resolution: int = 16, progress: ProgressCallback | None = None):
        self.geometry_resolution = geometry_resolution
        self.progress = progress or (lambda _message: None)
        self._temp_dirs: list[Path] = []
        self.warnings: list[str] = []

    def close(self) -> None:
        """Remove temporary extraction directories."""

        for path in self._temp_dirs:
            shutil.rmtree(path, ignore_errors=True)
        self._temp_dirs.clear()

    def parse(self, odb_path: Path | str) -> OdbJob:
        """Parse an ODB++ path and return a populated :class:`OdbJob`."""

        source_path = Path(odb_path).expanduser().resolve()
        root = self._prepare_root(source_path)
        root = self._normalize_root(root)
        self.progress(f"ODB++ root: {root}")

        step_name = self._find_step(root)
        self.progress(f"Selected step: {step_name}")
        signal_layers = self._read_signal_layers(root)
        drill_layers = self._read_drill_layers(root)
        pcb_outline_geometry, pcb_outline_source = self._parse_pcb_outline(root, step_name)
        component_outlines = self._parse_component_outlines(root, step_name)
        if pcb_outline_source:
            self.progress(f"PCB outline: {pcb_outline_source}")
        if component_outlines:
            self.progress(f"Component outlines: {len(component_outlines)}")
        if not signal_layers:
            raise OdbParseError("No signal/copper layers found in matrix/matrix")
        self.progress(f"Signal layers: {', '.join(signal_layers)}")
        if drill_layers:
            self.progress("Plated drill layers: " + ", ".join(layer.name for layer in drill_layers))

        eda_path = root / "steps" / step_name / "eda" / "data"
        if not eda_path.exists():
            raise OdbParseError(f"Missing EDA net data: {eda_path}")
        nets_by_number, feature_net_map = self._parse_eda_data(eda_path)
        self.progress(f"Nets in EDA data: {len(nets_by_number)}")

        features_by_layer: dict[str, list[FeatureRecord]] = {}
        for layer in signal_layers:
            layer_dir = root / "steps" / step_name / "layers" / layer.lower()
            if not layer_dir.exists():
                layer_dir = root / "steps" / step_name / "layers" / layer
            features_path = layer_dir / "features"
            if not features_path.exists():
                self.warnings.append(f"Missing features file for signal layer {layer}")
                continue
            self.progress(f"Parsing copper layer: {layer}")
            features_by_layer[layer] = self._parse_layer_features(features_path, layer)

        drill_features_by_layer: dict[str, list[FeatureRecord]] = {}
        for drill in drill_layers:
            layer_dir = root / "steps" / step_name / "layers" / drill.name.lower()
            if not layer_dir.exists():
                layer_dir = root / "steps" / step_name / "layers" / drill.name
            features_path = layer_dir / "features"
            if not features_path.exists():
                self.warnings.append(f"Missing features file for drill layer {drill.name}")
                continue
            self.progress(f"Parsing plated drill layer: {drill.name}")
            drill_features_by_layer[drill.name] = self._parse_layer_features(features_path, drill.name)

        return OdbJob(
            root=root,
            step_name=step_name,
            signal_layers=signal_layers,
            nets_by_number=nets_by_number,
            feature_net_map=feature_net_map,
            features_by_layer=features_by_layer,
            drill_layers=drill_layers,
            drill_features_by_layer=drill_features_by_layer,
            pcb_outline_geometry=pcb_outline_geometry,
            pcb_outline_source=pcb_outline_source,
            component_outlines=component_outlines,
            source_path=source_path,
        )

    def _prepare_root(self, source_path: Path) -> Path:
        if source_path.is_dir():
            return source_path
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        if self._is_zip_archive(source_path):
            extract_dir = Path(tempfile.mkdtemp(prefix="odb_clearance_"))
            self._temp_dirs.append(extract_dir)
            self.progress(f"Extracting ZIP archive: {source_path.name}")
            with zipfile.ZipFile(source_path, "r") as zf:
                zf.extractall(extract_dir)
            return extract_dir

        if self._is_tar_archive(source_path):
            extract_dir = Path(tempfile.mkdtemp(prefix="odb_clearance_"))
            self._temp_dirs.append(extract_dir)
            self.progress(f"Extracting TAR archive: {source_path.name}")
            try:
                with tarfile.open(source_path, "r:*") as tf:
                    self._safe_extract_tar(tf, extract_dir)
            except tarfile.TarError as exc:
                raise OdbParseError(f"Could not extract TAR/TGZ archive {source_path}: {exc}") from exc
            return extract_dir

        raise OdbParseError(
            "Unsupported input archive. Use an extracted ODB++ directory, .zip, .tgz, "
            ".tar.gz, or .tar archive."
        )

    def _is_zip_archive(self, source_path: Path) -> bool:
        return source_path.suffix.lower() == ".zip"

    def _is_tar_archive(self, source_path: Path) -> bool:
        name = source_path.name.lower()
        return name.endswith((".tgz", ".tar.gz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"))

    def _safe_extract_tar(self, tar: tarfile.TarFile, destination: Path) -> None:
        """Extract tar archives while rejecting path traversal entries."""

        destination = destination.resolve()
        for member in tar.getmembers():
            member_path = (destination / member.name).resolve()
            try:
                member_path.relative_to(destination)
            except ValueError as exc:
                raise OdbParseError(f"Unsafe archive member path: {member.name!r}") from exc

            if member.issym() or member.islnk():
                link_target = (member_path.parent / member.linkname).resolve()
                try:
                    link_target.relative_to(destination)
                except ValueError as exc:
                    raise OdbParseError(
                        f"Unsafe archive link target: {member.name!r} -> {member.linkname!r}"
                    ) from exc

        tar.extractall(destination)

    def _normalize_root(self, root: Path) -> Path:
        """Handle archives that contain one top-level job directory."""

        if (root / "steps").exists() and (root / "matrix" / "matrix").exists():
            return root
        candidates = [p for p in root.iterdir() if p.is_dir()]
        for candidate in candidates:
            if (candidate / "steps").exists() and (candidate / "matrix" / "matrix").exists():
                return candidate
        raise OdbParseError(f"Could not locate ODB++ steps/ and matrix/ directories under {root}")

    def _find_step(self, root: Path) -> str:
        matrix_path = root / "matrix" / "matrix"
        text = matrix_path.read_text(errors="ignore")
        match = re.search(r"STEP\s*\{[^}]*NAME=([^\n\r]+)", text, flags=re.IGNORECASE | re.S)
        if match:
            return match.group(1).strip().lower()
        steps_dir = root / "steps"
        steps = [p.name for p in steps_dir.iterdir() if p.is_dir()]
        if not steps:
            raise OdbParseError("No steps found")
        return steps[0]

    def _read_signal_layers(self, root: Path) -> list[str]:
        matrix_path = root / "matrix" / "matrix"
        text = matrix_path.read_text(errors="ignore")
        layers: list[str] = []
        for props in self._iter_matrix_layer_props(text):
            if props.get("TYPE", "").upper() in _SIGNAL_TYPES and props.get("NAME"):
                layers.append(props["NAME"])
        return layers

    def _read_drill_layers(self, root: Path) -> list[DrillLayerInfo]:
        """Return plated drill layers with their copper start/end span.

        KiCad and many CAM exports represent vias in a separate DRILL layer, e.g.
        `DRILL_PLATED_F.CU-B.CU`, rather than repeating via pads in every signal
        layer.  We parse these layers so the analyzer/viewer can project via
        copper onto every layer the plated hole connects.
        """

        matrix_path = root / "matrix" / "matrix"
        text = matrix_path.read_text(errors="ignore")
        drill_layers: list[DrillLayerInfo] = []
        for props in self._iter_matrix_layer_props(text):
            if props.get("TYPE", "").upper() != "DRILL" or not props.get("NAME"):
                continue
            name = props["NAME"]
            # Keep only plated board drill layers.  Non-plated mounting holes do
            # not create copper on all layers and should not be treated as vias.
            if props.get("CONTEXT", "").upper() == "BOARD" and "PLATED" in name.upper():
                drill_layers.append(
                    DrillLayerInfo(
                        name=name,
                        start_layer=props.get("START_NAME"),
                        end_layer=props.get("END_NAME"),
                    )
                )
        return drill_layers

    def _iter_matrix_layer_props(self, text: str) -> list[dict[str, str]]:
        blocks: list[dict[str, str]] = []
        for block in re.findall(r"LAYER\s*\{(.*?)\}", text, flags=re.IGNORECASE | re.S):
            props: dict[str, str] = {}
            for line in block.splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                props[key.strip().upper()] = value.strip()
            blocks.append(props)
        return blocks

    _REFDES_RE = re.compile(r"^(?:R|RN|C|U|Q|D|J|P|H|L|TP|SW|S|Y|F|K|RV|RZ|FB|X)\d+[A-Z0-9_\\-]*$", re.IGNORECASE)

    def _parse_component_outlines(self, root: Path, step_name: str) -> list[ComponentOutlineRecord]:
        """Estimate component contours and reference designators for viewer overlay.

        Many ODB++ exports do not provide a direct "component outline" object in a
        uniform place.  This method uses common KiCad/ODB++ fabrication data:
        reference designator strings from fab/silkscreen layers and component
        contours from courtyard/fab geometry.  The result is a visual aid only and
        is not used by clearance calculations.
        """

        step_root = root / "steps" / step_name
        layers_dir = step_root / "layers"
        records: list[ComponentOutlineRecord] = []
        for side, prefixes in (("top", ("f", "top")), ("bottom", ("b", "bottom"))):
            ref_layers = self._candidate_existing_layers(layers_dir, prefixes, ("fab", "silkscreen", "silk", "ss"))
            contour_layers = self._candidate_existing_layers(layers_dir, prefixes, ("courtyard", "fab"))
            refs = self._collect_reference_texts(ref_layers)
            contours = self._collect_component_contours(contour_layers)
            records.extend(self._match_refs_to_contours(refs, contours, side))
        return records

    def _candidate_existing_layers(self, layers_dir: Path, prefixes: tuple[str, ...], suffixes: tuple[str, ...]) -> list[Path]:
        """Return layer feature files matching common side/suffix names."""

        result: list[Path] = []
        if not layers_dir.exists():
            return result
        all_layer_dirs = [p for p in layers_dir.iterdir() if p.is_dir()]
        for layer_dir in all_layer_dirs:
            name = layer_dir.name.lower()
            parts = re.split(r"[._+\\-]+", name)
            prefix_match = any(name.startswith(prefix + ".") or name.startswith(prefix + "_") or name == prefix for prefix in prefixes)
            suffix_match = any(suffix in parts or name.endswith("." + suffix) or name.endswith("_" + suffix) for suffix in suffixes)
            if prefix_match and suffix_match and (layer_dir / "features").exists():
                result.append(layer_dir / "features")
        # Prefer courtyard before fab for contours, fab before silkscreen for text.
        return sorted(result, key=lambda p: p.parent.name.lower())

    def _collect_reference_texts(self, feature_paths: list[Path]) -> dict[str, object]:
        """Collect reference designator text geometry from fab/silkscreen features."""

        by_ref: dict[str, list[object]] = {}
        for path in feature_paths:
            layer_name = path.parent.name
            try:
                features = self._parse_layer_features(path, layer_name)
            except Exception as exc:
                self.warnings.append(f"Could not parse component reference layer {path}: {exc}")
                continue
            for feature in features:
                ref = self._feature_refdes(feature)
                if not ref:
                    continue
                geom = feature.geometry
                if geom is None or getattr(geom, "is_empty", True):
                    continue
                by_ref.setdefault(ref, []).append(geom)

        result: dict[str, object] = {}
        for ref, geoms in by_ref.items():
            geom = safe_union(geoms)
            if geom is not None and not getattr(geom, "is_empty", True):
                result[ref] = geom
        return result

    def _feature_refdes(self, feature: FeatureRecord) -> str | None:
        """Extract a reference designator-like .string value from a feature."""

        value = ""
        try:
            value = feature.decoded_attributes.get(".string", "") or feature.decoded_attributes.get(".refdes", "")
        except Exception:
            value = ""
        value = str(value).strip()
        if not value:
            return None
        # KiCad exported spaces as double underscores in some label strings.
        value = value.replace("__", "_").strip("_")
        if not self._REFDES_RE.fullmatch(value):
            return None
        return value

    def _collect_component_contours(self, feature_paths: list[Path]) -> list[tuple[str, object]]:
        """Collect candidate component contour geometries from courtyard/fab layers."""

        contours: list[tuple[str, object]] = []
        for path in feature_paths:
            layer_name = path.parent.name
            try:
                features = self._parse_layer_features(path, layer_name)
            except Exception as exc:
                self.warnings.append(f"Could not parse component contour layer {path}: {exc}")
                continue

            geoms = []
            for feature in features:
                if feature.geometry is None or getattr(feature.geometry, "is_empty", True):
                    continue
                # Ignore reference/value text geometry on fab/silk layers.
                if self._feature_refdes(feature):
                    continue
                try:
                    if str(feature.polarity).upper() != "P":
                        continue
                except Exception:
                    pass
                geoms.append(feature.geometry)

            if not geoms:
                continue
            union = safe_union(geoms)
            for part in self._iter_geometry_parts(union):
                if part is None or getattr(part, "is_empty", True):
                    continue
                try:
                    minx, miny, maxx, maxy = part.bounds
                    if (maxx - minx) < 0.15 or (maxy - miny) < 0.15:
                        continue
                except Exception:
                    continue
                contours.append((layer_name, part.envelope))
        return contours

    def _iter_geometry_parts(self, geom):
        """Yield top-level geometry parts from a Shapely geometry."""

        if geom is None or getattr(geom, "is_empty", True):
            return
        geom_type = getattr(geom, "geom_type", "")
        if geom_type in {"MultiPolygon", "GeometryCollection", "MultiLineString"}:
            for sub in getattr(geom, "geoms", []):
                yield from self._iter_geometry_parts(sub)
        else:
            yield geom

    def _match_refs_to_contours(
        self,
        refs: dict[str, object],
        contours: list[tuple[str, object]],
        side: str,
    ) -> list[ComponentOutlineRecord]:
        """Assign each reference designator to the nearest likely contour."""

        records: list[ComponentOutlineRecord] = []
        used_contour_indices: set[int] = set()
        for ref, ref_geom in sorted(refs.items()):
            try:
                center = ref_geom.centroid
                point = Point(float(center.x), float(center.y))
            except Exception:
                continue

            best_idx = None
            best_dist = float("inf")
            for idx, (_layer_name, contour) in enumerate(contours):
                if idx in used_contour_indices:
                    continue
                try:
                    dist = float(contour.distance(point))
                    minx, miny, maxx, maxy = contour.bounds
                    diagonal = ((maxx - minx) ** 2 + (maxy - miny) ** 2) ** 0.5
                    max_allowed = max(2.0, min(25.0, diagonal * 2.5))
                    if dist <= max_allowed and dist < best_dist:
                        best_idx = idx
                        best_dist = dist
                except Exception:
                    continue

            if best_idx is not None:
                layer_name, contour = contours[best_idx]
                used_contour_indices.add(best_idx)
                geom = contour
                source_layer = layer_name
                source = "nearest courtyard/fab contour"
            else:
                # Fallback: draw a compact contour around the reference text itself.
                try:
                    geom = ref_geom.envelope.buffer(0.75).envelope
                    source_layer = "reference text"
                    source = "fallback reference envelope"
                except Exception:
                    continue

            try:
                c = geom.centroid
                cx, cy = float(c.x), float(c.y)
            except Exception:
                cx, cy = float(point.x), float(point.y)

            records.append(
                ComponentOutlineRecord(
                    refdes=ref,
                    side=side,
                    geometry=geom,
                    center_x_mm=cx,
                    center_y_mm=cy,
                    source_layer=source_layer,
                    source=source,
                )
            )
        return records

    def _parse_pcb_outline(self, root: Path, step_name: str):
        """Parse PCB outline/profile geometry when present.

        Primary source is ODB++ ``steps/<step>/profile``. If that file is absent
        or empty, fall back to common mechanical outline layers such as
        ``edge.cuts``. The result is used for visualization and metadata only.
        """

        step_root = root / "steps" / step_name

        profile_path = step_root / "profile"
        if profile_path.exists():
            geometry = self._parse_outline_features_file(profile_path, "profile")
            if geometry is not None and not getattr(geometry, "is_empty", True):
                return geometry, "steps/<step>/profile"

        outline_names = (
            "edge.cuts",
            "edge_cuts",
            "outline",
            "board_outline",
            "pcb_outline",
            "profile",
            "mechanical",
            "mechanical1",
            "mech1",
        )
        layers_dir = step_root / "layers"
        for name in outline_names:
            features_path = layers_dir / name / "features"
            if not features_path.exists():
                continue
            geometry = self._parse_outline_features_file(features_path, f"layer:{name}")
            if geometry is not None and not getattr(geometry, "is_empty", True):
                return geometry, f"layer:{name}"

        return None, None

    def _parse_outline_features_file(self, features_path: Path, layer_name: str):
        """Parse an ODB++ profile/mechanical features file into outline geometry."""

        try:
            features = self._parse_layer_features(features_path, layer_name)
        except Exception as exc:
            self.warnings.append(f"Could not parse PCB outline from {features_path}: {exc}")
            return None

        geometries = [
            feature.geometry
            for feature in features
            if feature.geometry is not None and not getattr(feature.geometry, "is_empty", True)
        ]
        if not geometries:
            return None
        if len(geometries) == 1:
            return geometries[0]
        return safe_union(geometries)

    def _parse_eda_data(self, eda_path: Path) -> tuple[dict[int, str], dict[tuple[str, int], str]]:
        lines = eda_path.read_text(errors="ignore").splitlines()
        layer_names: list[str] = []
        nets_by_number: dict[int, str] = {}
        feature_net_map: dict[tuple[str, int], str] = {}
        current_net_number: int | None = None
        current_net_name: str | None = None

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("LYR "):
                layer_names = [token.lower() for token in line.split()[1:]]
                continue
            if line.startswith("#NET"):
                parts = line.split()
                current_net_number = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
                current_net_name = None
                continue
            if line.startswith("NET "):
                current_net_name = self._strip_inline_attributes(line[4:].strip())
                if current_net_number is not None:
                    nets_by_number[current_net_number] = current_net_name
                continue
            if line.startswith(("FID C", "FID H")) and current_net_name is not None:
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    layer_idx = int(parts[2])
                    feature_idx = int(parts[3])
                except ValueError:
                    continue
                if 0 <= layer_idx < len(layer_names):
                    feature_net_map[(layer_names[layer_idx], feature_idx)] = current_net_name

        return nets_by_number, feature_net_map


    def _strip_inline_attributes(self, text: str) -> str:
        """Remove ODB++ inline attribute suffix from a name field.

        Some EDA data files write net names as `GND ; 0=0,3=0.3,`. The
        semicolon suffix is metadata, not part of the net name. Keeping it as
        part of the name makes reports confusing and can make the same logical
        net appear under multiple names.
        """

        if ";" not in text:
            return text.strip()
        return text.split(";", 1)[0].strip()

    def _parse_layer_features(self, features_path: Path, layer: str) -> list[FeatureRecord]:
        lines = features_path.read_text(errors="ignore").splitlines()
        symbols: dict[int, SymbolDef] = {}
        attribute_names: dict[int, str] = {}
        attribute_texts: dict[int, str] = {}
        features_start = None

        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            if line.startswith("$"):
                try:
                    idx_token, raw_name = line.split(maxsplit=1)
                    idx = int(idx_token[1:])
                    symbols[idx] = parse_symbol(idx, raw_name)
                except Exception as exc:
                    self.warnings.append(
                        f"Could not parse symbol line in {layer}: {line!r}; reason: {exc}"
                    )
            elif line.startswith("@"):
                try:
                    idx_token, attribute_name = line.split(maxsplit=1)
                    attribute_names[int(idx_token[1:])] = attribute_name.strip()
                except Exception as exc:
                    self.warnings.append(
                        f"Could not parse attribute-name line in {layer}: {line!r}; reason: {exc}"
                    )
            elif line.startswith("&"):
                try:
                    idx_token, attribute_text = line.split(maxsplit=1)
                    attribute_texts[int(idx_token[1:])] = attribute_text.strip()
                except Exception as exc:
                    self.warnings.append(
                        f"Could not parse attribute-text line in {layer}: {line!r}; reason: {exc}"
                    )
            if line == "#Layer features":
                features_start = i + 1
                break
        if features_start is None:
            raise OdbParseError(f"Missing '#Layer features' section in {features_path}")

        features: list[FeatureRecord] = []
        i = features_start
        feature_index = 0
        while i < len(lines):
            raw = lines[i].strip()
            i += 1
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split()
            kind = parts[0]
            if kind == "L":
                record = self._parse_line_feature(
                    layer, feature_index, raw, parts, symbols, attribute_names, attribute_texts
                )
                features.append(record)
                feature_index += 1
            elif kind == "P":
                record = self._parse_pad_feature(
                    layer, feature_index, raw, parts, symbols, attribute_names, attribute_texts
                )
                features.append(record)
                feature_index += 1
            elif kind == "S":
                raw_lines = [raw]
                polarity = parts[1] if len(parts) > 1 else "P"
                surface_tokens = parts[3:] if len(parts) > 3 else []
                # Surface records are commonly written as:
                #   S P 0
                #   OB ...
                #   OS ...
                #   OC ...
                #   SE
                # but some exporters place OB/OS/OC on the same physical line as
                # the `S` header. Keep collecting token streams until SE so both
                # layouts are parsed identically.
                saw_se = any(token == "SE" for token in surface_tokens)
                while not saw_se and i < len(lines):
                    sub_raw = lines[i].strip()
                    i += 1
                    if not sub_raw:
                        continue
                    raw_lines.append(sub_raw)
                    sub_parts = sub_raw.split()
                    surface_tokens.extend(sub_parts)
                    saw_se = any(token == "SE" for token in sub_parts)

                boundaries = self._parse_surface_tokens(surface_tokens, layer, feature_index)
                geom = surface_geometry(boundaries)
                raw_attributes = self._extract_raw_attributes(raw)
                features.append(
                    FeatureRecord(
                        layer=layer,
                        index=feature_index,
                        kind="S",
                        polarity=polarity,
                        symbol_name=None,
                        raw="\n".join(raw_lines),
                        geometry=geom,
                        raw_attributes=raw_attributes,
                        decoded_attributes=self._decode_attribute_string(
                            raw_attributes, attribute_names, attribute_texts
                        ),
                    )
                )
                feature_index += 1
            else:
                # Unknown feature kinds are counted as one feature if they occur at top level.
                self.warnings.append(f"Unsupported feature kind {kind!r} in layer {layer}: {raw[:120]}")
                raw_attributes = self._extract_raw_attributes(raw)
                features.append(
                    FeatureRecord(
                        layer=layer,
                        index=feature_index,
                        kind=kind,
                        polarity="P",
                        symbol_name=None,
                        raw=raw,
                        geometry=None,
                        raw_attributes=raw_attributes,
                        decoded_attributes=self._decode_attribute_string(
                            raw_attributes, attribute_names, attribute_texts
                        ),
                    )
                )
                feature_index += 1
        return features


    def _parse_surface_tokens(
        self,
        tokens: list[str],
        layer: str,
        feature_index: int,
    ) -> list[tuple[str, list[tuple[float, float]]]]:
        """Parse ODB++ surface contour commands including OC arcs.

        Supported commands:
        - OB x y I/H: begin island/hole boundary
        - OS x y: straight segment to point
        - OC x_end y_end x_center y_center Y/N: circular arc to endpoint
        - OE: end current boundary
        - SE: end surface

        Unknown or malformed surface tokens are skipped with a warning instead
        of aborting the whole board analysis.
        """

        boundaries: list[tuple[str, list[tuple[float, float]]]] = []
        current_marker = "I"
        current_coords: list[tuple[float, float]] = []
        pos = 0
        arc_count = 0
        skipped = 0

        def finish_boundary() -> None:
            nonlocal current_coords
            if current_coords:
                boundaries.append((current_marker, current_coords))
            current_coords = []

        while pos < len(tokens):
            cmd = tokens[pos]
            if cmd == "OB":
                if current_coords:
                    finish_boundary()
                if pos + 3 >= len(tokens):
                    skipped += 1
                    break
                try:
                    x = parse_float(tokens[pos + 1])
                    y = parse_float(tokens[pos + 2])
                    marker = tokens[pos + 3]
                except Exception:
                    skipped += 1
                    pos += 1
                    continue
                current_marker = marker
                current_coords = [(x, y)]
                pos += 4
                continue
            if cmd == "OS":
                if pos + 2 >= len(tokens):
                    skipped += 1
                    break
                try:
                    current_coords.append((parse_float(tokens[pos + 1]), parse_float(tokens[pos + 2])))
                except Exception:
                    skipped += 1
                pos += 3
                continue
            if cmd == "OC":
                if pos + 5 >= len(tokens):
                    skipped += 1
                    break
                try:
                    end = (parse_float(tokens[pos + 1]), parse_float(tokens[pos + 2]))
                    center = (parse_float(tokens[pos + 3]), parse_float(tokens[pos + 4]))
                    flag = tokens[pos + 5].upper()
                    clockwise = True if flag == "Y" else False if flag == "N" else None
                    if current_coords:
                        points = arc_points(
                            current_coords[-1],
                            end,
                            center,
                            clockwise,
                            resolution=self.geometry_resolution,
                        )
                        current_coords.extend(points)
                    else:
                        current_coords.append(end)
                    arc_count += 1
                except Exception:
                    skipped += 1
                pos += 6
                continue
            if cmd == "OE":
                finish_boundary()
                pos += 1
                continue
            if cmd == "SE":
                finish_boundary()
                break

            # Ignore non-command tokens left over from unusual surface headers.
            pos += 1

        if current_coords:
            finish_boundary()
        # Do not log every arc-bearing surface; real boards can contain many of them.
        if skipped:
            self.warnings.append(
                f"Surface parser skipped {skipped} malformed token group(s) in {layer} feature #{feature_index}"
            )
        return boundaries

    def _parse_line_feature(
        self,
        layer: str,
        feature_index: int,
        raw: str,
        parts: list[str],
        symbols: dict[int, SymbolDef],
        attribute_names: dict[int, str],
        attribute_texts: dict[int, str],
    ) -> FeatureRecord:
        polarity = parts[6] if len(parts) > 6 else "P"
        symbol = self._symbol_or_fallback(symbols, int(parts[5]), layer)
        geom = track_geometry(
            symbol,
            parse_float(parts[1]),
            parse_float(parts[2]),
            parse_float(parts[3]),
            parse_float(parts[4]),
            resolution=self.geometry_resolution,
        )
        raw_attributes = self._extract_raw_attributes(raw)
        return FeatureRecord(
            layer=layer,
            index=feature_index,
            kind="L",
            polarity=polarity,
            symbol_name=symbol.raw_name,
            raw=raw,
            geometry=geom,
            raw_attributes=raw_attributes,
            decoded_attributes=self._decode_attribute_string(raw_attributes, attribute_names, attribute_texts),
        )

    def _parse_pad_feature(
        self,
        layer: str,
        feature_index: int,
        raw: str,
        parts: list[str],
        symbols: dict[int, SymbolDef],
        attribute_names: dict[int, str],
        attribute_texts: dict[int, str],
    ) -> FeatureRecord:
        polarity = parts[4] if len(parts) > 4 else "P"
        symbol = self._symbol_or_fallback(symbols, int(parts[3]), layer)
        orientation_token = self._last_token_before_attributes(parts[5:]) if len(parts) > 5 else None
        rotation = odb_pad_orientation_to_degrees(orientation_token)
        geom = pad_geometry(
            symbol,
            parse_float(parts[1]),
            parse_float(parts[2]),
            rotation_deg=rotation,
            resolution=self.geometry_resolution,
        )
        raw_attributes = self._extract_raw_attributes(raw)
        return FeatureRecord(
            layer=layer,
            index=feature_index,
            kind="P",
            polarity=polarity,
            symbol_name=symbol.raw_name,
            raw=raw,
            geometry=geom,
            raw_attributes=raw_attributes,
            decoded_attributes=self._decode_attribute_string(raw_attributes, attribute_names, attribute_texts),
        )

    def _last_token_before_attributes(self, tokens: list[str]) -> str | None:
        """Return the final non-attribute token from a feature record.

        Pad records may use a compact ODB++ orientation code such as ``3``.
        Keeping the original token lets the orientation decoder distinguish
        integer orient_def codes from literal degree values like ``270.0``.
        """

        for token in reversed(tokens):
            if token.startswith(';'):
                continue
            return token
        return None

    def _extract_raw_attributes(self, raw_feature_line: str) -> str:
        """Return the raw ODB++ feature attribute suffix after ';'."""

        if ";" not in raw_feature_line:
            return ""
        return raw_feature_line.split(";", 1)[1].strip()

    def _decode_attribute_string(
        self,
        raw_attributes: str,
        attribute_names: dict[int, str],
        attribute_texts: dict[int, str],
    ) -> dict[str, str]:
        """Decode ODB++ feature attributes such as `0=5,3=0.3`.

        The left-hand side is looked up in the `@` attribute-name table. Integer
        right-hand values are also looked up in the `&` text-string table when a
        matching entry exists. Unknown IDs remain visible as `@<id>` so the user
        never loses information.
        """

        decoded: dict[str, str] = {}
        if not raw_attributes:
            return decoded

        for item in raw_attributes.split(","):
            item = item.strip()
            if not item:
                continue

            if "=" in item:
                raw_key, raw_value = item.split("=", 1)
                raw_key = raw_key.strip()
                raw_value = raw_value.strip()
            else:
                # ODB++ also allows flag-style attributes without a value. Keep
                # them visible instead of silently dropping them.
                raw_key = item
                raw_value = "true"

            try:
                key_id = int(raw_key)
            except ValueError:
                key_name = raw_key
            else:
                key_name = attribute_names.get(key_id, f"@{key_id}")

            value = raw_value
            # Many ODB++ attributes store an integer reference into the feature
            # attribute text-string table. Resolve it while preserving numeric
            # literals such as 0.3, booleans, or quoted strings unchanged.
            if re.fullmatch(r"[+-]?\d+", raw_value):
                try:
                    text_id = int(raw_value)
                except ValueError:
                    text_id = None
                if text_id is not None and text_id in attribute_texts:
                    value = attribute_texts[text_id]

            # Avoid silently overwriting duplicate attribute names.
            unique_name = key_name
            duplicate_index = 2
            while unique_name in decoded:
                unique_name = f"{key_name}#{duplicate_index}"
                duplicate_index += 1
            decoded[unique_name] = value
        return decoded

    def _symbol_or_fallback(
        self, symbols: dict[int, SymbolDef], symbol_index: int, layer: str
    ) -> SymbolDef:
        symbol = symbols.get(symbol_index)
        if symbol is None:
            self.warnings.append(
                f"Missing symbol index {symbol_index} in layer {layer}; using 1 um fallback."
            )
            return SymbolDef(
                index=symbol_index,
                raw_name=f"missing_{symbol_index}",
                kind="unknown",
                width_mm=0.001,
                height_mm=0.001,
            )
        if symbol.kind == "unknown":
            self.warnings.append(f"Unsupported symbol {symbol.raw_name!r} in layer {layer}")
        return symbol
