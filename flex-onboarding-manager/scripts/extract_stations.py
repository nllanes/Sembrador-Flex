import json
import re
from pathlib import Path

src = Path(r"D:\Work\Project_To_Bot\monitor_saas\dashboard\index.html")
text = src.read_text(encoding="utf-8")
block = re.search(r"var FLEX_STATIONS=\[(.*?)\];", text, re.S).group(1)
items = []
for line in block.split("\n"):
    line = line.strip().rstrip(",")
    if not line or line.startswith("/*"):
        continue
    m = re.search(
        r'\{code:"([^"]+)",name:"([^"]+)",city:"([^"]+)",lat:([\d.-]+),lng:([\d.-]+)\}',
        line,
    )
    if m:
        items.append(
            {
                "code": m.group(1),
                "name": m.group(2),
                "city": m.group(3),
                "lat": float(m.group(4)),
                "lng": float(m.group(5)),
            }
        )
out = Path(__file__).resolve().parent.parent / "app" / "data" / "flex_stations.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(items, indent=2), encoding="utf-8")
print(f"Wrote {len(items)} stations to {out}")
