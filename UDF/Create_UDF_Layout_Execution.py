import arcpy
import os
import tempfile
import uuid

def parse_layout_numbers(layout_string):
    numbers = set()
    tokens = [token.strip() for token in layout_string.split(',')]
    for token in tokens:
        if '-' in token:
            start, end = map(int, token.split('-'))
            numbers.update(range(start, end + 1))
        else:
            numbers.add(int(token))
    return sorted(numbers)

def create_udf_layouts(layout_numbers_str, source_layout_name, flushing_fc):
    arcpy.AddMessage("=== Creating layouts and zooming to features ===")

    try:
        layout_numbers = parse_layout_numbers(layout_numbers_str)
        arcpy.AddMessage(f"Parsed layout numbers: {layout_numbers}")
    except Exception as e:
        arcpy.AddError(f"Invalid layout number input: {e}")
        return

    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        arcpy.AddMessage(f"ArcPy Version: {arcpy.__version__}")
    except Exception as e:
        arcpy.AddError(f"Could not access current project: {e}")
        return

    source_layout = next((l for l in aprx.listLayouts() if l.name == source_layout_name), None)
    if not source_layout:
        arcpy.AddError(f"Layout '{source_layout_name}' not found in current project.")
        return

    target_map = next((m for m in aprx.listMaps() if m.name == "UDF Basemap Data"), None)
    if not target_map:
        arcpy.AddError("Map named 'UDF Basemap Data' not found in current project.")
        return

    temp_pagx = os.path.join(tempfile.gettempdir(), f"_temp_{uuid.uuid4().hex}.pagx")
    source_layout.exportToPAGX(temp_pagx)

    temp_layer = "temp_flushing_layer"
    arcpy.MakeFeatureLayer_management(flushing_fc, temp_layer)
    arcpy.management.SelectLayerByAttribute(temp_layer, "CLEAR_SELECTION")

    maps_before = set(m.name for m in aprx.listMaps())

    for num in layout_numbers:
        layout_name = f"UDF Route {num}".strip()

        if any(l.name == layout_name for l in aprx.listLayouts()):
            arcpy.AddMessage(f"Skipped: Layout '{layout_name}' already exists.")
            continue

        try:
            layout = aprx.importDocument(temp_pagx)
            layout.name = layout_name

            maps_after = aprx.listMaps()
            imported_maps = [m for m in maps_after if m.name not in maps_before and m.name != "UDF Basemap Data"]
            for m in imported_maps:
                try:
                    aprx.deleteMap(m)
                    arcpy.AddMessage(f"Removed extra map: {m.name}")
                except:
                    pass

            map_frames = layout.listElements("MAPFRAME_ELEMENT")
            if not map_frames:
                arcpy.AddWarning(f"No map frame found in layout: {layout_name}")
                continue

            mf = map_frames[0]
            mf.map = target_map

            arcpy.management.SelectLayerByAttribute(temp_layer, "NEW_SELECTION", f'"RTENUM" = {num}')
            count = int(arcpy.GetCount_management(temp_layer)[0])
            arcpy.AddMessage(f"Selected features for RTENUM {num}: {count}")

            with arcpy.da.SearchCursor(temp_layer, ["SHAPE@", "MAPSCALE"] ) as cursor:
                feature = next(cursor, None)
                if feature:
                    shape, mapscale = feature
                    sr = mf.map.spatialReference
                    extent = shape.projectAs(sr).extent

                    x_center = (extent.XMin + extent.XMax) / 2.0
                    y_center = (extent.YMin + extent.YMax) / 2.0
                    width = extent.XMax - extent.XMin
                    height = extent.YMax - extent.YMin

                    x_buffer = width * 0.1
                    y_buffer = height * 0.1

                    buffered_extent = arcpy.Extent(
                        x_center - (width / 2 + x_buffer),
                        y_center - (height / 2 + y_buffer),
                        x_center + (width / 2 + x_buffer),
                        y_center + (height / 2 + y_buffer)
                    )

                    mf.camera.setExtent(buffered_extent)

                    if mapscale is not None:
                        mf.camera.scale = mapscale
                        arcpy.AddMessage(f"Zoomed to RTENUM {num} at MAPSCALE 1:{mf.camera.scale}")
                    else:
                        scale = max(int(round(mf.camera.scale / 100.0)) * 100, 500)
                        mf.camera.scale = scale
                        arcpy.AddMessage(f"Zoomed to RTENUM {num} at ~1:{mf.camera.scale}")
                else:
                    arcpy.AddWarning(f"No feature with RTENUM = {num} found.")

            arcpy.management.SelectLayerByAttribute(temp_layer, "CLEAR_SELECTION")
            arcpy.AddMessage(f"Created layout: {layout_name}")

        except Exception as e:
            arcpy.AddError(f"Failed to create layout {layout_name}: {e}")

    try:
        arcpy.management.SelectLayerByAttribute(temp_layer, "CLEAR_SELECTION")
        arcpy.Delete_management(temp_layer)
    except:
        pass

    arcpy.AddMessage("Layout creation complete.")

create_udf_layouts(
    arcpy.GetParameterAsText(0),
    arcpy.GetParameterAsText(1),
    arcpy.GetParameterAsText(2)
)
