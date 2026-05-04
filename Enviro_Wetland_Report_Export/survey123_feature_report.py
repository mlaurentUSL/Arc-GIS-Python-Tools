"""
survey123_feature_report.py
Business logic for the Enviro Report Export ArcGIS Pro Python Toolbox.

Configuration
-------------
Edit the three constants below to point at your own AGOL/Portal items:
  PORTAL_ITEM_ID  – Survey123 feature service item ID
  TEMPLATE_WETLAND – Wetland report template item ID
  TEMPLATE_UPLAND  – Upland report template item ID
"""

import os
import re
import json
import time
import shutil
import tempfile
from datetime import datetime, timezone

import requests

# ── Configuration ──────────────────────────────────────────────────────────────

PORTAL_ITEM_ID   = "f35eaa11693241f6af62264d99b37f22"
TEMPLATE_WETLAND = "75cf70e3519d41308e31ecaf90d1d8ae"
TEMPLATE_UPLAND  = "5451e38dd4d74748a090a5d76f8a3019"

FEATURE_REPORT_BASE = "https://survey123.arcgis.com/api/featureReport"

# Maximum number of submissions to fetch for the dropdown (sorted newest first)
MAX_SUBMISSIONS = 200

# ── Date helper ────────────────────────────────────────────────────────────────

def _format_date(date_ms, fmt="%Y-%m-%d"):
    """
    Convert an Esri epoch-millisecond timestamp to a formatted date string.
    Returns an empty string when *date_ms* is ``None`` or falsy.
    """
    if not date_ms:
        return ""
    return datetime.fromtimestamp(date_ms / 1000, tz=timezone.utc).strftime(fmt)

# ── Feature-service helpers ────────────────────────────────────────────────────

def _fieldnames(ds):
    """Return the set of field names for a FeatureLayer/Table dataset object."""
    try:
        return {f["name"] for f in ds.properties.fields}
    except Exception:
        return set()


def _pick_parent(item):
    """
    Find the 'parent' dataset in the feature service item.
    Heuristic: has both ``Project_Number`` and ``sampling_date`` fields,
    but does NOT have ``plot_location``.
    Checks tables first, then layers.
    """
    for ds in (getattr(item, "tables", None) or []) + (getattr(item, "layers", None) or []):
        fns = _fieldnames(ds)
        if "Project_Number" in fns and "sampling_date" in fns and "plot_location" not in fns:
            return ds
    return None


def _pick_repeat(item):
    """
    Find the first repeat dataset that contains ``plot_location``
    (used to distinguish Wetland vs Upland plot types).
    """
    for ds in (getattr(item, "tables", None) or []) + (getattr(item, "layers", None) or []):
        if "plot_location" in _fieldnames(ds):
            return ds
    return None


def _find_globalid_field(attrs):
    """Return the GlobalID field name found in a feature's attribute dict."""
    for k in ("globalid", "GlobalID", "GLOBALID"):
        if k in attrs and attrs[k]:
            return k
    return None


def _find_parentglobalid_field(ds):
    """Return the ParentGlobalID-style link field name from a dataset's schema."""
    fns = []
    try:
        fns = [f["name"] for f in ds.properties.fields]
    except Exception:
        pass
    for cand in fns:
        lc = cand.lower()
        if "parent" in lc and "global" in lc and "id" in lc:
            return cand
    for cand in ("parentglobalid", "ParentGlobalID", "PARENTGLOBALID"):
        if cand in fns:
            return cand
    return None


def _norm_guid(g):
    """Normalize a GUID string: strip whitespace and curly braces."""
    s = str(g).strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    return s

# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _headers(token):
    return {
        "Referer": "https://survey123.arcgis.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Esri-Authorization": "Bearer {}".format(token),
    }


def _download(url, out_path, token):
    """Stream-download a URL (passes token both as header and query param)."""
    with requests.get(
        url, params={"token": token}, stream=True, timeout=300, headers=_headers(token)
    ) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

# ── Survey123 report API ───────────────────────────────────────────────────────

