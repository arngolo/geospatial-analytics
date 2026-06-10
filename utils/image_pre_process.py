import os
import numpy as np
import rasterio
from rasterio import plot
from rasterio.plot import show
import json
from natsort import natsorted
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import random
import matplotlib.colors as mcolors


def Normalizer(feature):
    feature_min=feature.min()
    feature_max=feature.max()
    if feature_min==feature_max:
        feature=feature/feature_min
    else:
        feature=np.divide((feature-feature_min),(feature_max-feature_min))
    return feature

def aoi_geojson_reader(annotation_path):

    annotation_dictionary = {}
    # annotation for each image
    annotations = open(annotation_path,'rb')
    annotations = json.load(annotations)
    annotations = annotations['images']
    annotation_dictionary['images'] = {item['file_name']: item for item in annotations}

    #get unique classe labels from the created dictionary
    classes = {}
    counter = 1
    for image in list(annotation_dictionary['images'].keys()):
        for classe in annotation_dictionary['images'][image]['annotations']:
            if not classes or classe['class'] not in classes.keys():
                classes[classe['class']] = counter
                counter += 1
                
    annotation_dictionary['class_labels'] = classes
                
    return annotation_dictionary

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
    
    stack = np.moveaxis(stack, -1, 0) # reshape to (channel, height, width)
    geotiff = rasterio.open(output_path, "w", driver = "GTiff", height = stack.shape[1], width = stack.shape[2], dtype = stack.dtype, count = stack.shape[0], nodata = geoinfo['nodata'], crs = geoinfo['crs'], transform = geoinfo['transform'])
    geotiff.write(stack)
    geotiff.close()


