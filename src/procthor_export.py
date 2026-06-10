from __future__ import annotations

import argparse
import json
from pathlib import Path

from procthor_normalize import normalize_house_dict


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RAW_OUTPUT = ROOT_DIR / "outputs" / "procthor_house.json"
DEFAULT_WEB_OUTPUT = ROOT_DIR / "web" / "public" / "data" / "house.json"


def generate_house(seed: int, split: str) -> dict:
    try:
        from procthor.generation import HouseGenerator, PROCTHOR10K_ROOM_SPEC_SAMPLER
    except ModuleNotFoundError as exc:
        missing = exc.name or "dependency"
        raise RuntimeError(
            f"Missing dependency: {missing}. Install the required packages in the "
            "project virtual environment before generating a ProcTHOR house."
        ) from exc

    house_generator = HouseGenerator(
        split=split,
        seed=seed,
        room_spec_sampler=PROCTHOR10K_ROOM_SPEC_SAMPLER,
    )
    house, _ = house_generator.sample()
    return house.data


def export_house(seed: int, split: str, raw_output: Path, web_output: Path) -> dict:
    house = generate_house(seed=seed, split=split)

    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(json.dumps(house, indent=2), encoding="utf-8")

    normalized = normalize_house_dict(house)
    web_output.parent.mkdir(parents=True, exist_ok=True)
    web_output.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and normalize a ProcTHOR house.")
    parser.add_argument("--seed", type=int, default=42, help="Seed for ProcTHOR generation.")
    parser.add_argument(
        "--split",
        choices=["train", "val", "test"],
        default="train",
        help="ProcTHOR data split.",
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=DEFAULT_RAW_OUTPUT,
        help="Path to write the raw ProcTHOR house JSON.",
    )
    parser.add_argument(
        "--web-output",
        type=Path,
        default=DEFAULT_WEB_OUTPUT,
        help="Path to write the normalized Web viewer JSON.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    normalized = export_house(
        seed=args.seed,
        split=args.split,
        raw_output=args.raw_output,
        web_output=args.web_output,
    )
    print(
        f"Exported {len(normalized['objects'])} objects, "
        f"{len(normalized['rooms'])} rooms to {args.web_output}"
    )


if __name__ == "__main__":
    main()
