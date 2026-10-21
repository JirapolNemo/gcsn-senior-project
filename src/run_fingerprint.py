"""รันวิธี "ลายนิ้วมือ" กับทุกไตรมาสที่มีไฟล์ชื่อซ้ำกันหลายโฟลเดอร์

วิธีรัน (ต้องรันจากโฟลเดอร์หลักของ repo ไม่ใช่จากใน src/):
    python3 src/run_fingerprint.py

ผลลัพธ์:
    data/qa/fingerprint_report.xlsx        รายงาน Excel หลายชีต (ดูรายละเอียดด้านล่าง)
    data/qa/fingerprint_port_mapping.csv   ตารางระดับท่าเรือ (รหัสเก่า -> รหัสใหม่) สำหรับเติม master_ports

ชีตใน fingerprint_report.xlsx:
    PortMapping  - ตารางระดับท่าเรือ + จำนวนเส้นทางที่สนับสนุน + คอลัมน์ review
    RoutePairs   - คู่ระดับเส้นทางทุกคู่ที่ลายนิ้วมือตรงกัน
    Unmatched    - แถว removed/added ที่ไม่มีคู่ (ผู้ต้องสงสัยเรื่อง merge หรือเส้นทางเลิก/เปิดจริง)
    PairSummary  - ตัวเลขตรวจสอบต่อคู่ไฟล์ (แถวดิบ, key, removed, added, จับคู่ได้เท่าไร ฯลฯ)
    VsOldMethod  - คู่ที่วิธีลายนิ้วมือกับวิธีเดิม (find_rename_candidates) เห็นไม่ตรงกัน

หมายเหตุ: "old/new" ในที่นี้ = ไฟล์ A / ไฟล์ B ตามลำดับโฟลเดอร์ใน SOURCE_DIRS
(ข้อสันนิษฐาน: โฟลเดอร์ที่อยู่ก่อนคือชุดที่โหลดมาก่อน)
"""

import csv
from pathlib import Path

from diff_tools import (
    count_data_rows,
    find_fingerprint_pairs,
    find_rename_candidates,
    summarize_port_mapping,
    write_xlsx_sheets,
)
from run_diff import find_overlaps

OUT_XLSX = Path("data/qa/fingerprint_report.xlsx")
OUT_PORTS_CSV = Path("data/qa/fingerprint_port_mapping.csv")

# วิธีเดิมถือว่า "ตรงเต็ม" เมื่อคอลัมน์ที่ไม่ตรงมีแต่กลุ่มนี้ (รหัส/ชื่อ/บริษัท) ไม่มีตัวเลขต่าง
NON_NUMERIC_COLS = {"origin", "namea", "destination", "nameb", "companies"}


def old_method_pairs(path_a: Path, path_b: Path) -> set:
    """คู่ (old_key, new_key) ที่วิธีเดิมให้คะแนนเต็ม (ไม่นับความต่างของ companies/ชื่อ/รหัส)"""
    pairs = set()
    for c in find_rename_candidates(path_a, path_b)["candidates"]:
        mismatched = {m.strip() for m in c["mismatch_columns"].split(",") if m.strip()}
        if mismatched <= NON_NUMERIC_COLS:
            pairs.add((c["old_key"], c["new_key"]))
    return pairs


