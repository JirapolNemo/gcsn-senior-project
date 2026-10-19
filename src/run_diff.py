import csv as csv_module
from pathlib import Path
from diff_tools import compare_keyed, export_keyed_diff_excel, print_keyed_diff, find_rename_candidates

SOURCE_DIRS = {
    "2011-2017": Path("data/sources/Dataset (2011-2017)"),
    "2015-2023": Path("data/sources/Dataset (2015-2023)"),
    "2017-2026": Path("data/sources/Dataset (2017-2026)"),
}


def find_overlaps():
    files_by_name = {}
    for label, folder in SOURCE_DIRS.items():
        if not folder.exists():
            continue
        for csv_file in folder.glob("*.csv"):
            files_by_name.setdefault(csv_file.name, {})[label] = csv_file
    return {name: locs for name, locs in files_by_name.items() if len(locs) > 1}


def main():
    overlaps = find_overlaps()
    print(f"พบ {len(overlaps)} ไตรมาสที่ซ้ำกันมากกว่า 1 โฟลเดอร์\n")

    file_pairs = []
    change_rows = []

    # สถิติรวมทั้งหมด สำหรับเช็คว่า removed+added ไปอยู่ที่ไหนบ้าง
    total_removed = 0
    total_added = 0
    total_matched_removed = 0
    total_matched_added = 0
    total_unmatched_removed = 0
    total_unmatched_added = 0

    for filename, locations in sorted(overlaps.items()):
        labels = list(locations.keys())
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                a, b = labels[i], labels[j]
                path_a, path_b = locations[a], locations[b]
                file_pairs.append((f"{filename} ({a} vs {b})", path_a, path_b))
                print_keyed_diff(path_a, path_b)

                rename_result = find_rename_candidates(path_a, path_b)
                for c in rename_result["candidates"]:
                    change_rows.append({
                        "quarter": filename, "folder_a": a, "folder_b": b,
                        "change_type": "code_rename",
                        "old_origin": c["old_key"][0], "old_destination": c["old_key"][1],
                        "new_origin": c["new_key"][0], "new_destination": c["new_key"][1],
                        "changed_side": c["changed_side"],
                        "match_score": c["match_score"],
                        "match_ratio": c["match_ratio"],
                        "mismatch_columns": c["mismatch_columns"],
                        "code": "", "old_name": "", "new_name": "",
                    })

                result = compare_keyed(path_a, path_b)
                for (origin, dest), diffs in result["modified"].items():
                    for col_name, val_a, val_b in diffs:
                        if col_name in ("namea", "nameb"):
                            change_rows.append({
                                "quarter": filename, "folder_a": a, "folder_b": b,
                                "change_type": "name_change",
                                "old_origin": "", "old_destination": "",
                                "new_origin": "", "new_destination": "",
                                "changed_side": "", "match_score": "", "match_ratio": "",
                                "mismatch_columns": "",
                                "code": origin if col_name == "namea" else dest,
                                "old_name": val_a, "new_name": val_b,
                            })

                # --- สะสมสถิติ ---
                n_removed = len(result["removed"])
                n_added = len(result["added"])
                n_unmatched_removed = len(rename_result["unmatched_removed"])
                n_unmatched_added = len(rename_result["unmatched_added"])

                total_removed += n_removed
                total_added += n_added
                total_unmatched_removed += n_unmatched_removed
                total_unmatched_added += n_unmatched_added
                total_matched_removed += (n_removed - n_unmatched_removed)
                total_matched_added += (n_added - n_unmatched_added)

    if file_pairs:
        export_keyed_diff_excel(file_pairs, Path("data/qa/keyed_diff_report.xlsx"))
        print(f"\nสร้างรายงานที่ data/qa/keyed_diff_report.xlsx แล้ว")

    if change_rows:
        out_path = Path("data/qa/port_changes.csv")
        fieldnames = ["quarter", "folder_a", "folder_b", "change_type",
                      "old_origin", "old_destination", "new_origin", "new_destination",
                      "changed_side", "match_score", "match_ratio", "mismatch_columns",
                      "code", "old_name", "new_name"]
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv_module.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(change_rows)
        print(f"พบการเปลี่ยนแปลงทั้งหมด {len(change_rows)} รายการ -> {out_path}")
    else:
        print("ไม่พบการเปลี่ยนแปลงเลย")

    # --- สรุปสถิติ removed/added ว่าไปอยู่ไหนบ้าง ---
    print("\n=== สรุปที่มาของ removed/added rows ===")
    print(f"Removed รวม: {total_removed}  -> จับคู่ได้ (มี candidate อย่างน้อย 1): {total_matched_removed}  "
          f"| ไม่เจอคู่เลย: {total_unmatched_removed}")
    print(f"Added   รวม: {total_added}  -> จับคู่ได้ (มี candidate อย่างน้อย 1): {total_matched_added}  "
          f"| ไม่เจอคู่เลย: {total_unmatched_added}")
    print(f"Removed+Added รวมทั้งหมด: {total_removed + total_added}")
    print(f"จำนวน code_rename candidates ที่ดึงออกมา (ไม่ตัด threshold): "
          f"{sum(1 for r in change_rows if r['change_type'] == 'code_rename')}")


if __name__ == "__main__":
    main()