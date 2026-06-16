import os
import numpy as np
import rasterio
from rasterio import plot
from rasterio.plot import show
import json
from natsort import natsorted
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Polygon
import random
import matplotlib.colors as mcolors
from pyproj import Transformer
from rasterio.transform import rowcol
from skimage.exposure import match_histograms
from skimage.filters import threshold_otsu
from shapely.geometry import Polygon as sh_polygon
from shapely.ops import unary_union
from pyproj import Transformer


def Normalizer(feature):
    feature_min=feature.min()
    feature_max=feature.max()
    if feature_min==feature_max:
        feature=feature/feature_min
    else:
        feature=np.divide((feature-feature_min),(feature_max-feature_min))
    return feature

import json

def aoi_geojson_reader(annotation_path):
    """
    Read AOI GeoJSON file.

    Parameters
    ----------
    annotation_path : str

    Returns
    -------
    dict
        GeoJSON dictionary
    """

    with open(annotation_path, "r", encoding="utf-8") as f:
        geojson_dict = json.load(f)

    return geojson_dict

def clip_to_aoi(polygons, geojson_dict, srid=32735):

    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{srid}", always_xy=True)

    aoi = unary_union([
        sh_polygon([transformer.transform(lon, lat) for lon, lat in feature["geometry"]["coordinates"][0]])
        for feature in geojson_dict["features"]
        if feature["geometry"]["type"] == "Polygon"
    ])

    clipped = [p.intersection(aoi) for p in polygons if p.intersects(aoi)]

    return [p for p in clipped if not p.is_empty]

def geojson_polygon_to_pixels(coords, raster_meta):
    """
    Convert a GeoJSON polygon from lon/lat coordinates
    to raster pixel coordinates.

    Parameters
    ----------
    coords : list
        Polygon coordinates:
        [[lon, lat], [lon, lat], ...]

    raster_meta : dict
        {
            "crs": raster CRS,
            "transform": raster affine transform
        }

    Returns
    -------
    np.ndarray
        Shape (N, 2)
        [[col, row], ...]
    """

    transformer = Transformer.from_crs(
        "EPSG:4326",          # GeoJSON default CRS
        raster_meta["crs"],  # Raster CRS
        always_xy=True
    )

    vertices = []

    for lon, lat in coords:

        x, y = transformer.transform(lon, lat)

        row, col = rowcol(
            raster_meta["transform"],
            x,
            y
        )

        vertices.append([col, row])

    return np.asarray(vertices, dtype=np.float32)

def geojson_to_pixel_polygons(geojson_dict, raster_meta):

    polygons = []

    for feature in geojson_dict["features"]:

        geometry = feature["geometry"]

        if geometry["type"] != "Polygon":
            continue

        coords = geometry["coordinates"][0]

        pixel_vertices = geojson_polygon_to_pixels(
            coords,
            raster_meta
        )

        polygons.append(pixel_vertices)

    return polygons

def visualize_image_with_polygons(image, pixel_polygons=None, title="Image", show_vertices=False):

    # CHW -> HWC
    if image.ndim == 3 and image.shape[0] in (1, 2, 3):
        image = np.moveaxis(image, 0, -1)

    fig, ax = plt.subplots(figsize=(10, 10))

    if image.ndim == 2:

        ax.imshow(image, cmap="gray")

    elif image.ndim == 3:

        if image.shape[-1] == 1:

            ax.imshow(image[:, :, 0], cmap="gray")

        elif image.shape[-1] == 2:

            rgb = np.dstack([
                image[:, :, 0],
                image[:, :, 1],
                np.zeros_like(image[:, :, 0])
            ])

            ax.imshow(rgb)

        else:

            rgb = image[:, :, :3].astype(np.float32)

            if rgb.max() > 0:
                rgb /= rgb.max()

            ax.imshow(rgb)

    # Draw polygons only if provided
    if pixel_polygons is not None:

        for vertices in pixel_polygons:

            poly = Polygon(
                vertices,
                fill=False,
                edgecolor="red",
                linewidth=2
            )

            ax.add_patch(poly)

            if show_vertices:

                xs, ys = zip(*vertices)

                ax.plot(
                    xs,
                    ys,
                    "ro",
                    markersize=3
                )

    ax.set_title(title)

    plt.show()

def normalized_difference(band_a, band_b, epslon=1e-8):
    result = (band_a - band_b) / (band_a + band_b + epslon)
    return result

