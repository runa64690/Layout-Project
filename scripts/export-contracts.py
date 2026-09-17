"""Export reviewable API examples and OpenAPI; run from the repository root."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from api import app
from api_contract import LayoutDTO, catalog_payload, evaluate_payload, optimize_payload


def main():
    output = ROOT / "contracts"
    output.mkdir(exist_ok=True)
    example = {
        "schema_version": 1, "revision": 1,
        "room": {"grid_w": 12, "grid_h": 12, "ceiling_height_m": 2.5,
                 "doors": [{"key": "door_1", "label": "Door", "wall": "LEFT", "offset": 5, "length": 2, "placed": True}],
                 "windows": [{"key": "window_1", "label": "Window", "wall": "TOP", "offset": 5, "length": 2, "placed": True}]},
        "placements": [
            {"key": "shelf", "gx": 8, "gy": 9, "rotation": 0, "placed": True},
            {"key": "bed", "gx": 4, "gy": 5, "rotation": 0, "placed": True},
            {"key": "table", "gx": 5, "gy": 1, "rotation": 0, "placed": True},
            {"key": "tv_unit", "gx": 8, "gy": 1, "rotation": 0, "placed": True},
            {"key": "chair", "gx": 3, "gy": 1, "rotation": 0, "placed": True},
            {"key": "ceiling_light", "gx": 5, "gy": 5, "rotation": 0, "placed": True},
        ],
    }
    request = {"layout": example, "fixed_keys": ["bed"], "candidate_count": 3,
               "sample_count": 900, "burn_in": 250, "sample_stride": 15, "rng_seed": 42}
    examples = {
        "openapi.json": app.openapi(), "catalog.json": catalog_payload(),
        "layout.json": example, "evaluation.json": evaluate_payload(LayoutDTO.model_validate(example)).model_dump(),
        "optimization-request.json": request,
        "optimization-result.json": {"schema_version": 1, "revision": 1, "id": "example-job",
                                     "status": "succeeded", "error": None, "candidates": optimize_payload(request)},
    }
    for name, data in examples.items():
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(examples)} contract files to {output}")


if __name__ == "__main__":
    main()
