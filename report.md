# Change Detection Report

## 1. Method

### Algorithm

Spectral Angle Mapper (SAM) was selected as the primary change detection method.

SAM measures the spectral angle between the pixel vector of the before image and the after image in spectral feature space. A larger angle indicates a greater change in spectral signature. Unlike Change Vector Analysis (CVA), SAM is insensitive to differences in pixel intensity and is only sensitive to the direction of the spectral vector. This makes it more robust to radiometric inconsistencies between acquisition dates, such as differences in atmospheric conditions or solar angle.

### Algorithm comparison

Both CVA and SAM were evaluated under the same preprocessing pipeline. CVA detected a larger area of change (748 ha) compared to SAM (534 ha).

Visual inspection revealed that the two methods are complementary rather than competing:

- **CVA performed better in the pit area** (bottom-central scene). The mine pit exhibits strong spectral magnitude changes driven by excavation — exposed fresh rock, bench and ramp surfaces, water accumulation. CVA, which measures Euclidean distance in spectral space, captures these high-intensity shifts effectively and was able to resolve the spiral benching pattern of the pit.

- **SAM performed better in the surrounding area** (upper scene). The mine periphery shows subtler changes — vegetation disturbance, soil exposure, burn scars — where the spectral composition shifts without a large change in brightness. SAM, measuring spectral angle rather than magnitude, is more sensitive to these direction-only changes and less affected by illumination or mosaicing differences that are more pronounced toward the scene edges.

Without ground truth it is not possible to quantify which method has fewer false positives overall. The two methods are best understood as complementary — CVA for high-magnitude surface changes in the active pit, SAM for subtler spectral shifts in the surrounding area. A fusion of both probability maps would likely produce a more complete detection than either method alone.

### Preprocessing

Histogram matching was applied to the after image using the before image as reference, prior to change detection. This reduced radiometric inconsistency between the two dates and improved the specificity of both methods, particularly for CVA.

---

## 2. Results

### Scene overview

| Parameter       | Value                                 |
|-----------------|---------------------------------------|
| AOI             | 267.2 km² (16.7 km × 16.0 km)        |
| CRS             | EPSG:32735 (WGS 84 / UTM Zone 35S)   |
| Date before     | 2023-08-12                            |
| Date after      | 2023-09-02                            |
| Interval        | 21 days                               |

### Detected change

| Method       | Changed area | % of scene | Clusters   |
|--------------|-------------|------------|------------|
| SAM (final)  | ~534 ha     | 2.0%       | distributed |
| CVA          | ~748 ha     | 2.8%       | distributed |

### Spatial pattern

Detected changes are distributed across the entire scene with a slight concentration in the north-east quadrant (58.7% in the eastern half, 55.7% in the northern half). The change centroid is close to the scene centre, indicating no single dominant hotspot.

95.4% of detected changed pixels form clusters with at least one neighbouring changed pixel, confirming that the detections represent spatially coherent areas rather than random noise.

---

## 3. Interpretation

### Context

The scene covers a 267 km² area containing an open-pit mine, acquired over a 21-day interval in August–September 2023 (end of the dry season in the southern hemisphere, UTM Zone 35S).

### Change interpretation

In an active open-pit mine, spectral changes over a 21-day window are driven by operational activity rather than seasonal processes. The ~534 ha of detected change likely reflects a combination of:

- **Pit face advancement**: Excavation exposes fresh rock and soil surfaces with distinct spectral signatures compared to weathered or previously exposed material.
- **Waste dump expansion**: Waste rock is continuously deposited on dump areas, altering surface texture and composition.
- **Tailings or water body changes**: Pond levels and extent shift with operations, producing strong spectral change at boundaries.
- **Haul road and infrastructure activity**: Active haul roads and operational areas experience continuous surface disturbance.

### Pattern

Changes are distributed across the full extent of the scene rather than concentrated in one zone, which is consistent with a large mine with multiple simultaneous operational fronts (pit, waste dumps, tailings, processing areas) rather than a single point of change.

### Limitations

Results were evaluated through visual inspection only. Without ground truth or validation data, it is not possible to confirm which detected polygons correspond to specific mine features, or to assess the false positive rate of either algorithm.
