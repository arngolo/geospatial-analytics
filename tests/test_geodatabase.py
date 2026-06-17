import numpy as np
import pytest
from rasterio.transform import Affine
from shapely.geometry import MultiPolygon, Polygon

from utils.geodatabase import (
    binary_raster_to_polygons,
    connect_spatialite_database,
    create_change_detection_database,
    insert_aoi,
    insert_change_features,
    merge_touching_polygons,
    remove_small_polygons,
    sync_rasters,
)


# ---------------------------------------------------------------------
# Pure polygon helpers (no SpatiaLite required)
# ---------------------------------------------------------------------

def test_polygon_helpers():
    cases = []

    def check(name, condition):
        cases.append((name, bool(condition)))

    binary = np.zeros((4, 4), dtype=np.uint8)
    binary[1:3, 1:3] = 1
    polygons = binary_raster_to_polygons(binary, Affine.identity())
    check(
        "binary_raster_to_polygons extracts change region",
        len(polygons) == 1 and polygons[0].area == pytest.approx(4.0),
    )

    empty_binary = np.zeros((4, 4), dtype=np.uint8)
    check(
        "binary_raster_to_polygons returns empty for no change",
        binary_raster_to_polygons(empty_binary, Affine.identity()) == [],
    )

    small = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])  # area 1
    large = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])  # area 100
    kept = remove_small_polygons([small, large], min_area_m2=10)
    check("remove_small_polygons filters by area", kept == [large])

    left = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    right = Polygon([(1, 0), (1, 1), (2, 1), (2, 0)])
    merged = merge_touching_polygons([left, right])
    check(
        "merge_touching_polygons combines adjacent shapes",
        len(merged) == 1 and merged[0].area == pytest.approx(2.0),
    )

    far = Polygon([(100, 100), (100, 101), (101, 101), (101, 100)])
    merged_separate = merge_touching_polygons([left, far])
    check("merge_touching_polygons keeps separate shapes apart", len(merged_separate) == 2)

    check("merge_touching_polygons empty input returns empty list", merge_touching_polygons([]) == [])

    for name, passed in cases:
        print(f"[{'SUCCESS' if passed else 'FAILURE'}] {name}")

    failed = [name for name, passed in cases if not passed]
    assert not failed, f"failed cases: {failed}"


# ---------------------------------------------------------------------
# SpatiaLite availability
# ---------------------------------------------------------------------

def test_spatialite_extension_is_available(spatialite_available):
    assert spatialite_available, (
        "mod_spatialite could not be loaded. Set the SPATIALITE_DLL_PATH env var "
        "to mod_spatialite's location, or make sure it is on PATH."
    )


# ---------------------------------------------------------------------
# Database creation
# ---------------------------------------------------------------------

def test_create_change_detection_database_creates_expected_tables(
    require_spatialite, db_path, spatialite_dll_path
):
    create_change_detection_database(db_path, spatialite_dll_path=spatialite_dll_path)

    conn = connect_spatialite_database(db_path, spatialite_dll_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert {"rasters", "aoi", "change_features"}.issubset(tables)


def test_database_is_empty_before_insert(require_spatialite, db_path, spatialite_dll_path):
    create_change_detection_database(db_path, spatialite_dll_path=spatialite_dll_path)

    conn = connect_spatialite_database(db_path, spatialite_dll_path)
    cursor = conn.cursor()

    for table in ("rasters", "aoi", "change_features"):
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        assert cursor.fetchone()[0] == 0

    conn.close()


def test_database_has_data_after_inserting_dummy_raster(
    require_spatialite, db_path, spatialite_dll_path, tmp_path
):
    create_change_detection_database(db_path, spatialite_dll_path=spatialite_dll_path)
    conn = connect_spatialite_database(db_path, spatialite_dll_path)

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "dummy_raster.tif").write_bytes(b"")

    sync_rasters(conn, str(processed_dir))

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM rasters")
    assert cursor.fetchone()[0] == 1

    cursor.execute("SELECT raster_name, file_path FROM rasters")
    raster_name, file_path = cursor.fetchone()
    assert raster_name == "dummy_raster"
    assert file_path.endswith("dummy_raster.tif")

    conn.close()


def test_database_has_data_after_inserting_dummy_aoi(
    require_spatialite, db_path, spatialite_dll_path, sample_aoi_geojson
):
    create_change_detection_database(db_path, spatialite_dll_path=spatialite_dll_path)
    conn = connect_spatialite_database(db_path, spatialite_dll_path)

    insert_aoi(conn, sample_aoi_geojson, "test_aoi")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM aoi")
    assert cursor.fetchone()[0] == 1

    cursor.execute("SELECT name, ST_AsText(geometry) FROM aoi")
    name, wkt = cursor.fetchone()
    assert name == "test_aoi"
    assert wkt.startswith("MULTIPOLYGON")

    conn.close()


def test_database_has_data_after_inserting_dummy_change_features(
    require_spatialite, db_path, spatialite_dll_path
):
    create_change_detection_database(db_path, spatialite_dll_path=spatialite_dll_path)
    conn = connect_spatialite_database(db_path, spatialite_dll_path)

    # change_features.geometry is declared MULTIPOLYGON - SpatiaLite rejects a
    # bare POLYGON insert, so dummy features must be MultiPolygon too.
    polygon = MultiPolygon([Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])])
    insert_change_features(conn, [polygon], "2023-08-12", "2023-09-02", "CVA")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM change_features")
    assert cursor.fetchone()[0] == 1

    cursor.execute("SELECT method, area_m2, ST_AsText(geometry) FROM change_features")
    method, area, wkt = cursor.fetchone()
    assert method == "CVA"
    assert area == pytest.approx(100.0)
    assert wkt.startswith("MULTIPOLYGON")

    conn.close()
