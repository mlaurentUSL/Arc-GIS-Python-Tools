# -*- coding: utf-8 -*-
"""
Feature Class Field Builder
============================
ArcGIS Pro Script Tool (ArcPy)

Purpose
-------
Creates a new feature class at a specified path, or appends fields to an
existing feature class at that path.

Parameters (as configured in the Script Tool)
----------------------------------------------
0) append          (Boolean, Checkbox)
   If the output feature class already exists:
     - Checked  -> append new fields to the existing dataset.
     - Unchecked -> OVERWRITE: delete and recreate the feature class, then add fields.
   If the output feature class does not exist, this setting is ignored.

1) out_fc          (Feature Class, Output)
   Path to the new or existing feature class.

2) geometry_type   (String, Value List: POINT | POLYLINE | POLYGON)
   Geometry type used when creating a NEW feature class.
   Ignored when out_fc already exists AND append is checked.

3) text_fields     (String)
   Comma-separated field definition tokens for TEXT fields.

4) double_fields   (String)
   Comma-separated field definition tokens for DOUBLE fields.

5) long_fields     (String)
   Comma-separated field definition tokens for LONG fields.

6) short_fields    (String)
   Comma-separated field definition tokens for SHORT fields.

Field definition token format
-----------------------------
Tokens are comma-separated values.  Each token is either:
  - An integer  -> the ordering rank for the NEXT field name token
  - A string    -> a field name (optionally preceded by a rank integer)

Examples:
  "1,Asset ID,3,Community"
    * rank 1 -> Asset_ID   (TEXT)
    * rank 3 -> Community  (TEXT)

  "2,Diameter,4,Year,5,Elevation 2026"
    * rank 2 -> Diameter       (DOUBLE / LONG / SHORT depending on param)
    * rank 4 -> Year
    * rank 5 -> Elevation_2026  (space sanitized to _)

Ordering rules
--------------
- Ordering numbers are OPTIONAL.
- Partial or non-sequential ranks (e.g. 1,3,4,5,6) are compressed to
  sequential values while preserving relative order (-> 1,2,3,4,5).
- Unranked fields (no preceding number) appear AFTER all ranked fields,
  in their input order.

Field name sanitization
-----------------------
- Characters outside [A-Za-z0-9_] are replaced with "_".
- Multiple consecutive underscores are collapsed to one.
- Leading/trailing underscores are stripped.
- Names that start with a digit are prefixed with "F_".
- A warning is emitted whenever a name is modified.

Spatial reference (new feature classes)
----------------------------------------
- Uses arcpy.env.outputCoordinateSystem if set.
- Otherwise defaults to WGS 84 (EPSG:4326).

Undo notice
-----------
A warning is always emitted: geoprocessing operations of this type are
NOT undoable in the same way as edit operations inside an edit session.
"""

import os
import re
import arcpy


# ---------------------------------------------------------------------------
# Messaging helpers
# ---------------------------------------------------------------------------
def _msg(text):
    arcpy.AddMessage(str(text))

def _warn(text):
    arcpy.AddWarning(str(text))


def _err(text):
    arcpy.AddError(str(text))


# ---------------------------------------------------------------------------
# Field name sanitization
# ---------------------------------------------------------------------------
_RE_BAD_CHARS = re.compile(r"[^A-Za-z0-9_]+")
_RE_MULTI_US = re.compile(r"_+")


def sanitize_field_name(raw):
    """Return (sanitized_name, was_changed, list_of_reasons).

    Rules applied in order:
    1. Replace characters outside [A-Za-z0-9_] with '_'.
    2. Collapse consecutive underscores to a single '_'.
    3. Strip leading/trailing underscores.
    4. If the result starts with a digit, prefix 'F_'.
    5. If empty after all steps, fall back to 'FIELD'.
    """
    name = (raw or "").strip()
    original = name
    reasons = []

    replaced = _RE_BAD_CHARS.sub("_", name)
    if replaced != name:
        reasons.append("replaced non-alphanumeric/underscore characters with '_'")
    name = replaced

    collapsed = _RE_MULTI_US.sub("_", name)
    if collapsed != name:
        reasons.append("collapsed repeated '_' characters")
    name = collapsed

    stripped = name.strip("_")
    if stripped != name:
        reasons.append("stripped leading/trailing '_'")
    name = stripped

    if name and name[0].isdigit():
        name = "F_" + name
        reasons.append("prefixed 'F_' because field names cannot start with a digit")

    if not name:
        name = "FIELD"
        reasons.append("empty after sanitizing; renamed to 'FIELD'")

    was_changed = name != original
    return name, was_changed, reasons


