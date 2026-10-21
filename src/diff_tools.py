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

import ast
import csv
import math
import re
from collections import Counter, defaultdict
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


def transit_times_match(left: str, right: str) -> bool:
    import ast
    try:
        set_a = sorted(ast.literal_eval(left))
        set_b = sorted(ast.literal_eval(right))
        return set_a == set_b
    except (ValueError, SyntaxError):
        return left == right


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
            col_name = header[col_idx] if col_idx < len(header) else f"col{col_idx}"

            if col_name == "available_transit_times":
                is_match = transit_times_match(val_a, val_b)
            else:
                is_match = cells_match(val_a, val_b, numeric_tolerance)

            if not is_match:
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


def find_rename_candidates(path_a, path_b, numeric_tolerance=1e-9):
    """หา candidate ว่าเส้นทางที่ removed คู่ไหน น่าจะเป็นเส้นทางเดียวกับที่ added คู่ไหน"""
    header_a, rows_a = read_csv_dicts(path_a)
    header_b, rows_b = read_csv_dicts(path_b)
    result = compare_keyed(path_a, path_b, numeric_tolerance)

    candidates = []
    matched_removed_keys = set()
    matched_added_keys = set()

    for (o1, d1) in result["removed"]:
        row_a = rows_a[(o1, d1)]
        for (o2, d2) in result["added"]:
            row_b = rows_b[(o2, d2)]
            same_dest = (d1 == d2 and o1 != o2)
            same_origin = (o1 == o2 and d1 != d2)
            if not (same_dest or same_origin):
                continue

            match_count, total = 0, 0
            mismatch_cols = []
            for col_idx in range(1, max(len(row_a), len(row_b))):   # เริ่มที่ 1 = ข้าม period
                val_a = row_a[col_idx] if col_idx < len(row_a) else ""
                val_b = row_b[col_idx] if col_idx < len(row_b) else ""
                col_name = header_a[col_idx] if col_idx < len(header_a) else f"col{col_idx}"
                if col_name == "available_transit_times":
                    is_match = transit_times_match(val_a, val_b)
                else:
                    is_match = cells_match(val_a, val_b, numeric_tolerance)

                if col_idx >= 5:            # score นับเฉพาะ 13 column หลัง
                    total += 1
                    if is_match:
                        match_count += 1
                if not is_match:            # แต่รายชื่อที่ไม่ตรงเก็บทุก column
                    mismatch_cols.append(col_name)

            ratio = (match_count / total) if total else 0.0
            candidates.append({
                "old_key": (o1, d1),
                "new_key": (o2, d2),
                "match_score": f"{match_count}/{total}",
                "match_ratio": round(ratio, 4),
                "mismatch_columns": ", ".join(mismatch_cols),
                "changed_side": "origin" if same_dest else "destination",
            })
            matched_removed_keys.add((o1, d1))
            matched_added_keys.add((o2, d2))

    unmatched_removed = [k for k in result["removed"] if k not in matched_removed_keys]
    unmatched_added = [k for k in result["added"] if k not in matched_added_keys]

    return {
        "candidates": candidates,
        "unmatched_removed": unmatched_removed,
        "unmatched_added": unmatched_added,
    }


# ===========================================================================
# Fingerprint matching — หาท่าเรือที่เปลี่ยนรหัสด้วย "ลายนิ้วมือ" ของค่าตัวเลข
# ===========================================================================
#
# ลายนิ้วมือ = ค่าของคอลัมน์สถิติ (connections ... available_transit_times)
# ต่อกันเป็นชุดเดียว โดยไม่รวม companies / ชื่อท่า / รหัส origin-destination
# แถวสองแถวที่ลายนิ้วมือเหมือนกันแต่ key (origin, destination) ต่างกัน
# = น่าจะเป็นเส้นทางเดียวกันที่ถูกเปลี่ยนรหัส (ไม่ว่าจะเปลี่ยนปลายไหน)

