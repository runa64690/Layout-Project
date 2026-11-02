"""Export the API's bed-head regions for checking the real Web model orientation."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from api_v2 import LayoutV2, catalog_v2, evaluate_v2


def contract():
    room = {"vertices": [{"id": f"v{i}", "x": x, "y": y}
                         for i, (x, y) in enumerate([(0, 0), (6, 0), (6, 6), (0, 6)])],
            "doors": [], "windows": [], "ceiling_height_m": 2.5}
    definition = next(d for d in catalog_v2()["furniture"] if d["key"] == "bed")
    cases = []
    for angle in (0, 90, 180, 270, 37):
        placement = {"key": "bed", "x_m": 3, "y_m": 3, "rotation_deg": angle, "placed": True}
        evaluation = evaluate_v2(LayoutV2.model_validate({"schema_version": 2, "revision": 0,
                                                        "room": room, "placements": [placement]}))
        head = next(r for r in evaluation.regions if r.kind == "bed_head")
        cases.append({"placement": placement, "head": head.model_dump()["points"]})
    return {"definition": definition, "room": room, "cases": cases}


if __name__ == "__main__":
    destination = ROOT / "contracts" / "v2" / "bed-head.json"
    destination.write_text(json.dumps(contract(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {destination.name}")
