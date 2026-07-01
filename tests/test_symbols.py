from odb_clearance_analyzer.geometry import parse_symbol


def test_round_symbol_is_converted_from_microns_to_mm():
    sym = parse_symbol(0, "r300.0")
    assert sym.kind == "round"
    assert abs(sym.width_mm - 0.3) < 1e-12


def test_rect_symbol_is_converted_from_microns_to_mm():
    sym = parse_symbol(1, "rect800.0x950.0xr200.0")
    assert sym.kind == "rect"
    assert abs(sym.width_mm - 0.8) < 1e-12
    assert abs(sym.height_mm - 0.95) < 1e-12
    assert abs(sym.radius_mm - 0.2) < 1e-12


def test_oval_symbol_is_converted_from_microns_to_mm():
    sym = parse_symbol(2, "oval1700.0x2000.0")
    assert sym.kind == "oval"
    assert abs(sym.width_mm - 1.7) < 1e-12
    assert abs(sym.height_mm - 2.0) < 1e-12

from pathlib import Path

from odb_clearance_analyzer.odb_parser import OdbParser


def test_tgz_and_tar_gz_extensions_are_supported():
    parser = OdbParser()
    assert parser._is_tar_archive(Path("board.tgz"))
    assert parser._is_tar_archive(Path("board.tar.gz"))
    assert parser._is_tar_archive(Path("board.tar"))
    assert parser._is_tar_archive(Path("board.tar.xz"))
    assert not parser._is_tar_archive(Path("board.zip"))


def test_odb_feature_attribute_decoding_resolves_names_and_text_strings():
    parser = OdbParser()
    decoded = parser._decode_attribute_string(
        "0=5,3=0.3",
        {0: ".string", 3: ".clearance"},
        {5: "C21"},
    )
    assert decoded == {".string": "C21", ".clearance": "0.3"}


def test_odb_feature_attribute_decoding_keeps_unknown_ids():
    parser = OdbParser()
    decoded = parser._decode_attribute_string("7=12", {}, {})
    assert decoded == {"@7": "12"}


def test_odb_feature_attribute_decoding_preserves_bare_flags():
    parser = OdbParser()
    decoded = parser._decode_attribute_string("0=0,1", {0: ".pad_usage", 1: ".geometry"}, {0: "VIA"})
    assert decoded == {".pad_usage": "VIA", ".geometry": "true"}


def test_rounded_rectangle_pad_geometry_does_not_use_square_corners():
    from shapely.geometry import Point
    from odb_clearance_analyzer.geometry import pad_geometry, parse_symbol

    sym = parse_symbol(10, "rect1600.0x1600.0xr400.0")
    geom = pad_geometry(sym, 0.0, 0.0, resolution=8)

    # The old algorithm used the full bounding box, which incorrectly made
    # (0.8, 0.8) copper for a rounded rectangle. That point is outside the
    # real rounded corner and must not be inside the pad geometry.
    assert not geom.contains(Point(0.8, 0.8))
    assert geom.distance(Point(0.8, 0.8)) > 0.0

    # A point on the straight side is still copper.
    assert geom.covers(Point(0.8, 0.0))


def test_eda_net_name_strips_inline_odb_attributes():
    from odb_clearance_analyzer.odb_parser import OdbParser

    parser = OdbParser()
    assert parser._strip_inline_attributes("GND ; 0=0,3=0.3,") == "GND"
    assert parser._strip_inline_attributes("ISO_IPA ; 0=6,3=0.3,6=7,") == "ISO_IPA"
    assert parser._strip_inline_attributes("/RP2040/SPI0_RX") == "/RP2040/SPI0_RX"


