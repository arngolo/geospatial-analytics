import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Make sure `utils` is importable regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_SPATIALITE_DLL_PATH = r"C:\Program Files\QGIS 3.34.3\bin\mod_spatialite.dll"


def _resolve_spatialite_dll_path():
    return os.environ.get("SPATIALITE_DLL_PATH", DEFAULT_SPATIALITE_DLL_PATH)


def _try_load_spatialite(dll_path):
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(True)
    try:
        if dll_path and os.path.exists(dll_path):
            # mod_spatialite's dependent DLLs (proj, geos, sqlite3, ...) are only
            # resolved by SQLite's own LoadLibrary call if their directory is on
            # PATH - os.add_dll_directory alone is not enough here.
            dll_dir = os.path.dirname(dll_path)
            if dll_dir not in os.environ["PATH"]:
                os.environ["PATH"] = dll_dir + os.pathsep + os.environ["PATH"]
            conn.load_extension(dll_path)
        else:
            conn.load_extension("mod_spatialite")
        return True
    except Exception:
        return False
    finally:
        conn.close()


@pytest.fixture(scope="session")
def spatialite_dll_path():
    """Path to mod_spatialite. Override with the SPATIALITE_DLL_PATH env var."""
    return _resolve_spatialite_dll_path()


@pytest.fixture(scope="session")
def spatialite_available(spatialite_dll_path):
    return _try_load_spatialite(spatialite_dll_path)


@pytest.fixture
def require_spatialite(spatialite_available):
    if not spatialite_available:
        pytest.skip(
            "mod_spatialite extension is not available in this environment. "
            "Set the SPATIALITE_DLL_PATH env var to mod_spatialite's location."
        )


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "change_detection_test.sqlite")


@pytest.fixture
def sample_aoi_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [25.790701, -12.319634],
                            [25.943776, -12.319634],
                            [25.943776, -12.175975],
                            [25.790701, -12.175975],
                            [25.790701, -12.319634],
                        ]
                    ],
                },
                "properties": {"name": "Unknown"},
            }
        ],
    }


@pytest.fixture
def sample_aoi_geojson_path(tmp_path, sample_aoi_geojson):
    path = tmp_path / "aoi.geojson"
    path.write_text(json.dumps(sample_aoi_geojson))
    return str(path)
