# CPCI pipeline

คำนวณ CPCI (inbound/outbound + decomposition C1–C5) และ centrality อื่นๆ ให้ทุก quarter ของ 2011–2026
จากไฟล์ใน `data/sources/` โดยไม่มี path เฉพาะเครื่อง (ทุกอย่างอิง root ของ repo)

## วางไฟล์ยังไง

คัดลอกเนื้อใน zip ไปวางที่ root ของ repo (โครงเดียวกับที่มีอยู่):

```
src/cpci/            ← แพ็กเกจหลัก (ใหม่ทั้งโฟลเดอร์)
src/run_cpci.py      ← สั่งรัน
src/validate_cpci.py ← ตรวจกับของรุ่นพี่
tests/test_cpci.py
docs/CPCI_PIPELINE.md
requirements.txt
```

ไม่ไปยุ่งกับ `src/diff_tools.py`, `src/run_diff.py`, `src/run_fingerprint.py` ที่มีอยู่

## รัน (เปิด Terminal ที่ root ของ repo)

```bash
python3 -m pip install -r requirements.txt
python3 tests/test_cpci.py                    # ต้องขึ้น "8 tests passed"
python3 src/run_cpci.py --metrics cpci,degree,closeness   # เร็ว (วินาที)
python3 src/run_cpci.py --jobs 4              # ทุก metric ทุก quarter (~1.5 นาทีกับ 4 core)
python3 src/run_cpci.py --list-metrics
```

ตัวเลือกอื่น: `--first 20110925 --last 20170924`, `--save-links` (เขียนตาราง LSCI ต่อ link)

## ข้อมูลที่ใช้ (กำหนดใน `src/cpci/config.py` → `DEFAULT_SOURCE_RULES`)

| ช่วง | โฟลเดอร์ใน data/sources |
|---|---|
| 20110925 – 20170924 | `2011-2017` |
| 20171231 – ต่อไป | `2017-2026` |

`2015-2023` ไม่ใช้ (ซ้ำกับสองชุดแรก) 1 ไตรมาส = 1 ไฟล์ ถ้ากฎซ้อนกันโค้ดจะ error เอง
ชื่อโฟลเดอร์/ช่วงวันที่แก้ได้ที่ไฟล์เดียว

## Output (`data/processed/cpci/` ← อยู่ใน .gitignore)

- `scores.csv` แถวละ (quarter, port): `port_id, name, country, region`, คะแนนทุก metric, และ `rank_<ชื่อคอลัมน์>` (1 = สูงสุด, เสมอใช้ rank ต่ำสุด)
- `quarter_summary.csv` แถวละ quarter: โฟลเดอร์ต้นทาง, จำนวนท่า/link, `lambda1` (ค่า singular หลัก, ขนาดสัมบูรณ์ของเครือข่าย), `decomp_residual` (C1..C5 รวมกลับเป็น score ได้ ควร ~1e-15), `zero_inbound/outbound`, `mono_*` (monotonicity ของ rank)
- `run_info.json` metric/ช่วงข้อมูลที่ใช้ในรอบนั้น

คอลัมน์ที่เปลี่ยนชื่อจากของรุ่นพี่: `In Degree → InDegree`, `Out Degree → OutDegree`

## master_ports

ถ้ามี `data/reference/master_ports.csv` ที่มีคอลัมน์ `port_id` + (`old_code` และ/หรือ `new_code`) โค้ดจะใส่ `port_id` ให้ทุกแถว
ท่าที่ไม่อยู่ในไฟล์จะใช้ code เป็น `port_id` เอง ถ้าไม่มีไฟล์ = ใช้ code ตรงๆ (ไม่ error)
CPCI ต่อ quarter ไม่ต้องใช้ mapping ส่วนนี้ มีไว้ตอนเทียบข้าม quarter

## เพิ่ม metric ใหม่

สร้างไฟล์ใน `src/cpci/metrics/` เช่น `my_metric.py` (ตัวอย่างอยู่ใน docstring ของ `src/cpci/metrics/__init__.py`):

```python
from . import metric

@metric("pagerank", columns=["PageRank"], group="centrality", description="PageRank บนกราฟ LSCI")
def pagerank(net):                       # net = QuarterNetwork
    import networkx as nx
    pr = nx.pagerank(net.graph, weight=None)
    return {"PageRank": [pr[p] for p in net.ports]}
```

ไม่ต้องแก้ไฟล์อื่น: `run_cpci.py` เจอเองและใส่ rank ให้ ใน `net` มี `L` (LSCI matrix), `A` (A1..A5), `adjacency`, `graph` (networkx, edge attribute `time`), `hits`, `links` (ตาราง link)

## Validate กับของรุ่นพี่

```bash
python3 src/validate_cpci.py legacy                       # เทียบกับ logic ใน 0.CPCI.ipynb (ไม่ต้องใช้ไฟล์เพิ่ม)
python3 src/validate_cpci.py senior --senior-dir <โฟลเดอร์ Results ของรุ่นพี่>
```

`senior` อ่าน `2.Inbound/{q}_inbound.xlsx`, `3.Outbound/...`, `6.Centrality/...` (โครงเดียวกับที่ notebook เขียนออกมา) แล้วรายงาน
ความต่างสูงสุด, Kendall tau, สัดส่วน rank ตรงกัน, top-20 overlap ต่อคอลัมน์ ผลเขียนที่ `data/qa/cpci_validation_*.csv`

## จุดที่ต่างจาก notebook รุ่นพี่ (ตั้งใจ)

1. หา principal vector ด้วย SVD ของ L (ได้ inbound/outbound/λ เป็นคู่เดียวกัน) แทนการเรียก `np.linalg.eig` สองครั้งแล้ว "เอาคอลัมน์ 0" ซึ่งไม่การันตีว่าเป็นค่าที่ใหญ่สุด
2. เวลาของ edge ใน betweenness-time จับคู่ด้วย (origin, destination) ไม่ใช้ตำแหน่งแถว
3. rank คำนวณหลังปัดคะแนนเป็นทศนิยม 12 ตำแหน่ง กัน noise ของ float ทำให้ rank ของท่าที่คะแนนเท่ากันจริงๆ (เช่น 0) ต่างกันตามเครื่อง
4. ตรวจ schema ตอนอ่านไฟล์ (รองรับ BOM, `20110925.csv` ที่มีแค่ 12 คอลัมน์, `period` ที่เป็น string)
