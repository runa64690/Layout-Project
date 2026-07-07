import json
from pathlib import Path

import prior


def main():
    print("Loading ProcTHOR-10K dataset...")

    dataset = prior.load_dataset("procthor-10k")

    print("Dataset loaded.")
    print("Splits:, train, val, test")
    #print("Splits:", dataset.keys())

    # まず train の1件目を読む
    house = dataset["train"][0]

    print("\nHouse type:", type(house))
    print("House keys:")
    for key in house.keys():
        print(" -", key)

    # objects が家具・小物などのリスト
    objects = house.get("objects", [])
    print("\nNumber of objects:", len(objects))

    print("\nFirst 5 objects:")
    for obj in objects[:5]:
        print(json.dumps(obj, indent=2, ensure_ascii=False)[:1000])
        print("-" * 60)

    # 後で見やすいようにJSONとして保存
    output_dir = Path("procthor_work/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "sample_house_0.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(house, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()