# ---------------------------------------------------------------------------
# Field string parsing
# ---------------------------------------------------------------------------
def _tokenize(s):
    """Split on commas and return non-empty, stripped tokens."""
    if not s:
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def parse_field_string(field_string, param_label, type_label, base_order):
    """Parse a field definition string into a list of field descriptor dicts.

    Each descriptor:
        {
            "rank":   int | None,   # explicit ordering rank from input, or None
            "name":   str,          # sanitized field name
            "type":   str,          # "TEXT" | "DOUBLE" | "LONG" | "SHORT"
            "source": str,          # parameter name for warning messages
            "order":  int,          # stable insertion order (across all params)
        }

    Parameters
    ----------
    field_string : str
        Raw text-box input, e.g. "1,Asset ID,3,Community".
    param_label : str
        Human-readable parameter name for warnings.
    type_label : str
        ArcGIS field type string.
    base_order : int
        Added to local insertion index to give each param a non-overlapping
        range (ensures tie-breaking across params preserves param order).
    """
    tokens = _tokenize(field_string)
    results = []
    pending_rank = None
    local_idx = 0

    for token in tokens:
        # Is this token a rank integer?
        try:
            pending_rank = int(token)
            continue
        except ValueError:
            pass

        # It is a field name token.
        raw_name = token
        sanitized, changed, reasons = sanitize_field_name(raw_name)
        if changed:
            _warn(
                "[{src}] Field name '{orig}' was changed to '{new}' "
                "({reasons}).".format(
                    src=param_label,
                    orig=raw_name,
                    new=sanitized,
                    reasons="; ".join(reasons),
                )
            )

        results.append(
            {
                "rank": pending_rank,
                "name": sanitized,
                "type": type_label,
                "source": param_label,
                "order": base_order + local_idx,
            }
        )
        local_idx += 1
        pending_rank = None  # rank consumed by this name

    return results


# ---------------------------------------------------------------------------
# Rank compression
# ---------------------------------------------------------------------------
def compress_ranks(items):
    """Compress non-sequential explicit ranks to 1..N in relative order.

    Example: explicit ranks 1, 3, 4, 5, 6 -> reassigned 1, 2, 3, 4, 5.
    Unranked items (rank is None) are left unchanged.
    Items are modified in-place; the list is also returned.
    """
    ranked_values = sorted(
        {it["rank"] for it in items if it["rank"] is not None}
    )
    if not ranked_values:
        return items

    # Map each unique old rank to its new sequential value.
    rank_map = {old: new for new, old in enumerate(ranked_values, start=1)}
    for it in items:
        if it["rank"] is not None:
            it["rank"] = rank_map[it["rank"]]

    return items


# ---------------------------------------------------------------------------
# Final ordering
# ---------------------------------------------------------------------------
def build_ordered_fields(all_items):
    """Return items sorted for field creation.

    Sort key (primary -> secondary -> tertiary):
    1. Ranked items first (rank is not None), unranked last.
    2. By ascending rank value.
    3. By stable insertion order (base_order + local_idx), which encodes
       both parameter priority (text < double < long < short) and
       position within a parameter.
    """
    _BIG = 10 ** 9

    def _key(it):
        r = it["rank"]
        return (0 if r is not None else 1, r if r is not None else _BIG, it["order"])

    return sorted(all_items, key=_key)


# ---------------------------------------------------------------------------
# Feature class helpers
# ---------------------------------------------------------------------------
def ensure_feature_class(out_fc, geometry_type):
    """Create feature class if it does not exist.

    Returns True if the feature class already existed, False if it was created.
    """
    if arcpy.Exists(out_fc):
        _msg(
            "Output feature class already exists: {fc}\n"
            "Fields will be APPENDED to the existing dataset.  "
            "The geometry type parameter is ignored.".format(fc=out_fc)
        )
        return True

    workspace = os.path.dirname(out_fc)
    fc_name = os.path.basename(out_fc)

    if not workspace:
        raise arcpy.ExecuteError(
            "'out_fc' must include a workspace path "
            "(e.g., C:\\MyProject.gdb\\Assets)."
        )
    if not arcpy.Exists(workspace):
        raise arcpy.ExecuteError(
            "Workspace does not exist: {ws}".format(ws=workspace)
        )

    # Spatial reference
    sr = arcpy.env.outputCoordinateSystem
    if sr is None:
        sr = arcpy.SpatialReference(4326)  # WGS 84
        _msg(
            "No output coordinate system set in the environment.  "
            "Defaulting to WGS 84 (EPSG:4326)."
        )

    _msg(
        "Creating new {geom} feature class: {fc}".format(
            geom=geometry_type, fc=out_fc
        )
    )
    arcpy.management.CreateFeatureclass(
        out_path=workspace,
        out_name=fc_name,
        geometry_type=geometry_type,
        spatial_reference=sr,
    )
    return False