STATS_START_COL = 5                     # คอลัมน์ 0-4 = period, origin, namea, destination, nameb
NAMEA_COL = 2
NAMEB_COL = 4
FINGERPRINT_SKIP_COLS = ("companies",)  # คอลัมน์ที่ไม่เอามาทำลายนิ้วมือ
MIN_SUPPORT_OK = 3                      # เส้นทางแบบ 1:1 อย่างน้อยกี่เส้น ถึงถือว่า "น่าเชื่อ" ในตารางระดับท่าเรือ


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _normalize_cell(col_name: str, value: str, decimals: int):
    """ทำให้ค่าเทียบกันได้: ตัวเลขปัดทศนิยม, transit times เรียงลำดับก่อน"""
    value = value.strip()
    if col_name == "available_transit_times":
        try:
            return tuple(sorted(ast.literal_eval(value)))
        except (ValueError, SyntaxError, TypeError):
            return value
    try:
        return round(float(value), decimals)
    except ValueError:
        return value


def fingerprint_columns(header_a: list[str], header_b: list[str]) -> list[str]:
    """คอลัมน์ที่ใช้ทำลายนิ้วมือ = คอลัมน์สถิติที่มีทั้งสองไฟล์ (เทียบตามชื่อ ไม่ใช่ตำแหน่ง)
    ทำให้ไฟล์ที่มีคอลัมน์ไม่ครบ (เช่น 20110925.csv) ยังเทียบได้ด้วยคอลัมน์ที่มีร่วมกัน"""
    names_b = set(header_b[STATS_START_COL:])
    return [name for name in header_a[STATS_START_COL:]
            if name in names_b and name not in FINGERPRINT_SKIP_COLS]


def fingerprints_for_file(rows: dict, header: list[str], columns: list[str], decimals: int) -> dict:
    index = {name: i for i, name in enumerate(header)}
    return {
        key: tuple(_normalize_cell(name, _cell(row, index[name]), decimals) for name in columns)
        for key, row in rows.items()
    }


def count_data_rows(path: Path) -> int:
    """จำนวนแถวข้อมูลดิบในไฟล์ (ไม่นับ header และบรรทัดว่าง) ใช้เช็คว่าไม่มีแถวหายตอนทำ key"""
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return max(sum(1 for row in csv.reader(file) if row) - 1, 0)