def main() -> None:
    overlaps = find_overlaps()
    print(f"พบ {len(overlaps)} ไตรมาสที่ซ้ำกันมากกว่า 1 โฟลเดอร์")

    pair_records = []   # คู่ระดับเส้นทาง (พร้อม quarter/folder)
    unmatched_rows = []
    summary_rows = []
    compare_rows = []

    for filename, locations in sorted(overlaps.items()):
        labels = list(locations.keys())
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                a, b = labels[i], labels[j]
                path_a, path_b = locations[a], locations[b]
                result = find_fingerprint_pairs(path_a, path_b)
                stats = result["stats"]
                base = {"quarter": filename, "folder_a": a, "folder_b": b}

                for p in result["pairs"]:
                    pair_records.append({**base, **p})

                for kind, items in (("removed", result["unmatched_removed"]),
                                    ("added", result["unmatched_added"])):
                    for item in items:
                        unmatched_rows.append([
                            filename, a, b, kind, item["key"][0], item["key"][1],
                            item["namea"], item["nameb"],
                        ])

                raw_a, raw_b = count_data_rows(path_a), count_data_rows(path_b)
                summary_rows.append([
                    filename, a, b,
                    raw_a, raw_b, stats["routes_a"], stats["routes_b"],
                    raw_a - stats["routes_a"], raw_b - stats["routes_b"],
                    stats["common"], stats["common_numeric_changed"],
                    stats["removed"], stats["added"],
                    stats["pairs_total"], stats["pairs_1to1"], stats["pairs_ambiguous"],
                    stats["pairs_via_common_key"],
                    stats["unmatched_removed"], stats["unmatched_added"],
                    stats["columns_used"],
                    stats["ports_only_a"], stats["ports_only_b"],
                    ", ".join(result["ports_only_a"]), ", ".join(result["ports_only_b"]),
                ])

                # เทียบกับวิธีเดิม (เฉพาะคู่ที่ไม่ผ่าน key ที่มีทั้งสองไฟล์ เพื่อเทียบ pool เดียวกัน)
                new_set = {(p["old_key"], p["new_key"]) for p in result["pairs"]
                           if not p["via_common_key"]}
                old_set = old_method_pairs(path_a, path_b)
                match_type_of = {(p["old_key"], p["new_key"]): p["match_type"]
                                 for p in result["pairs"]}
                for old_key, new_key in sorted(new_set - old_set):
                    compare_rows.append([filename, a, b, "เจอเฉพาะลายนิ้วมือ",
                                         old_key[0], old_key[1], new_key[0], new_key[1],
                                         match_type_of[(old_key, new_key)]])
                for old_key, new_key in sorted(old_set - new_set):
                    compare_rows.append([filename, a, b, "เจอเฉพาะวิธีเดิม",
                                         old_key[0], old_key[1], new_key[0], new_key[1], ""])

    port_rows = summarize_port_mapping(pair_records)

    port_header = ["old_code", "new_code", "old_names", "new_names", "routes_1to1",
                   "routes_total", "quarters", "companies_mismatch_routes",
                   "competing_new_codes", "chain_or_reuse", "review"]
    pair_header = ["quarter", "folder_a", "folder_b", "old_origin", "old_destination",
                   "new_origin", "new_destination", "changed_side", "match_type",
                   "partners_for_old", "partners_for_new", "companies_match",
                   "via_common_key", "old_namea", "new_namea", "old_nameb", "new_nameb"]
    unmatched_header = ["quarter", "folder_a", "folder_b", "kind", "origin", "destination",
                        "namea", "nameb"]
    summary_header = ["quarter", "folder_a", "folder_b", "raw_rows_a", "raw_rows_b",
                      "routes_a", "routes_b", "rows_lost_a", "rows_lost_b",
                      "common", "common_numeric_changed", "removed", "added",
                      "pairs_total", "pairs_1to1", "pairs_ambiguous", "pairs_via_common_key",
                      "unmatched_removed", "unmatched_added", "columns_used",
                      "ports_only_a", "ports_only_b", "ports_only_a_list", "ports_only_b_list"]
    compare_header = ["quarter", "folder_a", "folder_b", "found_by",
                      "old_origin", "old_destination", "new_origin", "new_destination",
                      "match_type"]

    pair_sheet_rows = [[
        r["quarter"], r["folder_a"], r["folder_b"],
        r["old_key"][0], r["old_key"][1], r["new_key"][0], r["new_key"][1],
        r["changed_side"], r["match_type"], r["partners_for_old"], r["partners_for_new"],
        "" if r["companies_match"] is None else r["companies_match"],
        r["via_common_key"],
        r["old_namea"], r["new_namea"], r["old_nameb"], r["new_nameb"],
    ] for r in pair_records]

    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx_sheets(OUT_XLSX, {
        "PortMapping": [port_header] + [[r[h] for h in port_header] for r in port_rows],
        "RoutePairs": [pair_header] + pair_sheet_rows,
        "Unmatched": [unmatched_header] + unmatched_rows,
        "PairSummary": [summary_header] + summary_rows,
        "VsOldMethod": [compare_header] + compare_rows,
    })

    with OUT_PORTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=port_header)
        writer.writeheader()
        writer.writerows(port_rows)

    # ---- สรุปบนหน้าจอ ----
    total_removed = sum(r[11] for r in summary_rows)
    total_added = sum(r[12] for r in summary_rows)
    print(f"\nสร้างรายงาน {OUT_XLSX} และ {OUT_PORTS_CSV} แล้ว")
    print(f"คู่ไฟล์ที่เทียบ: {len(summary_rows)}")
    print(f"แถวดิบที่หายตอนทำ key (ซ้ำ/สั้นเกิน) รวม: "
          f"{sum(r[7] + r[8] for r in summary_rows)}  (ควรเป็น 0)")
    print(f"Removed รวม {total_removed} / Added รวม {total_added}")
    print(f"คู่ที่จับได้: {len(pair_records)}  "
          f"(1:1 = {sum(r['match_type'] == '1:1' for r in pair_records)}, "
          f"กำกวม = {sum(r['match_type'] != '1:1' for r in pair_records)}, "
          f"ผ่าน key ที่มีทั้งสองไฟล์/รหัสถูกใช้ซ้ำ = {sum(r['via_common_key'] for r in pair_records)})")
    print(f"removed ที่ไม่มีคู่: {sum(1 for r in unmatched_rows if r[3] == 'removed')}, "
          f"added ที่ไม่มีคู่: {sum(1 for r in unmatched_rows if r[3] == 'added')}")
    print(f"ตารางระดับท่าเรือ: {len(port_rows)} รายการ "
          f"(review = ok: {sum(r['review'] == 'ok' for r in port_rows)}, "
          f"ต้องตรวจ: {sum(r['review'] != 'ok' for r in port_rows)})")
    print(f"เทียบกับวิธีเดิม: เห็นไม่ตรงกัน {len(compare_rows)} คู่ "
          f"(ดูชีต VsOldMethod)")


if __name__ == "__main__":
    main()
