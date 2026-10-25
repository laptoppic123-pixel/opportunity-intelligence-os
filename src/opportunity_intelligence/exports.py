"""Dependency-light genuine OOXML, CSV and Markdown exports from one DB snapshot."""

import csv
from datetime import datetime, timezone
from io import StringIO, BytesIO
import json
from pathlib import Path
import zipfile
from xml.etree.ElementTree import Element, SubElement, tostring
from .safety import redact, spreadsheet_text
from .services import ideas_view

SHEETS = {
    "Ideas": "opportunities",
    "Problems": "problem_clusters",
    "Sources Evidence": "opportunity_evidence",
    "Competitors": "competitors",
    "Spending": "spending_signals",
    "Scores": "scores",
    "Research Tasks": "research_queue",
    "Usage & Cost": "provider_usage",
    "History": "score_history",
}


def project(store):
    snapshot = store.snapshot()
    observations = {o["id"]: o for o in snapshot["raw_observations"]}
    ideas = ideas_view_from_snapshot(snapshot)
    result = {
        "Dashboard": [
            {
                "metric": "Dataset",
                "value": "DEMO / SYNTHETIC DATA" if store.settings.demo else "Canonical Supabase records",
            },
            {"metric": "Ideas", "value": len(ideas)},
            {"metric": "Observed documents", "value": len(observations)},
            {"metric": "Customer validated", "value": sum(bool(i.get("customer_validated")) for i in ideas)},
            {
                "metric": "Live LLM assessments",
                "value": sum(i.get("analysis_method") == "llm-assisted" for i in ideas),
            },
            {
                "metric": "External cost USD",
                "value": sum(u.get("actual_cost") or 0 for u in snapshot["provider_usage"]),
            },
        ]
    }
    for sheet, table in SHEETS.items():
        result[sheet] = ideas if table == "opportunities" else snapshot[table]
    result["Sources Evidence"] = [
        {
            **e,
            "source_url": observations.get(e.get("observation_id"), {}).get("url"),
            "source_title": observations.get(e.get("observation_id"), {}).get("title"),
            "synthetic": observations.get(e.get("observation_id"), {}).get("synthetic"),
            "license": observations.get(e.get("observation_id"), {}).get("license"),
            "observed_at": observations.get(e.get("observation_id"), {}).get("observed_at"),
            "access_status": observations.get(e.get("observation_id"), {}).get("access_status"),
            "published_at": observations.get(e.get("observation_id"), {}).get("published_at"),
        }
        for e in result["Sources Evidence"]
    ]
    result["Speculative Gems"] = [i for i in ideas if i.get("status") == "speculative"]
    result["Settings"] = [
        {"name": "OI_LIVE_ENABLED", "value": store.settings.live},
        {"name": "OI_PAID_ENABLED", "value": store.settings.paid},
        {"name": "monthly_limit_usd", "value": float(store.settings.monthly_limit)},
        {"name": "internal_paid_stop_usd", "value": float(store.settings.paid_stop)},
        {"name": "export_time_utc", "value": datetime.now(timezone.utc).isoformat()},
        {
            "name": "score_meaning",
            "value": "Assessed weighted score, not probability of success. Nulls remain unknown.",
        },
    ]
    # Fixed required order, useful for comparing snapshot-consistent output across formats.
    order = [
        "Dashboard",
        "Ideas",
        "Problems",
        "Sources Evidence",
        "Competitors",
        "Spending",
        "Scores",
        "Speculative Gems",
        "Research Tasks",
        "Usage & Cost",
        "History",
        "Settings",
    ]
    return {name: redact(result[name]) for name in order}


def ideas_view_from_snapshot(snapshot):
    scores = {s["opportunity_id"]: s for s in snapshot["scores"]}
    return [
        {
            **i,
            "weighted_score": scores.get(i["id"], {}).get("weighted_score"),
            "coverage": scores.get(i["id"], {}).get("coverage", 0),
        }
        for i in snapshot["opportunities"]
    ]