def find_fingerprint_pairs(path_a: Path, path_b: Path, decimals: int = 6) -> dict:
    """จับคู่แถวของไฟล์ A กับไฟล์ B ที่ลายนิ้วมือเหมือนกันแต่ key (origin, destination) ต่างกัน

    pool ที่ใช้จับคู่:
      A-pool = แถว removed (มีแค่ใน A) + แถวที่ key มีทั้งสองไฟล์แต่ตัวเลขเปลี่ยน (ค่าฝั่ง A)
      B-pool = แถว added (มีแค่ใน B)   + แถวที่ key มีทั้งสองไฟล์แต่ตัวเลขเปลี่ยน (ค่าฝั่ง B)
    ส่วนที่เพิ่มจาก removed/added ใช้จับเคส "รหัสถูกนำกลับมาใช้ซ้ำ" (via_common_key = True)
    """
    header_a, rows_a = read_csv_dicts(path_a)
    header_b, rows_b = read_csv_dicts(path_b)
    columns = fingerprint_columns(header_a, header_b)
    fp_a = fingerprints_for_file(rows_a, header_a, columns, decimals)
    fp_b = fingerprints_for_file(rows_b, header_b, columns, decimals)

    keys_a, keys_b = set(rows_a), set(rows_b)
    removed = keys_a - keys_b
    added = keys_b - keys_a
    common = keys_a & keys_b
    changed_common = {k for k in common if fp_a[k] != fp_b[k]}

    pool_a = removed | changed_common
    pool_b = added | changed_common

    by_fingerprint: dict = defaultdict(list)
    for key in pool_b:
        by_fingerprint[fp_b[key]].append(key)

    raw_pairs = []
    for old_key in sorted(pool_a):
        for new_key in sorted(by_fingerprint.get(fp_a[old_key], [])):
            if new_key != old_key:
                raw_pairs.append((old_key, new_key))

    partners_of_old = Counter(old for old, _ in raw_pairs)
    partners_of_new = Counter(new for _, new in raw_pairs)

    comp_a = header_a.index("companies") if "companies" in header_a else None
    comp_b = header_b.index("companies") if "companies" in header_b else None

    pairs = []
    for old_key, new_key in raw_pairs:
        row_a, row_b = rows_a[old_key], rows_b[new_key]
        (o1, d1), (o2, d2) = old_key, new_key
        if o1 != o2 and d1 != d2:
            side = "both"
        elif o1 != o2:
            side = "origin"
        else:
            side = "destination"
        one_to_one = partners_of_old[old_key] == 1 and partners_of_new[new_key] == 1
        if comp_a is None or comp_b is None:
            companies_match = None
        else:
            companies_match = _cell(row_a, comp_a) == _cell(row_b, comp_b)
        pairs.append({
            "old_key": old_key,
            "new_key": new_key,
            "changed_side": side,
            "match_type": "1:1" if one_to_one else "ambiguous",
            "partners_for_old": partners_of_old[old_key],
            "partners_for_new": partners_of_new[new_key],
            "companies_match": companies_match,
            "via_common_key": (old_key in keys_b) or (new_key in keys_a),
            "old_namea": _cell(row_a, NAMEA_COL), "old_nameb": _cell(row_a, NAMEB_COL),
            "new_namea": _cell(row_b, NAMEA_COL), "new_nameb": _cell(row_b, NAMEB_COL),
        })

    matched_old, matched_new = set(partners_of_old), set(partners_of_new)

    def unmatched(keys, rows):
        return [{"key": k, "namea": _cell(rows[k], NAMEA_COL), "nameb": _cell(rows[k], NAMEB_COL)}
                for k in sorted(keys)]

    ports_a = {k[0] for k in keys_a} | {k[1] for k in keys_a}
    ports_b = {k[0] for k in keys_b} | {k[1] for k in keys_b}

    stats = {
        "routes_a": len(rows_a), "routes_b": len(rows_b),
        "common": len(common), "common_numeric_changed": len(changed_common),
        "removed": len(removed), "added": len(added),
        "pairs_total": len(pairs),
        "pairs_1to1": sum(p["match_type"] == "1:1" for p in pairs),
        "pairs_ambiguous": sum(p["match_type"] != "1:1" for p in pairs),
        "pairs_via_common_key": sum(p["via_common_key"] for p in pairs),
        "unmatched_removed": len(removed - matched_old),
        "unmatched_added": len(added - matched_new),
        "columns_used": len(columns),
        "ports_only_a": len(ports_a - ports_b), "ports_only_b": len(ports_b - ports_a),
    }
    return {
        "columns_used": columns,
        "pairs": pairs,
        "unmatched_removed": unmatched(removed - matched_old, rows_a),
        "unmatched_added": unmatched(added - matched_new, rows_b),
        "ports_only_a": sorted(ports_a - ports_b),
        "ports_only_b": sorted(ports_b - ports_a),
        "stats": stats,
    }


def summarize_port_mapping(pair_records: list[dict]) -> list[dict]:
    """รวมคู่ระดับเส้นทาง -> ตารางระดับท่าเรือ (รหัสเก่า -> รหัสใหม่) พร้อมจำนวนเส้นทางที่สนับสนุน

    pair_records: dict ของแต่ละคู่จาก find_fingerprint_pairs + quarter/folder_a/folder_b
    หมายเหตุ: เส้นทางเดียวกันในไตรมาสเดียวกันที่ซ้ำข้ามคู่โฟลเดอร์ นับเป็น 1 เส้นทาง
    """
    table: dict = {}
    for p in pair_records:
        route_id = (p["quarter"], p["old_key"], p["new_key"])
        mappings = []
        if p["changed_side"] in ("origin", "both"):
            mappings.append((p["old_key"][0], p["new_key"][0], p["old_namea"], p["new_namea"]))
        if p["changed_side"] in ("destination", "both"):
            mappings.append((p["old_key"][1], p["new_key"][1], p["old_nameb"], p["new_nameb"]))
        for old_code, new_code, old_name, new_name in mappings:
            entry = table.setdefault((old_code, new_code), {
                "old_names": set(), "new_names": set(), "quarters": set(),
                "routes_total": set(), "routes_1to1": set(), "companies_mismatch": set(),
            })
            entry["old_names"].add(old_name)
            entry["new_names"].add(new_name)
            entry["quarters"].add(p["quarter"])
            entry["routes_total"].add(route_id)
            if p["match_type"] == "1:1":
                entry["routes_1to1"].add(route_id)
            if p["companies_match"] is False:
                entry["companies_mismatch"].add(route_id)

    # chain / competing นับเฉพาะรายการที่มีหลักฐานแบบ 1:1 อย่างน้อย 1 เส้นทาง
    # (ไม่งั้นคู่บังเอิญที่ลายนิ้วมือซ้ำกันจะทำให้ท่าที่ถูกต้องโดนติดธงเกินจริง)
    strong = [key for key, e in table.items() if e["routes_1to1"]]
    old_codes = {old for old, _ in strong}
    new_codes = {new for _, new in strong}
    new_per_old = Counter(old for old, _ in strong)

    rows = []
    for (old_code, new_code), e in table.items():
        chain = (old_code in new_codes) or (new_code in old_codes)
        competing = new_per_old[old_code]
        if len(e["routes_1to1"]) >= MIN_SUPPORT_OK and competing == 1 and not chain:
            review = "ok"
        else:
            reasons = []
            if len(e["routes_1to1"]) < MIN_SUPPORT_OK:
                reasons.append("support น้อย")
            if competing > 1:
                reasons.append("รหัสเก่าชี้ไปหลายรหัสใหม่")
            if chain:
                reasons.append("chain/รหัสถูกใช้ซ้ำ")
            review = "check: " + ", ".join(reasons)
        rows.append({
            "old_code": old_code, "new_code": new_code,
            "old_names": " | ".join(sorted(n for n in e["old_names"] if n)),
            "new_names": " | ".join(sorted(n for n in e["new_names"] if n)),
            "routes_1to1": len(e["routes_1to1"]),
            "routes_total": len(e["routes_total"]),
            "quarters": len(e["quarters"]),
            "companies_mismatch_routes": len(e["companies_mismatch"]),
            "competing_new_codes": competing,
            "chain_or_reuse": chain,
            "review": review,
        })
    rows.sort(key=lambda r: (-r["routes_1to1"], r["old_code"], r["new_code"]))
    return rows


