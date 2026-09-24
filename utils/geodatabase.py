import os, glob
import sqlite3
from rasterio.features import shapes
from shapely.geometry import shape
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from pyproj import Transformer
from pathlib import Path




def create_change_detection_database(
    database_path,
    srid=32735,
    spatialite_dll_path=None
):
    """
    Create a SpatiaLite database for change detection.

    Parameters
    ----------
    database_path : str
        Output database path.

    srid : int, default=32735
        EPSG code used for geometry columns.

    spatialite_dll_path : str or None, default=None
        Path to mod_spatialite DLL/shared library.
        If None, attempts to load from system PATH.
    """

    conn = sqlite3.connect(database_path)

    conn.enable_load_extension(True)

    try:
        if spatialite_dll_path is None:
            conn.load_extension("mod_spatialite")
        else:
            conn.load_extension(spatialite_dll_path)

    except Exception as e:
        conn.close()
        raise RuntimeError(
            f"Failed to load SpatiaLite extension: {e}"
        )

    cursor = conn.cursor()

    # ----------------------------------------------------------
    # Initialize SpatiaLite metadata
    # ----------------------------------------------------------

    cursor.execute(
        "SELECT InitSpatialMetadata(1);"
    )

    # ----------------------------------------------------------
    # Raster metadata table
    # ----------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rasters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acquisition_date TEXT NOT NULL,
            raster_name TEXT NOT NULL,
            file_path TEXT NOT NULL
        );
    """)

    # ----------------------------------------------------------
    # AOI table
    # ----------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aoi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );
    """)

    cursor.execute(f"""
        SELECT AddGeometryColumn(
            'aoi',
            'geometry',
            {srid},
            'MULTIPOLYGON',
            'XY'
        );
    """)

    cursor.execute("""
        SELECT CreateSpatialIndex(
            'aoi',
            'geometry'
        );
    """)

    # ----------------------------------------------------------
    # Change features table
    # ----------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_before TEXT NOT NULL,
            date_after TEXT NOT NULL,
            method TEXT NOT NULL,
            area_m2 REAL,
            mean_change REAL
        );
    """)

    cursor.execute(f"""
        SELECT AddGeometryColumn(
            'change_features',
            'geometry',
            {srid},
            'MULTIPOLYGON',
            'XY'
        );
    """)

    cursor.execute("""
        SELECT CreateSpatialIndex(
            'change_features',
            'geometry'
        );
    """)

    conn.commit()
    conn.close()

    print(
        f"SpatiaLite database created: {database_path}"
    )

def binary_raster_to_polygons(
    binary_raster,
    transform
):
    """
    Convert a binary raster into polygons.

    Parameters
    ----------
    binary_raster : np.ndarray
        Binary image where:
            0 = no change
            1 = change

    transform : affine.Affine
        Raster transform.

    Returns
    -------
    list
        List of Shapely polygons.
    """

    polygons = []

    for geom, value in shapes(
        binary_raster.astype("uint8"),
        mask=binary_raster.astype(bool),
        transform=transform
    ):

        if value == 1:

            polygons.append(
                shape(geom)
            )

    return polygons

def remove_small_polygons(
    polygons,
    min_area_m2
):
    """
    Remove polygons below a minimum area.
    """

    return [
        polygon
        for polygon in polygons
        if polygon.area >= min_area_m2
    ]

def merge_touching_polygons(
    polygons
):
    """
    Merge touching/overlapping polygons.

    Returns
    -------
    list
        List of merged polygons.
    """

    merged = unary_union(
        polygons
    )

    if merged.is_empty:
        return []

    if merged.geom_type == "Polygon":
        return [merged]

    if merged.geom_type == "MultiPolygon":
        return list(
            merged.geoms
        )

    return []

def insert_change_features(
    conn,
    polygons,
    date_before,
    date_after,
    method,
    srid=32735
):

    cursor = conn.cursor()

    for polygon in polygons:

        cursor.execute(
            f"""
            INSERT INTO change_features (
                date_before,
                date_after,
                method,
                area_m2,
                mean_change,
                geometry
            )
            VALUES (
                ?, ?, ?, ?, ?,
                GeomFromText(?, {srid})
            )
            """,
            (
                date_before,
                date_after,
                method,
                polygon.area,
                None,
                polygon.wkt
            )
        )

    conn.commit()

def insert_aoi(conn, geojson_dict, name, srid=32735):
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{srid}", always_xy=True)
    cursor = conn.cursor()

    for feature in geojson_dict["features"]:
        if feature["geometry"]["type"] != "Polygon":
            continue

        coords = feature["geometry"]["coordinates"][0]
        projected = [transformer.transform(lon, lat) for lon, lat in coords]
        polygon = MultiPolygon([Polygon(projected)])

        cursor.execute(
            f"""
            INSERT INTO aoi (name, geometry)
            VALUES (?, GeomFromText(?, {srid}))
            """,
            (name, polygon.wkt)
        )

    conn.commit()

def connect_spatialite_database(
    database_path,
    spatialite_dll_path
):
    conn = sqlite3.connect(
        database_path
    )

    conn.enable_load_extension(True)

    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(
            os.path.dirname(
                spatialite_dll_path
            )
        )

    conn.load_extension(
        spatialite_dll_path
    )

    return conn

def inspect_database(database_path, spatialite_dll_path, limit=10):
    import os
    import sqlite3

    SYSTEM_TABLES = {
        "geometry_columns", "spatial_ref_sys", "spatial_ref_sys_aux",
        "views_geometry_columns", "virts_geometry_columns",
        "geometry_columns_statistics", "geometry_columns_field_infos",
        "geometry_columns_time", "geometry_columns_auth",
        "sql_statements_log", "SpatialIndex", "ElementaryGeometries",
        "KNN", "KNN2",
    }

    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(os.path.dirname(spatialite_dll_path))
    conn = sqlite3.connect(database_path)
    conn.enable_load_extension(True)
    conn.load_extension(spatialite_dll_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [
        r[0] for r in cursor.fetchall()
        if r[0] not in SYSTEM_TABLES and not r[0].startswith("idx_") and not r[0].startswith("views_") and not r[0].startswith("virts_") and not r[0].startswith("spatialite_") and not r[0].startswith("data_") and not r[0].startswith("sqlite_")
    ]

    print(f"{len(tables)} layer(s): {', '.join(tables)}\n")

    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        col_names = [c[1] for c in cursor.fetchall()]

        cursor.execute(
            "SELECT f_geometry_column FROM geometry_columns WHERE f_table_name=?",
            (table,)
        )
        geom_cols = {r[0] for r in cursor.fetchall()}

        parts = [f"ST_AsText({n}) AS {n}" if n in geom_cols else n for n in col_names]
        cursor.execute(f"SELECT {', '.join(parts)} FROM {table} LIMIT {limit}")
        rows = cursor.fetchall()

        print(f"--- {table} ({len(rows)} row(s)) ---")
        for row in rows:
            vals = {col: (str(v)[:80] + "..." if isinstance(v, str) and len(v) > 80 else v)
                    for col, v in zip(col_names, row)}
            print(vals)
        print()

    conn.close()

def sync_rasters(conn, processed_dir):
    cursor = conn.cursor()

    base = Path.cwd()

    tif_files = {
        Path(p).as_posix()
        for p in glob.glob(os.path.join(processed_dir, "*.tif"))
    }

    cursor.execute("SELECT id, file_path FROM rasters")
    db_rows = {row[1]: row[0] for row in cursor.fetchall()}
    db_paths = set(db_rows.keys())

    to_add = tif_files - db_paths
    for path in sorted(to_add):
        raster_name = Path(path).stem
        cursor.execute(
            "INSERT INTO rasters (acquisition_date, raster_name, file_path) VALUES (?, ?, ?)",
            ("unknown", raster_name, path)
        )
        print(f"Added: {path}")

    to_remove = db_paths - tif_files
    for path in sorted(to_remove):
        cursor.execute("DELETE FROM rasters WHERE id = ?", (db_rows[path],))
        print(f"Removed: {path}")

    conn.commit()
    print(f"\nSync complete — added {len(to_add)}, removed {len(to_remove)}")

def delete_records(database_path, spatialite_dll_path, table, id=None, where=None, remove_all=False):
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(os.path.dirname(spatialite_dll_path))
    conn = sqlite3.connect(database_path)
    conn.enable_load_extension(True)
    conn.load_extension(spatialite_dll_path)
    cursor = conn.cursor()

    if remove_all:
        cursor.execute(f"DELETE FROM {table}")
        print(f"Removed all rows from {table} ({cursor.rowcount} deleted)")

    elif id is not None:
        cursor.execute(f"DELETE FROM {table} WHERE id = ?", (id,))
        print(f"Removed row id={id} from {table} ({cursor.rowcount} deleted)")

    elif where is not None:
        field, value = next(iter(where.items()))
        cursor.execute(f"DELETE FROM {table} WHERE {field} = ?", (value,))
        print(f"Removed rows where {field}='{value}' from {table} ({cursor.rowcount} deleted)")

    else:
        conn.close()
        raise ValueError("Specify id, where, or remove_all=True")

    conn.commit()
    conn.close()
