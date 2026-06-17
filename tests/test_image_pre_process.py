import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine
from shapely.geometry import Polygon

from utils.image_pre_process import (
    Normalizer,
    aoi_geojson_reader,
    clip_to_aoi,
    geojson_polygon_to_pixels,
    geojson_to_pixel_polygons,
    get_bands,
    histogram_match,
    otsu_threshold_change,
    sam_change_detection,
    stack_to_geotiff,
    threshold_change,
)


# ---------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------

def test_normalizer_scales_values_to_unit_range():
    feature = np.array([0.0, 5.0, 10.0])

    result = Normalizer(feature)

    assert result.min() == pytest.approx(0.0)
    assert result.max() == pytest.approx(1.0)
    assert result[1] == pytest.approx(0.5)


def test_normalizer_handles_constant_feature():
    feature = np.array([4.0, 4.0, 4.0])

    result = Normalizer(feature)

    assert np.allclose(result, 1.0)


# ---------------------------------------------------------------------
# Thresholding
# ---------------------------------------------------------------------

def test_threshold_change_keeps_only_top_percentile():
    change_map = np.arange(100).reshape(10, 10).astype(np.float32)

    binary = threshold_change(change_map, percentile=95)

    assert binary.dtype == np.uint8
    assert set(np.unique(binary)).issubset({0, 1})
    assert binary.sum() == 5  # values 95..99 are above the 95th percentile


def test_otsu_threshold_change_separates_bimodal_data():
    change_map = np.concatenate([np.zeros(50), np.full(50, 255)]).astype(np.float32)

    binary = otsu_threshold_change(change_map)

    assert set(np.unique(binary)).issubset({0, 1})
    assert binary[:50].sum() == 0
    assert binary[50:].sum() == 50


# ---------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------

def test_sam_change_detection_no_change_for_identical_images():
    # Uniform magnitude across pixels avoids the min/max normalization step
    # amplifying float rounding noise into spurious nonzero probabilities.
    image = np.full((5, 5, 3), 100.0, dtype=np.float32)

    change_uint8, probability = sam_change_detection(image, image)

    assert change_uint8.dtype == np.uint8
    assert np.allclose(probability, 0.0, atol=1e-5)


def test_sam_change_detection_detects_direction_change():
    image_before = np.zeros((1, 2, 3), dtype=np.float32)
    image_before[0, 0] = [1, 0, 0]
    image_before[0, 1] = [1, 0, 0]

    image_after = np.zeros((1, 2, 3), dtype=np.float32)
    image_after[0, 0] = [1, 0, 0]  # no change
    image_after[0, 1] = [0, 1, 0]  # 90 degree spectral change

    _, probability = sam_change_detection(image_before, image_after)

    assert probability[0, 0] == pytest.approx(0.0)
    assert probability[0, 1] == pytest.approx(1.0)


def test_histogram_match_preserves_shape():
    rng = np.random.default_rng(0)
    source = rng.uniform(0, 255, size=(4, 4, 3)).astype(np.float32)
    reference = rng.uniform(0, 255, size=(4, 4, 3)).astype(np.float32)

    matched = histogram_match(source, reference)

    assert matched.shape == source.shape


# ---------------------------------------------------------------------
# AOI / geojson helpers
# ---------------------------------------------------------------------

def test_aoi_geojson_reader_reads_geojson_file(sample_aoi_geojson_path, sample_aoi_geojson):
    result = aoi_geojson_reader(sample_aoi_geojson_path)

    assert result == sample_aoi_geojson


def test_clip_to_aoi_keeps_only_intersecting_polygons(sample_aoi_geojson):
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32735", always_xy=True)
    coords = sample_aoi_geojson["features"][0]["geometry"]["coordinates"][0]
    projected = [transformer.transform(lon, lat) for lon, lat in coords]
    xs, ys = zip(*projected)
    center_x, center_y = sum(xs) / len(xs), sum(ys) / len(ys)

    inside = Polygon(
        [
            (center_x - 10, center_y - 10),
            (center_x - 10, center_y + 10),
            (center_x + 10, center_y + 10),
            (center_x + 10, center_y - 10),
        ]
    )
    outside = Polygon(
        [
            (center_x + 1_000_000, center_y),
            (center_x + 1_000_100, center_y),
            (center_x + 1_000_100, center_y + 100),
            (center_x + 1_000_000, center_y + 100),
        ]
    )

    clipped = clip_to_aoi([inside, outside], sample_aoi_geojson)

    assert len(clipped) == 1
    assert clipped[0].intersects(inside)


def test_geojson_polygon_to_pixels_matches_manual_transform():
    from pyproj import Transformer
    from rasterio.transform import rowcol

    raster_meta = {
        "crs": "EPSG:32735",
        "transform": Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 8700000.0),
    }
    coords = [(25.80, -12.30), (25.81, -12.30)]

    pixels = geojson_polygon_to_pixels(coords, raster_meta)

    transformer = Transformer.from_crs("EPSG:4326", raster_meta["crs"], always_xy=True)
    expected = []
    for lon, lat in coords:
        x, y = transformer.transform(lon, lat)
        row, col = rowcol(raster_meta["transform"], x, y)
        expected.append([col, row])

    assert pixels.shape == (2, 2)
    assert pixels.tolist() == expected


def test_geojson_to_pixel_polygons_skips_non_polygon_features():
    raster_meta = {
        "crs": "EPSG:32735",
        "transform": Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 8700000.0),
    }
    geojson_dict = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [25.80, -12.30]},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [25.80, -12.30],
                            [25.81, -12.30],
                            [25.81, -12.31],
                            [25.80, -12.30],
                        ]
                    ],
                },
            },
        ],
    }

    polygons = geojson_to_pixel_polygons(geojson_dict, raster_meta)

    assert len(polygons) == 1
    assert polygons[0].shape == (4, 2)


# ---------------------------------------------------------------------
# Raster IO helpers
# ---------------------------------------------------------------------

def test_get_bands_filters_xml_and_normalizes_path_separators(tmp_path):
    (tmp_path / "B02.tif").write_bytes(b"")
    (tmp_path / "B03.tif").write_bytes(b"")
    (tmp_path / "B02.tif.aux.xml").write_bytes(b"")

    bands = get_bands(str(tmp_path))

    assert set(bands.keys()) == {"B02", "B03"}
    assert all("\\" not in path for path in bands.values())


def test_stack_to_geotiff_round_trip(tmp_path):
    stack = np.random.default_rng(0).integers(0, 255, size=(4, 4, 2), dtype=np.uint8)
    geoinfo = {
        "nodata": None,
        "crs": "EPSG:32735",
        "transform": Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 8700000.0),
    }
    output_path = tmp_path / "stack.tif"

    stack_to_geotiff(stack, geoinfo, str(output_path))

    with rasterio.open(output_path) as src:
        assert src.count == 2
        assert (src.height, src.width) == (4, 4)
        written = np.moveaxis(src.read(), 0, -1)
        assert np.array_equal(written, stack)
