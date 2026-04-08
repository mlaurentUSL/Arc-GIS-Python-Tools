# Feature Class Field Builder

**ArcGIS Pro Script Tool (ArcPy)**  
Script: `tools/feature_class_field_builder.py`

---

## Overview

The **Feature Class Field Builder** is a single-script ArcGIS Pro geoprocessing tool
that lets you:

1. **Create a new feature class** at a chosen location, with a chosen geometry type.
2. **Append fields to an existing feature class** — if the output path already exists,
   the tool skips creation and adds only the fields you define.

Fields are defined by typing simple comma-separated tokens into four text parameters
(one per field type).  You can optionally prefix each field name with an ordering number
to control the final column order.

---

## Parameters

Parameters are read by positional index.  Configure them in this **exact order** in the
Script Tool properties dialog.

| # | Script name       | ArcGIS Pro data type           | Direction | Required |
|---|-------------------|-------------------------------|-----------|----------|
| 0 | `out_fc`          | Feature Class                 | Output    | Yes      |
| 1 | `geometry_type`   | String (Value List)           | Input     | Yes      |
| 2 | `text_fields`     | String                        | Input     | No       |
| 3 | `double_fields`   | String                        | Input     | No       |
| 4 | `long_fields`     | String                        | Input     | No       |
| 5 | `short_fields`    | String                        | Input     | No       |

---

### Parameter 0 — `out_fc` (Output Feature Class)

**Description:**  
The full path (including name) of the target feature class.

- If the path **does not exist**, the tool creates a new feature class with the
  geometry type you choose in parameter 1.
- If the path **already exists**, the tool prints a notice and **appends fields**
  to the existing dataset.  The geometry type parameter is ignored.

**Examples:**
```
C:\GIS\MyProject.gdb\Assets
C:\GIS\MyProject.gdb\WaterMains
\\server\data\Utilities.gdb\Valves
```

---

### Parameter 1 — `geometry_type` (Geometry Type)

**Description:**  
The geometry type used when creating a NEW feature class.  Ignored when `out_fc`
already exists.

**Value List (configure in Script Tool properties):**
```
POINT
POLYLINE
POLYGON
```

**Default:** `POINT`

---

### Parameter 2 — `text_fields` (Text Fields)

**Description:**  
Comma-separated field definition tokens for **TEXT** fields (maximum length 255).

**Token format:**
```
[rank,] field_name [, rank, field_name ...]
```
- An **integer** token sets the ordering rank for the field name that follows it.
- A **string** token is a field name.
- Ordering numbers are **optional**.

**Examples:**

| Input | Fields created |
|-------|----------------|
| `1,Asset ID,3,Community` | `Asset_ID` (rank 1), `Community` (rank 3) |
| `Asset ID,Community` | `Asset_ID` (unranked), `Community` (unranked) |
| `Note` | `Note` (unranked) |

---

### Parameter 3 — `double_fields` (Double Fields)

**Description:**  
Comma-separated field definition tokens for **DOUBLE** (floating-point) fields.

**Examples:**

| Input | Fields created |
|-------|----------------|
| `2,Diameter,5,Elevation 2026` | `Diameter` (rank 2), `Elevation_2026` (rank 5) |
| `Length,Width` | `Length` (unranked), `Width` (unranked) |

---

### Parameter 4 — `long_fields` (Long Integer Fields)

**Description:**  
Comma-separated field definition tokens for **LONG** (32-bit integer) fields.

**Example:**

| Input | Fields created |
|-------|----------------|
| `4,Year` | `Year` (rank 4) |
| `Count,Total` | `Count` (unranked), `Total` (unranked) |

---

### Parameter 5 — `short_fields` (Short Integer Fields)

**Description:**  
Comma-separated field definition tokens for **SHORT** (16-bit integer) fields.

**Example:**

| Input | Fields created |
|-------|----------------|
| `6,Status Code` | `Status_Code` (rank 6) |

---

## Field Name Sanitization Rules

Field names must follow ArcGIS / database naming conventions.  The tool
automatically sanitizes any name that violates these rules and **emits a
warning** so you know what was changed.

| Rule | Action | Example |
|------|--------|---------|
| Characters outside `[A-Za-z0-9_]` (spaces, hyphens, dots, etc.) | Replace with `_` | `Elevation 2026` → `Elevation_2026` |
| Multiple consecutive underscores | Collapse to one `_` | `Asset__ID` → `Asset_ID` |
| Leading or trailing underscores | Strip | `_Name_` → `Name` |
| Field name starts with a digit | Prefix with `F_` | `2026Elevation` → `F_2026Elevation` |
| Empty name after all rules applied | Rename to `FIELD` | `---` → `FIELD` |

---

## Field Ordering Rules

