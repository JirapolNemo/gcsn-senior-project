"""Key-aligned CSV comparison — fixes the row-position bug in Distinct_Data.py.

The original print_content_diff()/export_content_diff_excel() compared row N of
file A against row N of file B directly. Once one edge is inserted, removed, or
reordered anywhere in the file, every following row shifts out of alignment and
the script reports hundreds of false "value differs" cells for edges that are
actually unrelated to each other.

This module instead keys every row by (origin, destination) before comparing,
so a real content change on a given route is only reported if THAT route's row
actually changed — insertions/removals of other routes no longer cascade.

Drop this file next to Distinct_Data.py and import the two functions below in
place of print_content_diff / export_content_diff_excel. The CLI flags and
other functions in Distinct_Data.py (file discovery, hashing, set report, etc.)
are unaffected and can stay as-is.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZIP_DEFLATED, ZipFile

ORIGIN_COL = 1       # 0-based index of the 'origin' column
DESTINATION_COL = 3  # 0-based index of the 'destination' column


def read_csv_dicts(path: Path) -> tuple[list[str], dict[tuple[str, str], list[str]]]:
    """Read a CSV and key every data row by (origin, destination).

    Returns (header, {key: row}). If the same (origin, destination) pair
    appears more than once in one file (shouldn't happen, but worth knowing),
    the LAST occurrence wins and a warning is printed.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.reader(file))
    if not rows:
        return [], {}
    header, data = rows[0], rows[1:]
    keyed: dict[tuple[str, str], list[str]] = {}
    dup_keys = 0
    for row in data:
        if len(row) <= max(ORIGIN_COL, DESTINATION_COL):
            continue
        key = (row[ORIGIN_COL].strip(), row[DESTINATION_COL].strip())
        if key in keyed:
            dup_keys += 1
        keyed[key] = row
    if dup_keys:
        print(f"  [warn] {path.name}: {dup_keys} duplicate (origin,destination) "
              f"keys found — only the last row for each was kept")
    return header, keyed


def cells_match(left: str, right: str, numeric_tolerance: float) -> bool:
    if left == right:
        return True
    try:
        return math.isclose(float(left), float(right),
                             rel_tol=numeric_tolerance, abs_tol=numeric_tolerance)
    except ValueError:
        return False


def compare_keyed(
    path_a: Path,
    path_b: Path,
    numeric_tolerance: float = 1e-9,
) -> dict:
    """Compare two CSVs by (origin, destination) key instead of row position.

    Returns a dict with:
      - removed: keys present in A but not B (edge disappeared)
      - added: keys present in B but not A (edge appeared)
      - modified: {key: [(column_name, value_a, value_b), ...]} for keys in
        both files where at least one cell genuinely differs
      - unchanged_count: number of matched keys with zero real differences
    """
    header_a, rows_a = read_csv_dicts(path_a)
    header_b, rows_b = read_csv_dicts(path_b)
    header = header_a if len(header_a) >= len(header_b) else header_b

    keys_a, keys_b = set(rows_a), set(rows_b)
    removed = sorted(keys_a - keys_b)
    added = sorted(keys_b - keys_a)
    common = keys_a & keys_b

    modified: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    unchanged_count = 0
    for key in common:
        row_a, row_b = rows_a[key], rows_b[key]
        cell_diffs = []
        for col_idx in range(max(len(row_a), len(row_b))):
            val_a = row_a[col_idx] if col_idx < len(row_a) else ""
            val_b = row_b[col_idx] if col_idx < len(row_b) else ""
            if not cells_match(val_a, val_b, numeric_tolerance):
                col_name = header[col_idx] if col_idx < len(header) else f"col{col_idx}"
                cell_diffs.append((col_name, val_a, val_b))
        if cell_diffs:
            modified[key] = cell_diffs
        else:
            unchanged_count += 1

    return {
        "header": header,
        "removed": removed,
        "added": added,
        "modified": modified,
        "unchanged_count": unchanged_count,
    }