def add_fields_to_fc(out_fc, ordered_items):
    """Add fields to the feature class, skipping any that already exist."""
    existing_upper = {f.name.upper() for f in arcpy.ListFields(out_fc)}

    for it in ordered_items:
        fname = it["name"]
        ftype = it["type"]

        if fname.upper() in existing_upper:
            _warn(
                "Field '{name}' already exists in {fc} - skipping.".format(
                    name=fname, fc=out_fc
                )
            )
            continue

        kwargs = {"field_name": fname, "field_type": ftype}
        if ftype == "TEXT":
            kwargs["field_length"] = 255

        arcpy.management.AddField(out_fc, **kwargs)
        existing_upper.add(fname.upper())  # track to avoid re-adding within same run
        _msg("  Added {type} field: {name}".format(type=ftype, name=fname))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    # ------------------------------------------------------------------
    # Read parameters
    # ------------------------------------------------------------------
    append_existing = arcpy.GetParameter(0)          # Boolean (Checkbox)
    out_fc = arcpy.GetParameterAsText(1)             # Feature Class (Output)
    geometry_type = arcpy.GetParameterAsText(2)      # String value list
    text_fields = arcpy.GetParameterAsText(3)        # String
    double_fields = arcpy.GetParameterAsText(4)      # String
    long_fields = arcpy.GetParameterAsText(5)        # String
    short_fields = arcpy.GetParameterAsText(6)       # String

    # arcpy.GetParameter(0) can return None if the parameter isn't wired correctly.
    append_existing = bool(append_existing)

    if not out_fc:
        raise arcpy.ExecuteError("Parameter 'out_fc' is required.")

    if not geometry_type:
        geometry_type = "POINT"

    # ------------------------------------------------------------------
    # Undo notice
    # ------------------------------------------------------------------
    _warn(
        "IMPORTANT: This geoprocessing operation is NOT undoable in the "
        "way that edit operations are.  Verify your inputs before running."
    )

    # ------------------------------------------------------------------
    # Create / overwrite / append behavior
    # ------------------------------------------------------------------
    if arcpy.Exists(out_fc):
        if append_existing:
            _msg(
                "Output feature class already exists: {fc}\n"
                "Append is enabled; fields will be added to the existing dataset.  "
                "The geometry type parameter is ignored.".format(fc=out_fc)
            )
        else:
            _warn(
                "Output feature class already exists: {fc}\n"
                "Append is disabled; the existing dataset will be OVERWRITTEN "
                "(deleted and recreated) before adding fields.".format(fc=out_fc)
            )
            try:
                arcpy.management.Delete(out_fc)
            except Exception:
                # If Delete fails, let ArcPy surface the underlying geoprocessing error.
                raise

    # Ensure the feature class exists (create if needed). If we overwrote, it no
    # longer exists, so this will create it.
    ensure_feature_class(out_fc, geometry_type)

    # ------------------------------------------------------------------
    # Parse all field strings
    # ------------------------------------------------------------------
    # base_order values give non-overlapping ranges so that across parameters
    # the order is: text -> double -> long -> short
    text_items = parse_field_string(text_fields, "text_fields", "TEXT", base_order=0)
    double_items = parse_field_string(double_fields, "double_fields", "DOUBLE", base_order=100_000)
    long_items = parse_field_string(long_fields, "long_fields", "LONG", base_order=200_000)
    short_items = parse_field_string(short_fields, "short_fields", "SHORT", base_order=300_000)

    all_items = text_items + double_items + long_items + short_items

    ordered = []
    if not all_items:
        _warn(
            "No field definitions were provided.  "
            "The feature class will be created (if needed) with no additional fields."
        )
    else:
        # Compress non-sequential / partial ranks then build final order once.
        compress_ranks(all_items)
        ordered = build_ordered_fields(all_items)

        _msg("Fields to be created (in final order):")
        for idx, it in enumerate(ordered, start=1):
            rank_str = str(it["rank"]) if it["rank"] is not None else "unranked"
            _msg(
                "  {idx}. {name:<30}  type={type:<6}  rank={rank}  "
                "source={src}".format(
                    idx=idx,
                    name=it["name"],
                    type=it["type"],
                    rank=rank_str,
                    src=it["source"],
                )
            )

    # ------------------------------------------------------------------
    # Add fields
    # ------------------------------------------------------------------
    if ordered:
        add_fields_to_fc(out_fc, ordered)

    # ------------------------------------------------------------------
    # Derive output parameter (required for Output parameter type)
    # ------------------------------------------------------------------
    arcpy.SetParameterAsText(1, out_fc)
    _msg("Done.")


# ---------------------------------------------------------------------------
# Script entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except arcpy.ExecuteError:
        _err(arcpy.GetMessages(2))
        raise
    except Exception as exc:
        _err(str(exc))
        raise