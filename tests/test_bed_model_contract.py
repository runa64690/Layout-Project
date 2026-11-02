"""Keep the head regions used by the Web GLB test aligned with the real API."""
import importlib.util
import json
from pathlib import Path


def test_web_bed_head_contract_matches_current_api():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("bed_head_contract", root / "scripts/export-bed-head-contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Compare JSON wire values (the catalog also contains tuple-valued fields).
    assert json.loads(json.dumps(module.contract())) == json.loads((root / "contracts/v2/bed-head.json").read_text(encoding="utf-8"))
