"""
Integration test that exercises the insert functions against
data/testdata/{processed,aoi,change_detection_polygons} one by one,
inspecting the database after each step.

Skipped until that fixture data is provided.
"""

from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, shape

from utils.geodatabase import (
    connect_spatialite_database,
    create_change_detection_database,
    insert_aoi,
    insert_change_features,
    sync_rasters,
)
from utils.image_pre_process import aoi_geojson_reader

TESTDATA_DIR = Path(__file__).resolve().parents[1] / "data" / "testdata"

pytestmark = pytest.mark.skipif(
    not TESTDATA_DIR.exists(),
    reason=(
        "data/testdata not present. Expected subfolders: "
        "processed/, aoi/, change_detection_polygons/"
    ),
)


def test_full_insert_workflow_against_testdata(require_spatialite, db_path, spatialite_dll_path):
    create_change_detection_database(db_path, spatialite_dll_path=spatialite_dll_path)
    conn = connect_spatialite_database(db_path, spatialite_dll_path)
    cursor = conn.cursor()

    # ---------------------------------------------------------
    # 1. rasters from data/testdata/processed
    # ---------------------------------------------------------
    processed_dir = TESTDATA_DIR / "processed"
    expected_raster_count = len(list(processed_dir.glob("*.tif")))

    sync_rasters(conn, str(processed_dir))

    cursor.execute("SELECT COUNT(*) FROM rasters")
    assert cursor.fetchone()[0] == expected_raster_count

    # ---------------------------------------------------------
    # 2. AOIs from data/testdata/aoi
    # ---------------------------------------------------------
    aoi_files = sorted((TESTDATA_DIR / "aoi").glob("*.geojson"))
    assert aoi_files, "expected at least one AOI geojson in data/testdata/aoi"

    for aoi_file in aoi_files:
        geojson_dict = aoi_geojson_reader(str(aoi_file))
        insert_aoi(conn, geojson_dict, aoi_file.stem)

    cursor.execute("SELECT COUNT(*) FROM aoi")
    assert cursor.fetchone()[0] == len(aoi_files)

    # ---------------------------------------------------------
    # 3. change polygons from data/testdata/change_detection_polygons
    # ---------------------------------------------------------
    polygon_files = sorted((TESTDATA_DIR / "change_detection_polygons").glob("*.geojson"))
    assert polygon_files, "expected at least one change polygons geojson"

    total_polygons = 0
    for polygon_file in polygon_files:
        geojson_dict = aoi_geojson_reader(str(polygon_file))
        polygons = []
        for feature in geojson_dict["features"]:
            geometry = shape(feature["geometry"])
            # change_features.geometry is declared MULTIPOLYGON - SpatiaLite
            # rejects a bare POLYGON insert.
            if geometry.geom_type == "Polygon":
                geometry = MultiPolygon([geometry])
            if geometry.geom_type == "MultiPolygon":
                polygons.append(geometry)

        insert_change_features(conn, polygons, "2023-08-12", "2023-09-02", "CVA")
        total_polygons += len(polygons)

    cursor.execute("SELECT COUNT(*) FROM change_features")
    assert cursor.fetchone()[0] == total_polygons

    conn.close()