def print_keyed_diff(path_a: Path, path_b: Path, numeric_tolerance: float = 1e-9) -> None:
    """Human-readable report using key-aligned comparison."""
    result = compare_keyed(path_a, path_b, numeric_tolerance)
    print(f"\n{path_a.name}  (A: {path_a})")
    print(f"vs  {path_b.name}  (B: {path_b})")
    print(f"Matched routes unchanged: {result['unchanged_count']}")
    print(f"Matched routes with real cell differences: {len(result['modified'])}")
    print(f"Routes only in A (removed/renamed-away): {len(result['removed'])}")
    print(f"Routes only in B (added/renamed-in): {len(result['added'])}")

    if result["removed"]:
        print("\nRoutes present in A but missing in B:")
        for origin, dest in result["removed"][:20]:
            print(f"  {origin} -> {dest}")
        if len(result["removed"]) > 20:
            print(f"  ... and {len(result['removed']) - 20} more")

    if result["added"]:
        print("\nRoutes present in B but missing in A:")
        for origin, dest in result["added"][:20]:
            print(f"  {origin} -> {dest}")
        if len(result["added"]) > 20:
            print(f"  ... and {len(result['added']) - 20} more")

    if result["modified"]:
        print("\nRoutes present in both, with real cell differences:")
        for (origin, dest), diffs in list(result["modified"].items())[:20]:
            print(f"  {origin} -> {dest}:")
            for col_name, val_a, val_b in diffs:
                print(f"      {col_name}: {val_a!r} -> {val_b!r}")
        if len(result["modified"]) > 20:
            print(f"  ... and {len(result['modified']) - 20} more routes with diffs")


def excel_column_letter(column_number: int) -> str:
    letters = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def export_keyed_diff_excel(
    file_pairs: list[tuple[str, Path, Path]],
    output_file: Path,
    numeric_tolerance: float = 1e-9,
) -> None:
    """Export key-aligned differences across many date/file pairs to one .xlsx.

    file_pairs: list of (date_label, path_a, path_b).
    """
    header = [
        "File Name", "Diff Kind", "Origin", "Destination",
        "Column", "Value A", "Value B",
    ]
    rows = [header]

    for date_label, path_a, path_b in file_pairs:
        result = compare_keyed(path_a, path_b, numeric_tolerance)
        for origin, dest in result["removed"]:
            rows.append([date_label, "Route removed in B", origin, dest, "", "", ""])
        for origin, dest in result["added"]:
            rows.append([date_label, "Route added in B", origin, dest, "", "", ""])
        for (origin, dest), diffs in result["modified"].items():
            for col_name, val_a, val_b in diffs:
                rows.append([date_label, "Value changed", origin, dest, col_name, val_a, val_b])

    if len(rows) == 1:
        rows.append(["No differences", "", "", "", "", "", ""])

    def cell_xml(row_number: int, column_number: int, value: str) -> str:
        cell_ref = f"{excel_column_letter(column_number)}{row_number}"
        return (f'<c r={quoteattr(cell_ref)} t="inlineStr">'
                f"<is><t>{escape(str(value))}</t></is></c>")

    def worksheet_xml(rows: list[list[str]]) -> str:
        row_xml = []
        for row_number, row in enumerate(rows, start=1):
            cells = "".join(cell_xml(row_number, col_num, value)
                             for col_num, value in enumerate(row, start=1))
            row_xml.append(f'<row r="{row_number}">{cells}</row>')
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{''.join(row_xml)}</sheetData></worksheet>")

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="KeyedDifferences" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    root_relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    with ZipFile(output_file, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types)
        workbook.writestr("_rels/.rels", root_relationships)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet_xml(rows))

    print(f"Keyed diff Excel created: {output_file}")
    print(f"Total diff rows (route added/removed/changed): {len(rows) - 1}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python keyed_diff.py <file_a.csv> <file_b.csv>")
        raise SystemExit(1)
    print_keyed_diff(Path(sys.argv[1]), Path(sys.argv[2]))
