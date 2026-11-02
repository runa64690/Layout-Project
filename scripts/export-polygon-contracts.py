"""Export v2 contracts without overwriting the existing v1 examples."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from api import app
from api_v2 import LayoutV2, catalog_v2, evaluate_v2, optimize_v2


def main():
    output = ROOT / "contracts" / "v2"
    output.mkdir(exist_ok=True)
    example = {
        "schema_version": 2, "revision": 1,
        "room": {"vertices": [{"id": f"v{i}", "x": x, "y": y}
                              for i, (x, y) in enumerate([(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)])],
                 "doors": [{"key": "door_1", "label": "ドア", "edge_id": "v0", "offset_m": .2, "width_m": .8}],
                 "windows": []},
        "placements": [{"key": "chair", "x_m": .5, "y_m": 2.5, "rotation_deg": 23, "placed": True},
                       {"key": "shelf", "x_m": 2.8, "y_m": .8, "rotation_deg": 0, "placed": True}],
    }
    request = {"layout": example, "fixed_keys": ["chair"], "candidate_count": 3,
               "sample_count": 30, "burn_in": 5, "sample_stride": 5, "rng_seed": 42}
    examples = {"catalog.json": catalog_v2(), "layout.json": example,
                "evaluation.json": evaluate_v2(LayoutV2.model_validate(example)).model_dump(),
                "optimization-request.json": request,
                "optimization-result.json": {"schema_version": 2, "id": "example-job", "revision": 1,
                                             "status": "succeeded", "error": None, "candidates": optimize_v2(request)},
                "openapi.json": app.openapi()}
    for name, data in examples.items():
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Exported {len(examples)} polygon API examples")


if __name__ == "__main__":
    main()
