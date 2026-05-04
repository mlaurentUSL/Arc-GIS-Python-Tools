# Enviro Wetland Report Export

## Overview

An ArcGIS Pro Python Toolbox tool that exports **Survey123 Feature Report PDFs**
(Wetland and/or Upland) for a selected project submission directly from ArcGIS Pro.

The tool:

1. Reads the latest submissions from the hosted Survey123 feature service and
   populates a dropdown for the user to pick a project.
2. Detects whether the selected submission has Wetland and/or Upland repeat records
   by querying the related repeat table.
3. Submits asynchronous report jobs to the Survey123 Feature Report API for each
   applicable template (Wetland, Upland, or both).
4. Downloads the resulting PDFs and merges them into a single output PDF using
   `arcpy.mp.PDFDocumentCreate`.

---

## Files

| File | Purpose |
|---|---|
| `Enviro_Report_Export.pyt` | ArcGIS Pro Python Toolbox (thin wrapper) |
| `survey123_feature_report.py` | Business logic module (helpers + main export function) |
| `README.md` | This file |

---

## Configuration

Before using the tool, open `survey123_feature_report.py` and edit the three
constants near the top of the file:

```python
# Item ID of the Survey123 feature service in AGOL/Portal
PORTAL_ITEM_ID   = "f35eaa11693241f6af62264d99b37f22"

# Item IDs of the two Survey123 report templates
TEMPLATE_WETLAND = "75cf70e3519d41308e31ecaf90d1d8ae"
TEMPLATE_UPLAND  = "5451e38dd4d74748a090a5d76f8a3019"
```

To find an item ID:
- Open the item in ArcGIS Online / Portal
- The ID is the 32-character string at the end of the item URL, e.g.:
  `https://www.arcgis.com/home/item.html?id=**f35eaa11693241f6af62264d99b37f22**`

---

## Setup – Adding the Toolbox to ArcGIS Pro

1. Open **ArcGIS Pro**.
2. In the **Catalog** pane, right-click **Toolboxes** → **Add Toolbox**.
3. Navigate to this folder and select **`Enviro_Report_Export.pyt`**.
4. The toolbox **Enviro Report Export** will appear under Toolboxes.
5. Expand it to find the **Export Survey123 Feature Report** tool.

---

## Sign-In Requirement

The tool uses `arcpy.GetSigninToken()` and `arcpy.GetActivePortalURL()` to
authenticate with your portal.  You **must** be signed into the same portal that
hosts the Survey123 feature service and the report templates.

To sign in:
- Go to **File → Sign In** (ArcGIS Pro 3.x) and sign into your ArcGIS Online or
  Enterprise portal.
- Alternatively: **Project → Portals → Sign In**.

If you are not signed in, the submission dropdown will show `Loading...` as a
placeholder and the tool will display an informative error when you try to run it.

---

## Inputs

| # | Parameter | Type | Description |
|---|---|---|---|
| 0 | **Survey Submission** | Drop-down (String) | Project submission formatted as `Project_Number \| YYYY-MM-DD \| OID <id>`. Populated automatically when the tool dialog opens. |
| 1 | **Output PDF File** | File (Output) | Full path including filename for the merged output PDF. The `.pdf` extension is added automatically if omitted. |

---

## Outputs

A single merged PDF at the path specified in **Output PDF File**.

The file is named as specified by the user.  Intermediate per-template PDFs are
written to a temporary folder and deleted automatically after merging.

---

## How It Works

1. **Dropdown population** – `updateParameters` calls `get_submission_labels()`,
   which queries the parent Survey123 dataset for the latest
   `MAX_SUBMISSIONS` (default 200) records sorted newest first.
   Labels are cached for the life of the tool dialog.

2. **Parent record lookup** – The parent dataset is identified by field heuristic:
   must contain `Project_Number` + `sampling_date` and must **not** contain
   `plot_location`.

3. **Repeat detection** – The repeat table is identified by containing
   `plot_location`.  The tool counts records where `plot_location` equals
   `wetland` or `upland` (case-insensitive) linked to the selected parent
   via `ParentGlobalID`.  If repeat detection fails for any reason, both
   templates are attempted with a warning.

4. **Report generation** – Each applicable template is submitted as an
   asynchronous job to:
   `https://survey123.arcgis.com/api/featureReport/createReport/submitJob`
   The job is polled every 2 seconds for up to ~8 minutes.

5. **PDF merge** – All downloaded PDFs are merged with
   `arcpy.mp.PDFDocumentCreate` / `appendPages` into the final output file.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Dropdown shows `Loading...` permanently | Not signed into portal | Sign in via File → Sign In |
| "Feature service item not found" | Wrong `PORTAL_ITEM_ID` | Update the constant in `survey123_feature_report.py` |
| "Survey123 redirected to login" | Token expired or wrong portal | Sign out and sign back in |
| "Report job timed out" | Large report or slow API | Re-run; check Survey123 service status |
| "No Wetland/Upland repeat records found" | No matching repeats for this OID | Verify the submission has plot records |
