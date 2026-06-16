# Geospatial Change Detection

## Overview

This project implements a geospatial change detection workflow using Sentinel-2 RGB imagery.

The workflow:

1. Loads and preprocesses multi-temporal imagery.
2. Applies histogram matching to improve radiometric consistency.
3. Performs change detection using:

   * Change Vector Analysis (CVA)
   * Spectral Angle Mapper (SAM)
4. Generates binary change maps through thresholding.
5. Converts detected changes into vector polygons.
6. Removes small polygons and merges adjacent detections.
7. Stores results in a SpatiaLite database.

---

## Project Structure

```text
.
├── data/
│   ├── processed/
│   ├── change_database.sqlite
│   └── ...
├── debug_geodatabase.ipynb
├── debug_notebook.ipynb
├── utils/
│   ├── geodatabase.py
│   ├── image_pre_process.py
│   └── ...
├── report.md
├── README.md
└── requirements.txt
```

---

## Methodology

### Change Detection

Two algorithms were evaluated:

#### Change Vector Analysis (CVA)

The provided example implementation supplied with the challenge was based on CVA and served as the primary inspiration for the implementation.

CVA computes the Euclidean distance between corresponding pixels in spectral feature space. Larger distances indicate stronger change.

#### Spectral Angle Mapper (SAM)

SAM measures the spectral angle between pixel vectors and is less sensitive to differences in brightness and image radiometry.

The SAM implementation was added to compare its behavior against CVA under the same processing workflow.

---

### Histogram Matching

Visual inspection revealed radiometric differences between acquisition dates.

Histogram matching was applied before change detection to improve radiometric consistency between images.

The reference and source images used for histogram matching were selected through visual inspection.

Observed effects:

* Reduced mosaicing artifacts.
* Improved visual consistency between acquisition dates.
* Reduced false positive detections, particularly for CVA.

---

## Database

Results are stored in a SpatiaLite database.

### Tables

#### rasters

Stores raster metadata and file locations.

| Column           | Description            |
| ---------------- | ---------------------- |
| id               | Primary key            |
| acquisition_date | Image acquisition date |
| raster_type      | Raster category        |
| file_path        | Path to raster file    |

#### aoi

Stores Area of Interest (AOI) geometries.

| Column   | Description  |
| -------- | ------------ |
| id       | Primary key  |
| name     | AOI name     |
| geometry | AOI geometry |

#### change_features

Stores detected change polygons.

| Column      | Description              |
| ----------- | ------------------------ |
| id          | Primary key              |
| date_before | Earlier acquisition date |
| date_after  | Later acquisition date   |
| method      | CVA or SAM               |
| area_m2     | Polygon area             |
| mean_change | Average change value     |
| geometry    | Change polygon geometry  |

---

## Environment Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Activate (Linux/macOS):
```bash
source .venv/bin/activate
```

Activate (Windows PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Processed Outputs

Files written to `data/processed/` during the workflow:

| File | Description |
|------|-------------|
| `sentinel2_20230812_RGB.tif` | Stacked RGB bands for the before date (2023-08-12) |
| `sentinel2_20230902_RGB.tif` | Stacked RGB bands for the after date (2023-09-02) |
| `geotiff_hist_match.tif` | After image after histogram matching to the before image |
| `change.tif` | CVA raw change magnitude map |
| `change_probability.tif` | CVA change probability map (normalised) |
| `change_sam.tif` | SAM raw spectral angle map |
| `change_probability_sam.tif` | SAM change probability map (normalised) |
| `binary_cd_threshold_98_sam.tif` | Binary change mask — SAM, 98th percentile threshold |
| `binary_cd_auto_otsu_cva.tif` | Binary change mask — CVA, automatic Otsu threshold |

---

## SpatiaLite Setup

Before starting Jupyter Notebook, add the directory containing the SpatiaLite libraries to your system PATH:

```bash
export PATH="<spatialite_libraries_dir>:$PATH"
```

This allows Python to locate `mod_spatialite` and its dependencies when loading the extension.

---

## Running the Workflow

### 1. Create the database

Open `debug_geodatabase.ipynb` and run the `create database cell`.

This creates the SpatiaLite database at `data/change_database.sqlite` with the `rasters`, `aoi`, and `change_features` tables.

### 2. Execute change detection

Open `debug_notebook.ipynb` and run all cells.

This loads and preprocesses the imagery, applies histogram matching, runs CVA and SAM change detection, and generates binary change maps.

### 3. Generate vector features and save to database

Continuing in `debug_notebook.ipynb`, the workflow:

* Thresholds change maps.
* Converts binary rasters to polygons.
* Clips to AOI to remove edge artifacts.
* Removes small polygons.
* Merges adjacent detections.
* Inserts geometries into the SpatiaLite database.