1. Provide an **integer token** before a field name to assign it an ordering rank.
2. All ranked fields appear **before** unranked fields.
3. Ranked fields are sorted by rank value (ascending).
4. If ranks are **non-sequential** (e.g., `1, 3, 4, 5, 6`), the tool compresses
   them to sequential values while **preserving relative order**:
   - Input ranks `1, 3, 4, 5, 6` → compressed to `1, 2, 3, 4, 5`
5. Unranked fields keep the order they were typed, with **text → double → long → short**
   parameter order as the tiebreaker.
6. If a field already exists in the feature class, it is **skipped** with a warning.

---

## Complete Working Example

**Parameters:**

| Parameter      | Value |
|----------------|-------|
| `out_fc`       | `C:\GIS\MyProject.gdb\Assets` |
| `geometry_type`| `POINT` |
| `text_fields`  | `1,Asset ID,3,Community` |
| `double_fields`| `2,Diameter,5,Elevation 2026` |
| `long_fields`  | `4,Year` |
| `short_fields`  | *(blank)* |

**Sanitization warnings produced:**
- `[text_fields]` Field name `'Asset ID'` was changed to `'Asset_ID'` (replaced non-alphanumeric/underscore characters with '_').
- `[double_fields]` Field name `'Elevation 2026'` was changed to `'Elevation_2026'` (replaced non-alphanumeric/underscore characters with '_').

**Final field order:**

| Order | Field name       | Type   | Rank |
|-------|------------------|--------|------|
| 1     | `Asset_ID`       | TEXT   | 1    |
| 2     | `Diameter`       | DOUBLE | 2    |
| 3     | `Community`      | TEXT   | 3    |
| 4     | `Year`           | LONG   | 4    |
| 5     | `Elevation_2026` | DOUBLE | 5    |

---

## Spatial Reference (New Feature Classes)

- If `arcpy.env.outputCoordinateSystem` is set in the current ArcGIS Pro
  environment, that coordinate system is used.
- If it is **not** set, the tool defaults to **WGS 84 (EPSG:4326)** and prints
  an informational message.

---

## Undo Warning

> **Warning:** This geoprocessing operation is **NOT undoable** in the way
> that edit operations inside an edit session are.  Verify your inputs before
> running.  The tool emits this warning every time it runs as a reminder.

---

## How to Add This Script as a Tool in ArcGIS Pro

### Step 1 — Create or open a toolbox

1. In the **Catalog** pane, expand **Toolboxes**.
2. Right-click **Toolboxes** → **New Toolbox (.atbx)** and name it
   (e.g., `FieldTools.atbx`), **or** open an existing toolbox.

### Step 2 — Add the script

1. Right-click the toolbox → **Add** → **Script**.
2. Fill in:
   - **Name:** `FeatureClassFieldBuilder` (no spaces)
   - **Label:** `Feature Class Field Builder`
   - **Description:** *(optional)*
3. Under **Script File**, browse to `tools/feature_class_field_builder.py`.
4. Click **Next**.

### Step 3 — Configure parameters

Add the following parameters **in this exact order**:

| Index | Label                | Name              | Data Type      | Type     | Direction |
|-------|----------------------|-------------------|----------------|----------|-----------|
| 0     | Output Feature Class | `out_fc`          | Feature Class  | Required | Output    |
| 1     | Geometry Type        | `geometry_type`   | String         | Required | Input     |
| 2     | Text Fields          | `text_fields`     | String         | Optional | Input     |
| 3     | Double Fields        | `double_fields`   | String         | Optional | Input     |
| 4     | Long Fields          | `long_fields`     | String         | Optional | Input     |
| 5     | Short Fields         | `short_fields`    | String         | Optional | Input     |

**For `geometry_type`, configure a Value List filter:**
1. Click the `geometry_type` row.
2. In the **Filter** column, choose **Value List**.
3. Add the values: `POINT`, `POLYLINE`, `POLYGON`.
4. Set the **Default Value** to `POINT`.

### Step 4 — Finish

Click **Finish**.  The tool now appears in your toolbox and can be opened from
the Geoprocessing pane like any other tool.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Workspace does not exist` error | `out_fc` path references a `.gdb` that hasn't been created yet | Create the geodatabase first (e.g., *Data Management → Geodatabase → Create File GDB*) |
| Field silently skipped | Field with that name already exists | Check existing schema; rename the field in the token string |
| Wrong field order | Rank numbers not assigned, or two fields share a rank | Add explicit rank integers before each field name |
| Name unchanged warning | Input already valid | No action needed; it's just informational |

---

## Requirements

- ArcGIS Pro (any current release)
- `arcpy` (included with ArcGIS Pro)
- No additional Python packages required

---

## File Location in This Repository

```
Arc-GIS-Python-Tools/
└── tools/
    └── feature_class_field_builder.py
└── README_feature_class_field_builder.md   ← this file
└── README.md
```