def write_xlsx_sheets(output_file: Path, sheets: dict[str, list[list]]) -> None:
    """เขียน .xlsx หลายชีตด้วย stdlib ล้วน (ไม่ต้องติดตั้ง openpyxl)

    sheets: {ชื่อชีต: [[หัวตาราง...], [แถว...], ...]}  แถวแรกของแต่ละชีต = หัวตาราง
    ใส่ freeze แถวแรก + ตัวกรอง (filter) ให้อัตโนมัติ ตัวเลข/True-False เก็บเป็นชนิดจริง
    """
    names = [re.sub(r"[\[\]:*?/\\]", "_", n)[:31] for n in sheets]
    all_rows = list(sheets.values())

    def clean(text) -> str:
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text))

    def cell_xml(row_number: int, column_number: int, value) -> str:
        ref = f"{excel_column_letter(column_number)}{row_number}"
        if isinstance(value, bool):
            return f'<c r="{ref}" t="b"><v>{int(value)}</v></c>'
        if isinstance(value, (int, float)) and not (isinstance(value, float) and not math.isfinite(value)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        if value is None:
            value = ""
        return (f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
                f"{escape(clean(value))}</t></is></c>")

    def sheet_xml(rows: list[list]) -> str:
        ncols = max((len(r) for r in rows), default=1) or 1
        last_ref = f"{excel_column_letter(ncols)}{max(len(rows), 1)}"
        body = "".join(
            f'<row r="{i}">' + "".join(cell_xml(i, j, v) for j, v in enumerate(row, start=1)) + "</row>"
            for i, row in enumerate(rows, start=1)
        )
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheetViews><sheetView workbookViewId="0">'
                '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                '</sheetView></sheetViews>'
                f'<cols><col min="1" max="{ncols}" width="18" customWidth="1"/></cols>'
                f"<sheetData>{body}</sheetData>"
                f'<autoFilter ref="A1:{last_ref}"/></worksheet>')

    sheet_entries = "".join(
        f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>'
        for i, name in enumerate(names, start=1))
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_entries}</sheets></workbook>")
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(names) + 1))
        + "</Relationships>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(names) + 1))
        + "</Types>")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>')

    with ZipFile(output_file, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types)
        workbook.writestr("_rels/.rels", root_rels)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for i, rows in enumerate(all_rows, start=1):
            workbook.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(rows))


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python keyed_diff.py <file_a.csv> <file_b.csv>")
        raise SystemExit(1)
    print_keyed_diff(Path(sys.argv[1]), Path(sys.argv[2]))