def test_negative_cutout_features_are_subtracted_before_clearance_measurement():
    from types import SimpleNamespace

    from shapely.geometry import box

    from odb_clearance_analyzer.analyzer import ClearanceAnalyzer
    from odb_clearance_analyzer.models import FeatureRecord

    layer = "signal_1"
    features = [
        FeatureRecord(layer, 0, "S", "P", None, "GND pour", box(0, 0, 10, 10)),
        # Anti-pad / clearance opening around the signal pad.
        FeatureRecord(layer, 1, "S", "N", None, "negative cutout", box(3.9, 3.9, 5.1, 5.1)),
        FeatureRecord(layer, 2, "P", "P", "rect1000x1000", "signal pad", box(4, 4, 5, 5)),
    ]
    job = SimpleNamespace(
        features_by_layer={layer: features},
        feature_net_map={(layer.lower(), 0): "GND", (layer.lower(), 2): "SIG"},
    )

    analyzer = ClearanceAnalyzer()
    net_geometry_by_layer, _, _, _ = analyzer._build_net_geometry(
        job=job,
        layers=[layer],
        include_none_net=False,
        precision_grid_mm=None,
        geometry_resolution=16,
    )
    measurements = analyzer._measure_all_layers(net_geometry_by_layer)

    assert len(measurements) == 1
    rec = measurements[0]
    assert {rec.net_a, rec.net_b} == {"GND", "SIG"}
    assert abs(rec.clearance_mm - 0.1) < 1e-9


def test_odb_pad_orientation_code_is_not_treated_as_degrees():
    from odb_clearance_analyzer.geometry import odb_pad_orientation_to_degrees

    assert odb_pad_orientation_to_degrees("0") == 0.0
    assert odb_pad_orientation_to_degrees("1") == 90.0
    assert odb_pad_orientation_to_degrees("2") == 180.0
    assert odb_pad_orientation_to_degrees("3") == 270.0
    assert odb_pad_orientation_to_degrees("270.0") == 270.0


def test_rectangular_pad_orientation_code_avoids_false_overlap_on_1p27_pitch():
    from odb_clearance_analyzer.geometry import pad_geometry, parse_symbol

    sym = parse_symbol(16, "rect700x1400")
    upper = pad_geometry(sym, 40.4, 66.453548, rotation_deg=270.0, resolution=8)
    lower = pad_geometry(sym, 40.4, 65.183548, rotation_deg=270.0, resolution=8)

    assert upper.distance(lower) > 0.55
    assert not upper.intersects(lower)


def test_parser_applies_integer_pad_orientation_code_to_pad_geometry():
    from odb_clearance_analyzer.geometry import parse_symbol
    from odb_clearance_analyzer.odb_parser import OdbParser

    parser = OdbParser(geometry_resolution=8)
    symbols = {16: parse_symbol(16, "rect700x1400")}
    attrs = {0: ".pad_usage", 2: ".geometry", 3: ".smd"}
    texts = {0: "Via_025-05-056_OCT_PLUG", 9: "Pad_Rec_0.7x1.4_Paste_15"}
    rec = parser._parse_pad_feature(
        "signal_1",
        0,
        "P 40.4 66.453548 16 P 0 3 ;0=0,2=9,3",
        "P 40.4 66.453548 16 P 0 3 ;0=0,2=9,3".split(),
        symbols,
        attrs,
        texts,
    )
    minx, miny, maxx, maxy = rec.geometry.bounds

    # With orientation code 3 correctly applied, the 1.4 mm dimension is along X.
    assert (maxx - minx) > 1.39
    assert (maxy - miny) < 0.71


def test_arc_points_approximates_odb_oc_arc():
    from odb_clearance_analyzer.geometry import arc_points

    pts = arc_points((1.0, 0.0), (0.0, 1.0), (0.0, 0.0), clockwise=False, resolution=8)
    assert pts[-1] == (0.0, 1.0)
    assert len(pts) > 2
    # A true quarter arc should bow outward near x=y~0.707; a straight chord would stay at x+y=1.
    assert max(x + y for x, y in pts) > 1.3


