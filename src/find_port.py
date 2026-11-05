"""ค้นว่ารหัสท่าเรือ (UN/LOCODE) ที่ระบุ ปรากฏในไฟล์ไหนบ้างใน data/sources

วิธีรัน (จากโฟลเดอร์หลักของ repo หรือที่ไหนก็ได้):
    python3 src/find_port.py PTFNC USFRP
    python3 src/find_port.py PTFNC USFRP --root /path/to/repo      # ระบุโฟลเดอร์ repo เอง
    python3 src/find_port.py PTFNC --folder raw                    # ค้นใน data/raw แทน data/sources

ผลลัพธ์:
    - สรุปบนหน้าจอ: ท่านี้อยู่กี่ไฟล์ ไตรมาสแรก/ล่าสุด และเจอในโฟลเดอร์ไหนบ้าง
    - ไฟล์ data/qa/port_search.csv : แถวละ 1 (ไฟล์ x เส้นทาง) ที่มีท่านี้ (เปิดดูรายละเอียดได้)

หมายเหตุ: ค้นตามชื่อคอลัมน์ origin / destination (ไม่ใช้ตำแหน่ง) จึงใช้ได้กับไฟล์ที่คอลัมน์ไม่ครบ
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def default_root() -> Path:
    # <root>/src/find_port.py -> root = พ่อของโฟลเดอร์ src
    return Path(__file__).resolve().parents[1]


def find_csv_files(base: Path):
    """ไฟล์ .csv ทุกไฟล์ใต้ base (รวมโฟลเดอร์ย่อย) เรียงตามชื่อโฟลเดอร์/ชื่อไฟล์"""
    return sorted(p for p in base.rglob("*.csv") if not p.name.startswith("."))


def search_file(path: Path, codes: set):
    """คืนรายการแถวที่ origin หรือ destination ตรงกับ code ใน codes"""
    hits = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return hits
        names = [h.strip().lower() for h in header]
        if "origin" not in names or "destination" not in names:
            return hits  # ไม่ใช่ไฟล์เส้นทาง (เช่น ports.csv) ข้ามไป
        io, idn = names.index("origin"), names.index("destination")
        ina = names.index("namea") if "namea" in names else None
        inb = names.index("nameb") if "nameb" in names else None
        for line_no, row in enumerate(reader, start=2):  # บรรทัด 1 = header
            if len(row) <= max(io, idn):
                continue
            o, d = row[io].strip(), row[idn].strip()
            for code in codes:
                if code in (o, d):
                    role = "origin" if code == o else "destination"
                    name = ""
                    if role == "origin" and ina is not None and ina < len(row):
                        name = row[ina].strip()
                    if role == "destination" and inb is not None and inb < len(row):
                        name = row[inb].strip()
                    hits.append({
                        "code": code, "role": role, "name": name,
                        "origin": o, "destination": d, "line": line_no,
                    })
    return hits


def main():
    parser = argparse.ArgumentParser(description="ค้นรหัสท่าเรือในไฟล์ข้อมูลดิบ")
    parser.add_argument("codes", nargs="+", help="รหัสท่าเรือ เช่น PTFNC USFRP")
    parser.add_argument("--root", type=Path, default=None, help="โฟลเดอร์หลักของ repo")
    parser.add_argument("--folder", default="sources",
                        help="โฟลเดอร์ใต้ data/ ที่จะค้น (ค่าเริ่มต้น sources)")
    args = parser.parse_args()

    root = (args.root or default_root()).resolve()
    base = root / "data" / args.folder
    codes = {c.strip().upper() for c in args.codes}
    if not base.exists():
        raise SystemExit(f"ไม่พบโฟลเดอร์ {base}")

    files = find_csv_files(base)
    all_folders = sorted({str(p.parent.relative_to(base)) for p in files})
    print(f"ค้น {sorted(codes)} ใน {len(files)} ไฟล์ ใต้ {base}")
    for folder in all_folders:
        n = sum(1 for p in files if str(p.parent.relative_to(base)) == folder)
        print(f"  - {folder}: {n} ไฟล์")
    print()

    out_rows = []
    per_code = {c: defaultdict(list) for c in codes}   # code -> {(folder, file): hits}
    for path in files:
        hits = search_file(path, codes)
        rel_folder = str(path.parent.relative_to(base))
        for h in hits:
            per_code[h["code"]][(rel_folder, path.name)].append(h)
            out_rows.append({"code": h["code"], "folder": rel_folder, "file": path.name,
                             "role": h["role"], "name": h["name"],
                             "origin": h["origin"], "destination": h["destination"],
                             "line": h["line"]})

    for code in sorted(codes):
        found = per_code[code]
        print("=" * 60)
        if not found:
            print(f"{code}: ไม่พบในไฟล์ใดเลย")
            continue
        keys = sorted(found, key=lambda k: (k[1], k[0]))
        quarters = sorted({k[1] for k in keys})
        names = sorted({h["name"] for hs in found.values() for h in hs if h["name"]})
        print(f"{code}: พบ {len(keys)} ไฟล์ ({len(quarters)} ไตรมาส)  "
              f"แรกสุด {quarters[0]}  ล่าสุด {quarters[-1]}")
        print(f"  ชื่อที่พบ: {', '.join(names) if names else '-'}")
        by_folder = defaultdict(list)
        for folder, fname in keys:
            by_folder[folder].append(fname)
        # แสดงทุกโฟลเดอร์ที่ค้น (รวมโฟลเดอร์ที่ไม่พบ) จะได้เห็นครบทั้ง 3 dataset
        for folder in all_folders:
            fnames = by_folder.get(folder, [])
            if fnames:
                print(f"  โฟลเดอร์ {folder}: พบ {len(fnames)} ไฟล์ -> {', '.join(fnames)}")
            else:
                print(f"  โฟลเดอร์ {folder}: ไม่พบ")
        print("  จำนวนเส้นทางต่อไฟล์ (เป็นต้นทาง/ปลายทาง):")
        for folder, fname in keys:
            hs = found[(folder, fname)]
            n_o = sum(h["role"] == "origin" for h in hs)
            n_d = sum(h["role"] == "destination" for h in hs)
            partners = sorted({h["destination"] if h["role"] == "origin" else h["origin"]
                               for h in hs})
            print(f"    {fname} [{folder}]  origin={n_o} destination={n_d}  "
                  f"คู่เส้นทาง: {', '.join(partners)}")

    out_path = root / "data" / "qa" / "port_search.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["code", "folder", "file", "role", "name",
                                               "origin", "destination", "line"])
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"\nเขียนรายละเอียดทุกแถวที่พบ {len(out_rows)} แถว -> {out_path}")


if __name__ == "__main__":
    main()