def get_bands(raster_path):
    bands = os.listdir(raster_path)
    bands_dict = {}

    for i in bands:

        if "xml" not in i: # filters qgis created files
            i_path = os.path.join(raster_path, i)
            if '\\' in i_path:
                i_path = i_path.replace('\\', '/')
            bands_dict[str(i.split('.tif')[0])] = i_path
    print(bands_dict)
    return (bands_dict)

def stack_bands(list_of_bands, bands):


    ''' stacks images from a list of bands'''

    # n_bands = len(list_of_bands)
    
    src = rasterio.open(bands[list_of_bands[0]])
    nodata = src.nodata
    crs = src.crs
    transform =  src.transform
    geoinfo = {'nodata':nodata, 'crs':crs, 'transform':transform}

    print(src, "\n", nodata, "\n", crs, "\n", transform, "\n")
    if nodata:
        print("nodata value: ", nodata)
        for i in list_of_bands:
            
            # # if nodata has a value, needs to be set to nan value
            img = rasterio.open(bands[i])
            bands[i] = np.ma.masked_values(img.read(1), src.nodata)

    else:
        for i in list_of_bands:
                
            # in case nodata is none (image already filled with nan values)
            img = rasterio.open(bands[i])
            band_1 = src.read(1)
            bands[i] = img.read(1)

    stack = np.dstack(tuple(bands.values()))
    return stack, geoinfo

def stack_to_geotiff(stack, geoinfo, output_path):
    if stack.ndim == 2:
        geotiff = rasterio.open(output_path, "w", driver = "GTiff", height = stack.shape[0], width = stack.shape[1], dtype = stack.dtype, count = 1, nodata = geoinfo['nodata'], crs = geoinfo['crs'], transform = geoinfo['transform'])
        geotiff.write(stack, 1)    
    else:
        stack = np.moveaxis(stack, -1, 0) # reshape to (channel, height, width)
        geotiff = rasterio.open(output_path, "w", driver = "GTiff", height = stack.shape[1], width = stack.shape[2], dtype = stack.dtype, count = stack.shape[0], nodata = geoinfo['nodata'], crs = geoinfo['crs'], transform = geoinfo['transform'])
        geotiff.write(stack)
    geotiff.close()

def histogram_match(image_source, image_reference):

    return match_histograms(image_source, image_reference, channel_axis=-1)

def sam_change_detection(image_before, image_after):

    """
    Detect changes between two co-registered images using
    Spectral Angle Mapper (SAM).

    SAM measures the angle between the spectral vectors of the
    same pixel observed at two different dates. Unlike Change
    Vector Analysis (CVA), which measures the magnitude of the
    spectral difference, SAM measures the change in spectral
    direction and is therefore less sensitive to overall
    brightness and radiometric differences between images.

    Parameters
    ----------
    image_before : np.ndarray
        Image at time T1.
        Shape: (height, width, bands)

    image_after : np.ndarray
        Image at time T2.
        Shape: (height, width, bands)

    Returns
    -------
    change_uint8 : np.ndarray
        Change map normalized to 0–255 (uint8).
        Useful for visualization or saving as raster.

    change_probability : np.ndarray
        Change map normalized to 0–1 (float32).
        Higher values indicate stronger spectral change.

    Advantages:
    - More robust to illumination differences
    - More robust to radiometric inconsistencies
    - Commonly used in remote sensing and hyperspectral analysis

    Limitations:
    - Uses only spectral direction and ignores change magnitude
    - Can be sensitive when spectral vectors have very low values
    """

    image_before = image_before.astype(np.float32)
    image_after = image_after.astype(np.float32)

    dot_product = np.sum(image_before * image_after, axis=2)

    norm_before = np.linalg.norm(image_before, axis=2)
    norm_after = np.linalg.norm(image_after, axis=2)

    cosine = dot_product / (norm_before * norm_after + 1e-8)
    cosine = np.clip(cosine, -1, 1)

    angle = np.arccos(cosine)

    probability = (angle - angle.min()) / (angle.max() - angle.min() + 1e-8)

    change_uint8 = (probability * 255).astype(np.uint8)

    return change_uint8, probability

def threshold_change(change_map, percentile=95):
    thresh = np.percentile(change_map, percentile)
    binary = (change_map > thresh).astype(np.uint8)
    return binary

def otsu_threshold_change(change_map):
    t = threshold_otsu(change_map)
    binary = (change_map > t).astype(np.uint8)
    return binary