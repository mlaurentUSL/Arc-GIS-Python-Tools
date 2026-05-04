# -*- coding: utf-8 -*-
"""
Enviro_Report_Export.pyt
ArcGIS Pro Python Toolbox – Survey123 Feature Report Export

Thin toolbox wrapper.  All business logic lives in survey123_feature_report.py,
which must be in the same folder as this .pyt file.
"""

import arcpy
import os
import sys

# ── Make sure the sibling module is importable ─────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


class Toolbox:
    def __init__(self):
        self.label = "Enviro Report Export"
        self.alias = "EnviroReportExport"
        self.tools = [EnviroReportExport]


class EnviroReportExport:
    """Export a merged Wetland/Upland Survey123 Feature Report PDF."""

    def __init__(self):
        self.label = "Export Survey123 Feature Report"
        self.description = (
            "Queries the Survey123 parent feature service, lets the user pick a "
            "project submission from a dropdown, generates Wetland and/or Upland "
            "feature-report PDFs via the Survey123 report API, and merges them into "
            "a single output PDF using ArcGIS Pro."
        )
        self.canRunInBackground = False

    # ── Parameters ─────────────────────────────────────────────────────────────

    def getParameterInfo(self):
        # Parameter 0 – Survey submission dropdown
        p0 = arcpy.Parameter(
            displayName="Survey Submission",
            name="survey_submission",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        p0.filter.type = "ValueList"
        p0.filter.list = ["Loading..."]

        # Parameter 1 – Output PDF file path (browse-style output)
        p1 = arcpy.Parameter(
            displayName="Output PDF File",
            name="output_pdf",
            datatype="DEFile",
            parameterType="Required",
            direction="Output",
        )
        p1.filter.list = ["pdf"]

        return [p0, p1]

    def isLicensed(self):
        return True

    # ── Validator logic (ToolValidator equivalent in .pyt) ─────────────────────

    def updateParameters(self, parameters):
        """
        Dynamically populate the Survey Submission dropdown.

        The list is fetched once and cached: if the dropdown already contains
        real entries (anything other than the single "Loading..." placeholder)
        it is left unchanged.  This prevents an expensive REST call on every
        parameter-change event.
        """
        p0 = parameters[0]
        current = list(p0.filter.list) if p0.filter.list else []

        # Skip refresh if the list is already populated with real values
        if current and not (len(current) == 1 and current[0] == "Loading..."):
            return

        try:
            import survey123_feature_report as sfr
            labels = sfr.get_submission_labels()
        except Exception:
            labels = ["Loading..."]

        p0.filter.list = labels

    def updateMessages(self, parameters):
        pass

    # ── Execution ──────────────────────────────────────────────────────────────

    def execute(self, parameters, messages):
        import survey123_feature_report as sfr

        sel = parameters[0].valueAsText or ""
        out_path = parameters[1].valueAsText or ""

        # Enforce .pdf extension even if the user omitted it
        if out_path and not out_path.lower().endswith(".pdf"):
            out_path += ".pdf"

        sfr.export_feature_report(sel, out_path)

    def postExecute(self, parameters):
        pass
