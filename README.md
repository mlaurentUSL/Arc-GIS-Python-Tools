# Arc-GIS-Python-Tools

A collection of Python scripts designed to automate GIS workflows within **ArcGIS Pro** using the `arcpy` library.

---

## Scripts

### `Create_UDF_Layout_Execution.py`

Automates the creation of multiple map layouts in an ArcGIS Pro project for **UDF (Utility Distribution Feature) routes**. For each requested route number, the script duplicates a source layout template, assigns it to the correct map, and automatically zooms the map frame to the matching feature.

---

#### Requirements

- **ArcGIS Pro** with a valid license (the script runs inside an open ArcGIS Pro project)
- **Python / arcpy** (bundled with ArcGIS Pro)
- An ArcGIS Pro project (`.aprx`) that contains:
  - A **source layout** to use as a template (its name is supplied as a parameter)
  - A map named exactly **`UDF Basemap Data`**
- A **flushing feature class** with the following attribute fields:
  | Field | Type | Description |
  |-------|------|-------------|
  | `RTENUM` | Integer | Route number used to identify and select features |
  | `MAPSCALE` | Integer / Double | Desired display scale for the layout (optional; calculated automatically if `NULL`) |

---

#### Parameters

The script is intended to be run as an **ArcGIS Script Tool** and reads its three inputs via `arcpy.GetParameterAsText()`:

| # | Parameter | Description | Example |
|---|-----------|-------------|---------|
| 0 | `layout_numbers_str` | Comma-separated list of route numbers to process. Supports individual values and ranges. | `"1,3,5-8,12"` |
| 1 | `source_layout_name` | Name of the existing layout in the project to use as a template. | `"UDF Template"` |
| 2 | `flushing_fc` | Path to the feature class containing the flushing/route features. | `"C:\GIS\data.gdb\Flushing"` |

**Layout number syntax examples:**

| Input | Resolved route numbers |
|-------|------------------------|
| `"1,2,3"` | 1, 2, 3 |
| `"5-8"` | 5, 6, 7, 8 |
| `"1,3,5-7"` | 1, 3, 5, 6, 7 |

---

#### How It Works

1. **Parse layout numbers** — converts the comma-separated input string (with optional ranges) into a sorted list of integers.
2. **Open the current ArcGIS Pro project** — accesses the active `.aprx` project via `arcpy.mp.ArcGISProject("CURRENT")`.
3. **Locate the source layout and target map** — verifies that the template layout and the `UDF Basemap Data` map both exist in the project.
4. **Export the source layout to a temporary `.pagx` file** — creates a reusable layout template in the system's temp directory.
5. **For each route number:**
   - Skip if a layout named `UDF Route <N>` already exists.
   - Import the temporary `.pagx` to create a new layout and rename it `UDF Route <N>`.
   - Assign the `UDF Basemap Data` map to the layout's first map frame.
   - Select the feature where `RTENUM = <N>` in the flushing feature class.
   - Zoom the map frame camera to the feature's extent (with a 10 % buffer on each side).
   - Apply the `MAPSCALE` value from the feature if available; otherwise round the calculated scale to the nearest 100 (minimum 500).
6. **Clean up** — removes the temporary feature layer after all layouts are processed.

---

#### Usage

1. In **ArcGIS Pro**, add `Create_UDF_Layout_Execution.py` as a **Script Tool** inside a custom Toolbox (`.tbx`).
2. Configure the three parameters in the tool's **Properties** dialog (types: `String`, `String`, `Feature Layer / Feature Class`).
3. Open your project, ensure a map named `UDF Basemap Data` exists, and run the tool from the **Geoprocessing** pane.
4. Newly created layouts will appear in the project's **Layouts** panel, each named `UDF Route <N>` and zoomed to the corresponding route feature.

---

#### Notes

- If a layout named `UDF Route <N>` already exists in the project, that route is **skipped** automatically.
- Any extra maps accidentally imported alongside the layout template are deleted to keep the project clean.
- All error and status messages are surfaced through the ArcGIS Pro **Geoprocessing Messages** pane (`arcpy.AddMessage` / `arcpy.AddWarning` / `arcpy.AddError`).
