from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


def load_asset_id_database() -> dict[str, dict[str, Any]]:
    import procthor.databases

    database_path = resources.files(procthor.databases).joinpath("asset-database.json")
    asset_database = json.loads(database_path.read_text(encoding="utf-8"))

    asset_id_database: dict[str, dict[str, Any]] = {}
    for assets in asset_database.values():
        for asset in assets:
            asset_id_database[asset["assetId"]] = asset
    return asset_id_database


def _vector3(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": float(x), "y": float(y), "z": float(z)}


def _polygon_bounds(points: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    zs = [float(point["z"]) for point in points]
    return {
        "min": _vector3(min(xs), min(ys), min(zs)),
        "max": _vector3(max(xs), max(ys), max(zs)),
    }


def _normalize_room(room: dict[str, Any]) -> dict[str, Any]:
    floor_polygon = [_vector3(point["x"], point["y"], point["z"]) for point in room["floorPolygon"]]
    return {
        "id": room["id"],
        "roomType": room.get("roomType", "Unknown"),
        "floorPolygon": floor_polygon,
        "floorMaterial": room.get("floorMaterial"),
        "bounds": _polygon_bounds(floor_polygon),
    }


def _normalize_wall(wall: dict[str, Any]) -> dict[str, Any]:
    polygon = [_vector3(point["x"], point["y"], point["z"]) for point in wall["polygon"]]
    return {
        "id": wall["id"],
        "roomId": wall.get("roomId"),
        "material": wall.get("material"),
        "polygon": polygon,
        "empty": bool(wall.get("empty", False)),
    }


def _normalize_opening(opening: dict[str, Any], asset_id_database: dict[str, dict[str, Any]]) -> dict[str, Any]:
    asset = asset_id_database.get(opening["assetId"], {})
    bbox = opening.get("boundingBox", {})
    return {
        "id": opening["id"],
        "assetId": opening["assetId"],
        "objectType": asset.get("objectType"),
        "room0": opening.get("room0"),
        "room1": opening.get("room1"),
        "wall0": opening.get("wall0"),
        "wall1": opening.get("wall1"),
        "boundingBox": {
            "min": _vector3(
                bbox.get("min", {}).get("x", 0.0),
                bbox.get("min", {}).get("y", 0.0),
                bbox.get("min", {}).get("z", 0.0),
            ),
            "max": _vector3(
                bbox.get("max", {}).get("x", 0.0),
                bbox.get("max", {}).get("y", 0.0),
                bbox.get("max", {}).get("z", 0.0),
            ),
        },
    }


def _normalize_object(
    obj: dict[str, Any],
    asset_id_database: dict[str, dict[str, Any]],
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    asset = asset_id_database.get(obj["assetId"], {})
    size = asset.get("boundingBox", {})
    normalized = {
        "id": obj["id"],
        "parentId": parent_id,
        "assetId": obj["assetId"],
        "objectType": asset.get("objectType", "Unknown"),
        "position": _vector3(
            obj["position"]["x"],
            obj["position"]["y"],
            obj["position"]["z"],
        ),
        "rotation": _vector3(
            obj["rotation"]["x"],
            obj["rotation"]["y"],
            obj["rotation"]["z"],
        ),
        "size": _vector3(
            size.get("x", 0.5),
            size.get("y", 0.5),
            size.get("z", 0.5),
        ),
        "kinematic": bool(obj.get("kinematic", False)),
        "childrenIds": [child["id"] for child in obj.get("children", [])],
    }

    normalized_objects = [normalized]
    for child in obj.get("children", []):
        normalized_objects.extend(
            _normalize_object(
                child,
                asset_id_database=asset_id_database,
                parent_id=obj["id"],
            )
        )
    return normalized_objects


def normalize_house_dict(house: dict[str, Any]) -> dict[str, Any]:
    asset_id_database = load_asset_id_database()

    objects: list[dict[str, Any]] = []
    for obj in house.get("objects", []) or []:
        objects.extend(_normalize_object(obj, asset_id_database=asset_id_database))

    return {
        "schemaVersion": 1,
        "metadata": house.get("metadata", {}),
        "rooms": [_normalize_room(room) for room in house.get("rooms", []) or []],
        "walls": [_normalize_wall(wall) for wall in house.get("walls", []) or []],
        "doors": [
            _normalize_opening(door, asset_id_database=asset_id_database)
            for door in house.get("doors", []) or []
        ],
        "windows": [
            _normalize_opening(window, asset_id_database=asset_id_database)
            for window in house.get("windows", []) or []
        ],
        "objects": objects,
    }


def normalize_house_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)

    house = json.loads(input_path.read_text(encoding="utf-8"))
    normalized = normalize_house_dict(house)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return normalized