def test_parser_surface_tokens_support_oc_arcs():
    from odb_clearance_analyzer.odb_parser import OdbParser

    parser = OdbParser(geometry_resolution=8)
    boundaries = parser._parse_surface_tokens(
        [
            "OB", "1", "0", "I",
            "OC", "0", "1", "0", "0", "N",
            "OS", "0", "0",
            "OE",
            "SE",
        ],
        "signal_1",
        123,
    )
    assert len(boundaries) == 1
    marker, coords = boundaries[0]
    assert marker == "I"
    assert len(coords) > 4
    assert coords[0] == (1.0, 0.0)
    assert coords[-1] == (0.0, 0.0)
    assert any(x > 0.6 and y > 0.6 for x, y in coords)


def test_plated_drill_features_are_projected_to_all_span_layers():
    from types import SimpleNamespace

    from shapely.geometry import Point

    from odb_clearance_analyzer.analyzer import ClearanceAnalyzer
    from odb_clearance_analyzer.models import DrillLayerInfo, FeatureRecord

    fcu = "F.CU"
    bcu = "B.CU"
    drill = "DRILL_PLATED_F.CU-B.CU"
    via = FeatureRecord(
        drill,
        0,
        "P",
        "P",
        "r300.0",
        "P 1 1 0 P 0 8 0.0 ;1=0",
        Point(1, 1).buffer(0.15, resolution=8),
        decoded_attributes={".geometry": "VIA_ROUNDD700000"},
    )
    job = SimpleNamespace(
        signal_layers=[fcu, bcu],
        features_by_layer={fcu: [], bcu: []},
        drill_layers=[DrillLayerInfo(drill, fcu, bcu)],
        drill_features_by_layer={drill: [via]},
        feature_net_map={(drill.lower(), 0): "VIA_NET"},
    )

    analyzer = ClearanceAnalyzer()
    net_geometry_by_layer, via_geometry_by_layer, layer_counts, _skipped = analyzer._build_net_geometry(
        job=job,
        layers=[fcu, bcu],
        include_none_net=False,
        precision_grid_mm=None,
        geometry_resolution=8,
    )

    assert "VIA_NET" in net_geometry_by_layer[fcu]
    assert "VIA_NET" in net_geometry_by_layer[bcu]
    assert "VIA_NET" in via_geometry_by_layer[fcu]
    assert "VIA_NET" in via_geometry_by_layer[bcu]
    minx, miny, maxx, maxy = via_geometry_by_layer[fcu]["VIA_NET"].bounds
    assert abs((maxx - minx) - 0.7) < 1e-6
    assert layer_counts[fcu] == 1
    assert layer_counts[bcu] == 1


def test_effective_air_gap_subtracts_intermediate_copper_on_shortest_line():
    from shapely.geometry import box

    from odb_clearance_analyzer.analyzer import ClearanceAnalyzer
    from odb_clearance_analyzer.models import MeasurementRecord

    layer = "L1"
    by_net = {
        "A": box(0.0, -0.5, 1.0, 0.5),
        "BLOCK": box(2.0, -0.5, 3.0, 0.5),
        "B": box(4.0, -0.5, 5.0, 0.5),
    }
    rec = MeasurementRecord(layer, "A", "B", 3.0, 1.0, 0.0, 4.0, 0.0)
    records = ClearanceAnalyzer()._measure_effective_air_gap_matrix({layer: by_net}, [rec])

    assert len(records) == 1
    assert records[0].copper_on_path is True
    assert records[0].blocker_nets == "BLOCK"
    assert abs(records[0].copper_blocked_length_mm - 1.0) < 1e-9
    assert abs(records[0].effective_air_gap_mm - 2.0) < 1e-9


def test_analyzer_cooperative_cancellation_raises_analysis_cancelled():
    from odb_clearance_analyzer.analyzer import ClearanceAnalyzer
    from odb_clearance_analyzer.models import AnalysisCancelled

    analyzer = ClearanceAnalyzer(cancel_check=lambda: True)
    try:
        analyzer._measure_all_layers({"L1": {}})
    except AnalysisCancelled as exc:
        assert "stopped" in str(exc).lower()
    else:
        raise AssertionError("Expected AnalysisCancelled")