def columns(rows):
    return list(dict.fromkeys(k for r in rows for k in r)) or ["status"]


def display(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def csv_bytes(rows):
    out = StringIO(newline="")
    cols = columns(rows)
    writer = csv.DictWriter(out, fieldnames=cols)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: spreadsheet_text(display(r.get(k))) for k in cols})
    return ("\ufeff" + out.getvalue()).encode("utf-8")


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def xml(element):
    return tostring(element, encoding="utf-8", xml_declaration=True)


def letter(i):
    result = ""
    while i:
        i, n = divmod(i - 1, 26)
        result = chr(65 + n) + result
    return result


def xlsx_bytes(sheets, *, demo=False):
    buffer = BytesIO()
    package = "http://schemas.openxmlformats.org/package/2006/relationships"
    content = "http://schemas.openxmlformats.org/package/2006/content-types"
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        types = Element("Types", xmlns=content)
        for ext, typ in [
            ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
            ("xml", "application/xml"),
        ]:
            SubElement(types, "Default", Extension=ext, ContentType=typ)
        rootrels = Element("Relationships", xmlns=package)
        SubElement(
            rootrels, "Relationship", Id="rId1", Type=REL + "/officeDocument", Target="xl/workbook.xml"
        )
        z.writestr("_rels/.rels", xml(rootrels))
        workbook = Element("workbook", xmlns=NS, attrib={"xmlns:r": REL})
        tablist = SubElement(workbook, "sheets")
        wrels = Element("Relationships", xmlns=package)
        for idx, (name, rows) in enumerate(sheets.items(), 1):
            SubElement(tablist, "sheet", name=name, sheetId=str(idx), attrib={"r:id": f"rId{idx}"})
            SubElement(
                wrels,
                "Relationship",
                Id=f"rId{idx}",
                Type=REL + "/worksheet",
                Target=f"worksheets/sheet{idx}.xml",
            )
            SubElement(
                types,
                "Override",
                PartName=f"/xl/worksheets/sheet{idx}.xml",
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            )
            sheet = Element("worksheet", xmlns=NS, attrib={"xmlns:r": REL})
            view = SubElement(SubElement(sheet, "sheetViews"), "sheetView", workbookViewId="0")
            SubElement(view, "pane", ySplit="2", topLeftCell="A3", activePane="bottomLeft", state="frozen")
            cols = columns(rows)
            widths = SubElement(sheet, "cols")
            for j, col in enumerate(cols, 1):
                SubElement(
                    widths,
                    "col",
                    min=str(j),
                    max=str(j),
                    width=str(
                        48
                        if any(s in col for s in ["url", "claim", "problem", "solution", "excerpt"])
                        else 24
                    ),
                    customWidth="1",
                )
            data = SubElement(sheet, "sheetData")
            links = []
            matrix = [
                ["DEMO / SYNTHETIC DATA" if demo else "Opportunity Intelligence OS · canonical export"],
                cols,
            ]
            matrix.extend([[r.get(c) for c in cols] for r in rows])
            for ridx, values in enumerate(matrix, 1):
                row = SubElement(data, "row", r=str(ridx), ht="30" if ridx <= 2 else "22", customHeight="1")
                for cidx, value in enumerate(values, 1):
                    addr = f"{letter(cidx)}{ridx}"
                    style = "1" if ridx <= 2 else "0"
                    if value is None:
                        SubElement(row, "c", r=addr, s=style)
                        continue
                    if ridx > 2 and isinstance(value, str) and cols[cidx - 1].endswith(("_at", "_date")):
                        try:
                            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
                            if instant.tzinfo:
                                instant = instant.astimezone(timezone.utc).replace(tzinfo=None)
                            serial = (instant - datetime(1899, 12, 30)).total_seconds() / 86400
                            cell = SubElement(row, "c", r=addr, s="2")
                            SubElement(cell, "v").text = str(serial)
                            continue
                        except ValueError:
                            pass
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        cell = SubElement(row, "c", r=addr, s=style)
                        SubElement(cell, "v").text = str(value)
                    else:
                        cell = SubElement(row, "c", r=addr, s=style, t="inlineStr")
                        SubElement(SubElement(cell, "is"), "t").text = spreadsheet_text(display(value))[
                            :32700
                        ]
                        if (
                            isinstance(value, str)
                            and value.startswith(("https://", "http://"))
                            and "url" in cols[cidx - 1].lower()
                            and ridx > 2
                        ):
                            links.append((addr, value))
            SubElement(sheet, "autoFilter", ref=f"A2:{letter(len(cols))}{max(2, len(matrix))}")
            if links:
                hyperlinks = SubElement(sheet, "hyperlinks")
                rels = Element("Relationships", xmlns=package)
                for n, (addr, url) in enumerate(links, 1):
                    SubElement(hyperlinks, "hyperlink", ref=addr, attrib={"r:id": f"rId{n}"})
                    SubElement(
                        rels,
                        "Relationship",
                        Id=f"rId{n}",
                        Type=REL + "/hyperlink",
                        Target=url,
                        TargetMode="External",
                    )
                z.writestr(f"xl/worksheets/_rels/sheet{idx}.xml.rels", xml(rels))
            SubElement(
                sheet,
                "pageMargins",
                left="0.3",
                right="0.3",
                top="0.5",
                bottom="0.5",
                header="0.2",
                footer="0.2",
            )
            z.writestr(f"xl/worksheets/sheet{idx}.xml", xml(sheet))
        SubElement(
            wrels, "Relationship", Id=f"rId{len(sheets) + 1}", Type=REL + "/styles", Target="styles.xml"
        )
        z.writestr("xl/workbook.xml", xml(workbook))
        z.writestr("xl/_rels/workbook.xml.rels", xml(wrels))
        z.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd hh:mm"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF152437"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>""",
        )
        for part, typ in [("workbook", "sheet.main"), ("styles", "styles")]:
            SubElement(
                types,
                "Override",
                PartName=f"/xl/{part}.xml",
                ContentType=f"application/vnd.openxmlformats-officedocument.spreadsheetml.{typ}+xml",
            )
        z.writestr("[Content_Types].xml", xml(types))
    return buffer.getvalue()


def markdown(sheets):
    lines = [
        "# Opportunity Intelligence OS research summary",
        "",
        str(sheets["Dashboard"][0]["value"]),
        "",
        "Scores are assessed rankings, never probabilities of profit or validation.",
        "",
    ]
    evidence = sheets["Sources Evidence"]
    for idea in sheets["Ideas"]:
        lines += [
            "## " + idea["title"],
            "",
            f"Track: {idea.get('track')} · Status: {idea.get('status')} · Method: {idea.get('analysis_method')}",
            "",
            "Problem: " + str(idea.get("problem") or "unknown"),
            "",
            "Hypothesis: " + str(idea.get("solution") or "unknown"),
            "",
            "Unknowns: " + display(idea.get("unknowns")),
            "",
        ]
        for e in evidence:
            if e["opportunity_id"] == idea["id"]:
                lines.append(
                    f"- {e['claim_type']}: {e['claim']} ([original source]({e.get('source_url') or ''}))"
                )
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def export_all(store, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sheets = project(store)
    (directory / "opportunities.xlsx").write_bytes(xlsx_bytes(sheets, demo=store.settings.demo))
    (directory / "research-summary.md").write_bytes(markdown(sheets))
    for name, rows in sheets.items():
        (directory / (name.lower().replace(" ", "_").replace("&", "and") + ".csv")).write_bytes(
            csv_bytes(rows)
        )
    return {"ideas": len(sheets["Ideas"]), "sheets": len(sheets), "directory": str(directory)}