def _submit_report(token, portal_url, feature_layer_url, objectid, template_id, out_name):
    """
    Submit an asynchronous Survey123 Feature Report job.
    Uses the /submitJob endpoint to avoid HTML login-redirect responses.
    Returns the job ID string.
    """
    submit_url = FEATURE_REPORT_BASE + "/createReport/submitJob"
    payload = {
        "f": "json",
        "token": token,
        "portalUrl": portal_url,
        "featureLayerUrl": feature_layer_url,
        "templateItemId": template_id,
        "queryParameters": json.dumps({"objectIds": [int(objectid)]}),
        "outputFormat": "pdf",
        "outputReportName": out_name,
    }
    r = requests.post(
        submit_url, data=payload, headers=_headers(token), timeout=60, allow_redirects=False
    )

    # Explicit redirect → login means the token was rejected
    if r.status_code in (301, 302, 303, 307, 308):
        loc = r.headers.get("Location", "")
        raise Exception(
            "Survey123 redirected to login — check that you are signed into the correct "
            "portal (Project ➜ Portals) and that the token is valid.\n"
            "Redirect location: {}".format(loc)
        )

    if not r.text:
        raise Exception("Survey123 /submitJob returned an empty response.")

    t = r.text.strip()
    if not t.startswith("{"):
        raise Exception(
            "Survey123 /submitJob returned non-JSON.\n"
            "HTTP status: {}\n{}".format(r.status_code, r.text[:800])
        )

    j = r.json()
    job_id = j.get("jobId") or j.get("jobID")
    if not job_id:
        raise Exception(
            "Survey123 /submitJob response missing jobId.\n{}".format(
                json.dumps(j, indent=2)
            )
        )
    return job_id


def _wait_job(token, portal_url, job_id):
    """
    Poll the Survey123 job status endpoint until the job completes or times out.
    Returns the final job-status JSON object.
    Polls up to 240 times with a 2-second delay (~8 minutes total).
    """
    job_url = FEATURE_REPORT_BASE + "/jobs/{}".format(job_id)
    for _ in range(240):
        r = requests.get(
            job_url,
            params={"f": "json", "token": token, "portalUrl": portal_url},
            headers=_headers(token),
            timeout=30,
            allow_redirects=False,
        )

        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            raise Exception(
                "Survey123 job-status endpoint redirected to login.\n"
                "Redirect location: {}".format(loc)
            )

        if not r.text:
            time.sleep(2)
            continue

        t = r.text.strip()
        if not t.startswith("{"):
            raise Exception(
                "Survey123 job-status returned non-JSON.\n"
                "HTTP status: {}\n{}".format(r.status_code, r.text[:800])
            )

        j = r.json()
        st = j.get("jobStatus")
        if st in ("esriJobSucceeded", "esriJobPartialSucceeded", "esriJobFailed"):
            return j
        time.sleep(2)

    raise Exception("Report job timed out after ~8 minutes (jobId: {}).".format(job_id))


def _get_result_pdf(job_json):
    """Extract the first result-file URL and name from a completed job object."""
    ri = (job_json or {}).get("resultInfo") or {}
    rf = ri.get("resultFiles") or []
    if not rf:
        return None, None
    return rf[0].get("url"), rf[0].get("name")

# ── Public API ─────────────────────────────────────────────────────────────────

def get_submission_labels():
    """
    Query the parent Survey123 dataset and return a list of label strings for
    the tool dropdown, formatted as::

        Project_Number | YYYY-MM-DD | OID <objectid>

    Returns ``["Loading..."]`` on any error (including not signed in) so the
    ToolValidator never crashes.

    Performance note: fetches at most ``MAX_SUBMISSIONS`` records, sorted by
    ``sampling_date`` descending so the newest work appears first.
    """
    import arcpy  # imported here so the module can be loaded outside ArcPy
    from arcgis.gis import GIS

    DUMMY = ["Loading..."]
    try:
        info = arcpy.GetSigninToken()
        if not info or "token" not in info:
            return DUMMY

        token = info["token"]
        portal_url = arcpy.GetActivePortalURL()
        gis = GIS(portal_url, token=token)

        item = gis.content.get(PORTAL_ITEM_ID)
        if not item:
            return DUMMY

        parent = _pick_parent(item)
        if not parent:
            return DUMMY

        oid_field = getattr(parent.properties, "objectIdField", "OBJECTID")
        q = parent.query(
            where="1=1",
            out_fields="{},Project_Number,sampling_date".format(oid_field),
            return_geometry=False,
            result_record_count=MAX_SUBMISSIONS,
            order_by_fields="sampling_date DESC",
        )

        labels = []
        for f in (q.features if q else []):
            a = f.attributes or {}
            proj = a.get("Project_Number")
            date_ms = a.get("sampling_date")
            oid = a.get(oid_field)
            if proj is None or oid is None:
                continue
            date_str = _format_date(date_ms) or "No Date"
            labels.append("{} | {} | OID {}".format(proj, date_str, oid))

        return labels if labels else DUMMY

    except Exception:
        return DUMMY


def export_feature_report(sel, out_path):
    """
    Main entry point called from the .pyt ``execute()`` method.

    Parameters
    ----------
    sel : str
        The selected dropdown label, e.g. ``"USL-2024-001 | 2024-06-15 | OID 42"``
    out_path : str
        Full path to the output PDF file.  A ``.pdf`` extension is appended
        automatically if the user omitted it.
    """
    import arcpy
    from arcgis.gis import GIS

    # ── parse OID from label ──────────────────────────────────────────────────
    m = re.search(r"OID\s+(\d+)\s*$", sel or "")
    if not m:
        arcpy.AddError(
            "Cannot parse OID from selection: '{}'.\n"
            "Expected format: 'Project_Number | YYYY-MM-DD | OID <number>'.".format(sel)
        )
        raise SystemExit(1)
    parent_oid = int(m.group(1))

    # ── enforce .pdf extension ────────────────────────────────────────────────
    if not out_path.lower().endswith(".pdf"):
        out_path += ".pdf"

    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.isdir(out_dir):
        arcpy.AddError("Output directory does not exist: {}".format(out_dir))
        raise SystemExit(1)

    # ── authenticate ──────────────────────────────────────────────────────────
    info = arcpy.GetSigninToken()
    if not info or "token" not in info:
        arcpy.AddError(
            "Not signed into a portal in ArcGIS Pro.\n"
            "Sign in via File ➜ Sign In (or Project ➜ Portals), then re-run the tool."
        )
        raise SystemExit(1)
    token = info["token"]
    portal_url = arcpy.GetActivePortalURL()
    arcpy.AddMessage("Portal URL: {}".format(portal_url))

    # ── connect to feature service ────────────────────────────────────────────
    gis = GIS(portal_url, token=token)
    item = gis.content.get(PORTAL_ITEM_ID)
    if not item:
        arcpy.AddError(
            "Feature service item not found.  "
            "Verify that PORTAL_ITEM_ID = '{}' is correct and accessible to your account.".format(
                PORTAL_ITEM_ID
            )
        )
        raise SystemExit(1)
    arcpy.AddMessage("Feature service: {}".format(item.title))

    # ── locate parent dataset ─────────────────────────────────────────────────
    parent_ds = _pick_parent(item)
    if not parent_ds:
        arcpy.AddError(
            "Parent dataset not found in feature service.  "
            "Expected a layer/table with fields 'Project_Number' and 'sampling_date' "
            "but without 'plot_location'."
        )
        raise SystemExit(1)
    arcpy.AddMessage("Parent dataset URL: {}".format(parent_ds.url))

    # ── query the selected parent record ──────────────────────────────────────
    oid_field = getattr(parent_ds.properties, "objectIdField", "OBJECTID")
    parent_q = parent_ds.query(
        where="{}={}".format(oid_field, parent_oid),
        out_fields="*",
        return_geometry=False,
    )
    if not parent_q or not parent_q.features:
        arcpy.AddError("Parent record with {} = {} not found.".format(oid_field, parent_oid))
        raise SystemExit(1)

    parent_attrs = parent_q.features[0].attributes or {}

    gid_field = _find_globalid_field(parent_attrs)
    if not gid_field:
        arcpy.AddError("Parent record is missing a GlobalID field — cannot link to repeat table.")
        raise SystemExit(1)

    parent_gid = _norm_guid(parent_attrs[gid_field])
    parent_gid_braced = "{" + parent_gid + "}"

    # ── detect wetland / upland repeat counts ─────────────────────────────────
    # Sentinel value -1 means "detection failed; run both templates"
    wet_ct = 0
    upl_ct = 0

    repeat_ds = _pick_repeat(item)
    if repeat_ds:
        arcpy.AddMessage("Repeat dataset URL: {}".format(repeat_ds.url))
        fk = _find_parentglobalid_field(repeat_ds)
        if fk:
            try:
                rep = repeat_ds.query(
                    where="{0}='{1}' OR {0}='{2}'".format(fk, parent_gid, parent_gid_braced),
                    out_fields="plot_location",
                    return_geometry=False,
                )
                for f in (rep.features if rep else []):
                    loc = ((f.attributes or {}).get("plot_location") or "").strip().lower()
                    if loc == "wetland":
                        wet_ct += 1
                    elif loc == "upland":
                        upl_ct += 1
                arcpy.AddMessage(
                    "Repeat counts — Wetland: {}, Upland: {}".format(wet_ct, upl_ct)
                )
            except Exception as exc:
                arcpy.AddWarning(
                    "Could not query repeat table ({}). "
                    "Will attempt both Wetland and Upland templates.".format(exc)
                )
                wet_ct = upl_ct = -1
        else:
            arcpy.AddWarning(
                "ParentGlobalID link field not found in repeat table. "
                "Will attempt both Wetland and Upland templates."
            )
            wet_ct = upl_ct = -1
    else:
        arcpy.AddWarning(
            "No repeat table with 'plot_location' field found. "
            "Will attempt both Wetland and Upland templates."
        )
        wet_ct = upl_ct = -1

    run_wetland = wet_ct > 0 or wet_ct == -1
    run_upland  = upl_ct > 0 or upl_ct == -1

    if not run_wetland and not run_upland:
        arcpy.AddError(
            "No Wetland or Upland repeat records found for OID {}.".format(parent_oid)
        )
        raise SystemExit(1)

    # ── build filename fragments ───────────────────────────────────────────────
    proj = str(parent_attrs.get("Project_Number") or "Report").replace(" ", "_")
    date_ms = parent_attrs.get("sampling_date")
    date_str = _format_date(date_ms, fmt="%Y%m%d") or "NoDate"
    feature_layer_url = parent_ds.url

    # ── generate PDFs in a temporary folder ───────────────────────────────────
    tmp = tempfile.mkdtemp(prefix="s123pdf_")
    parts = []
    try:
        # ── Wetland PDF ────────────────────────────────────────────────────────
        if run_wetland:
            arcpy.AddMessage("Submitting Wetland report job…")
            out_name = "{}_{}_OID{}_WETLAND".format(proj, date_str, parent_oid)
            jid = _submit_report(
                token, portal_url, feature_layer_url, parent_oid, TEMPLATE_WETLAND, out_name
            )
            arcpy.AddMessage("Wetland job ID: {}".format(jid))
            jobj = _wait_job(token, portal_url, jid)
            if jobj.get("jobStatus") == "esriJobFailed":
                msg = jobj.get("messages", "")
                if wet_ct == -1:
                    arcpy.AddWarning("Wetland report job failed (skipping): {}".format(msg))
                else:
                    raise Exception("Wetland report job failed: {}".format(msg))
            else:
                url, name = _get_result_pdf(jobj)
                if not url:
                    arcpy.AddWarning("Wetland report returned no download URL.")
                else:
                    pth = os.path.join(tmp, name or (out_name + ".pdf"))
                    _download(url, pth, token)
                    parts.append(pth)
                    arcpy.AddMessage("Wetland PDF downloaded: {}".format(pth))

        # ── Upland PDF ─────────────────────────────────────────────────────────
        if run_upland:
            arcpy.AddMessage("Submitting Upland report job…")
            out_name = "{}_{}_OID{}_UPLAND".format(proj, date_str, parent_oid)
            jid = _submit_report(
                token, portal_url, feature_layer_url, parent_oid, TEMPLATE_UPLAND, out_name
            )
            arcpy.AddMessage("Upland job ID: {}".format(jid))
            jobj = _wait_job(token, portal_url, jid)
            if jobj.get("jobStatus") == "esriJobFailed":
                msg = jobj.get("messages", "")
                if upl_ct == -1:
                    arcpy.AddWarning("Upland report job failed (skipping): {}".format(msg))
                else:
                    raise Exception("Upland report job failed: {}".format(msg))
            else:
                url, name = _get_result_pdf(jobj)
                if not url:
                    arcpy.AddWarning("Upland report returned no download URL.")
                else:
                    pth = os.path.join(tmp, name or (out_name + ".pdf"))
                    _download(url, pth, token)
                    parts.append(pth)
                    arcpy.AddMessage("Upland PDF downloaded: {}".format(pth))

        # ── merge all parts into the final output PDF ──────────────────────────
        if not parts:
            arcpy.AddError(
                "No PDF parts were produced.  "
                "Check the warnings above for details on why each template failed."
            )
            raise SystemExit(1)

        arcpy.AddMessage(
            "Merging {} PDF part(s) into output file: {}".format(len(parts), out_path)
        )
        pdfdoc = arcpy.mp.PDFDocumentCreate(out_path)
        for p in parts:
            pdfdoc.appendPages(p)
        pdfdoc.saveAndClose()
        arcpy.AddMessage("Export complete.  Output: {}".format(out_path))

    finally:
        # ── clean up temp files ────────────────────────────────────────────────
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
