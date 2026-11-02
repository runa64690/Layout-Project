"""Meter-based polygon API. Conversion into legacy solver units stays here."""
from dataclasses import asdict
import math
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator
from shapely.geometry import Polygon

from api_contract import (DTO, Restraint, Protection, OptimizationDTO, SafetyDTO, MitigationDTO,
                          ScoreTerm, safety_payload, mitigation_payload)
from design_models import CELL_SIZE_M, FURNITURE_PRESETS, PlacedFurniture, build_items_from_placements, get_rotated_size, validate_layout
from polygon_room import PolygonRoom, PolygonOpening, polygon_parts
from layout_cost import evaluate_layout_cost
from layout_service import generate_candidates
from layout_safety import bed_head_polygon


class VertexV2(DTO):
    id: str = Field(min_length=1, max_length=64)
    x: float = Field(ge=-100, le=100, allow_inf_nan=False)
    y: float = Field(ge=-100, le=100, allow_inf_nan=False)


class OpeningV2(DTO):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(default="Opening", max_length=100)
    edge_id: str = Field(min_length=1, max_length=64)
    offset_m: float = Field(ge=0, le=24, allow_inf_nan=False)
    width_m: float = Field(gt=0, le=24, allow_inf_nan=False)
    placed: bool = True
    film: Protection = "unknown"
    curtains: Protection = "unknown"


class RoomV2(DTO):
    vertices: list[VertexV2] = Field(min_length=3, max_length=64)
    ceiling_height_m: float = Field(default=2.5, ge=2, le=10, allow_inf_nan=False)
    doors: list[OpeningV2] = Field(default_factory=list, max_length=32)
    windows: list[OpeningV2] = Field(default_factory=list, max_length=32)

    @property
    def origin(self):
        return min(v.x for v in self.vertices), min(v.y for v in self.vertices)

    def to_domain(self):
        ox, oy = self.origin
        points = [((v.x-ox)/CELL_SIZE_M, (v.y-oy)/CELL_SIZE_M) for v in self.vertices]
        def convert(values):
            return [PolygonOpening(v.key, v.label, v.edge_id, v.offset_m/CELL_SIZE_M,
                                   v.width_m/CELL_SIZE_M, v.placed, v.film, v.curtains) for v in values]
        return PolygonRoom(math.ceil(max(x for x, y in points)), math.ceil(max(y for x, y in points)),
                           doors=convert(self.doors), windows=convert(self.windows),
                           boundary=points, vertex_ids=[v.id for v in self.vertices])

    @model_validator(mode="after")
    def validate_geometry(self):
        points = [(v.x, v.y) for v in self.vertices]
        if len({v.id for v in self.vertices}) != len(points):
            raise ValueError("Vertex IDs must be unique")
        if any(math.dist(a, b) <= 1e-6 for a, b in zip(points, points[1:]+points[:1])):
            raise ValueError("Room has a zero-length edge")
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area <= 1e-8:
            raise ValueError("Room boundary intersects, touches or has zero area")
        x0, y0, x1, y1 = polygon.bounds
        if x1-x0 > 16 or y1-y0 > 16:
            raise ValueError("Room width and height must each be at most 16 m")
        room = self.to_domain()
        openings = room.doors+room.windows
        if len({o.key for o in openings}) != len(openings):
            raise ValueError("Opening keys must be unique")
        for i, opening in enumerate(openings):
            # Unplaced openings retain the old edge so the editor can repair them.
            if not opening.placed:
                continue
            room.validate_opening(opening)
            for other in openings[:i]:
                if other.placed and other.edge_id == opening.edge_id and max(other.offset, opening.offset) < min(other.offset+other.length, opening.offset+opening.length)-1e-6:
                    raise ValueError("Wall openings overlap")
        return self


class PlacementV2(DTO):
    key: str = Field(min_length=1, max_length=64)
    x_m: float = Field(default=0, ge=-100, le=100, allow_inf_nan=False)
    y_m: float = Field(default=0, ge=-100, le=100, allow_inf_nan=False)
    rotation_deg: float = Field(default=0, ge=0, lt=360, allow_inf_nan=False)
    placed: bool = False
    restraint: Restraint = "unknown"
    installation_confirmed: bool = False

    @model_validator(mode="after")
    def check_confirmation(self):
        if self.installation_confirmed and (not self.placed or self.restraint in ("none", "unknown")):
            raise ValueError("Installation confirmation requires a placed, restrained item")
        return self


class LayoutV2(DTO):
    schema_version: Literal[2] = 2
    revision: int = Field(default=0, ge=0, le=2147483647, strict=True)
    room: RoomV2
    placements: list[PlacementV2] = Field(default_factory=list, max_length=len(FURNITURE_PRESETS))

    @model_validator(mode="after")
    def check_keys(self):
        keys = [p.key for p in self.placements]
        if len(set(keys)) != len(keys) or set(keys)-FURNITURE_PRESETS.keys():
            raise ValueError("Furniture keys must be unique catalog entries")
        return self

    def to_domain(self):
        ox, oy = self.room.origin
        placements = {}
        for p in self.placements:
            preset = FURNITURE_PRESETS[p.key]
            rotation = p.rotation_deg/90
            w, h = get_rotated_size(preset.gw, preset.gd, rotation)
            placements[p.key] = PlacedFurniture(p.key, preset.label,
                (p.x_m-ox)/CELL_SIZE_M-w/2 if p.placed else None,
                (p.y_m-oy)/CELL_SIZE_M-h/2 if p.placed else None,
                rotation, p.placed, p.restraint, p.installation_confirmed)
        return self.room.to_domain(), placements


class OptimizationV2(OptimizationDTO):
    layout: LayoutV2

    @model_validator(mode="after")
    def require_furniture(self):
        if not self.layout.placements:
            raise ValueError("Select at least one furniture item")
        return self


class PointMetersV2(DTO):
    x: float
    y: float


class RegionV2(DTO):
    kind: str
    key: str
    scenario_id: str = ""
    primary: bool = False
    points: list[PointMetersV2]


class CandidateV2(DTO):
    evaluation_version: int = 3
    placements: list[PlacementV2]
    cost: float
    valid: bool
    safety: SafetyDTO
    natural_cost: float
    violations: list[str]


class EvaluationV2(DTO):
    schema_version: Literal[2] = 2
    evaluation_version: int = 3
    revision: int
    area_m2: float
    tatami: float
    total: float
    breakdown: list[ScoreTerm]
    violations: list[str]
    safety: SafetyDTO
    natural_cost: float
    mitigations: list[MitigationDTO]
    regions: list[RegionV2]
    limitations: list[str] = Field(default_factory=lambda: ["避難経路は25cm格子による近似です。細い通路や斜めの境界では到達不能と判定される場合があります。"])


class JobV2(DTO):
    schema_version: Literal[2] = 2
    id: str
    revision: int
    status: Literal["queued", "running", "succeeded", "failed"]
    candidates: list[CandidateV2] = Field(default_factory=list)
    error: str | None = None


def catalog_v2():
    labels = {"bed": "ベッド", "shelf": "本棚", "table": "テーブル", "tv_unit": "テレビ台", "chair": "椅子", "ceiling_light": "天井照明"}
    return {"schema_version": 2, "evaluation_version": 3, "tatami_m2": 1.62,
            "capabilities": ["polygon_rooms", "arbitrary_wall_angles", "continuous_placement", "safety_scenarios"],
            "furniture": [asdict(p) | {"label": labels[p.key], "model_id": p.key,
                "width_m": p.gw*CELL_SIZE_M, "depth_m": p.gd*CELL_SIZE_M, "height_m": p.h_cell*CELL_SIZE_M}
                for p in FURNITURE_PRESETS.values()]}


def evaluate_v2(layout):
    room, placements = layout.to_domain()
    if any(not p.placed for p in placements.values()):
        raise ValueError("Place all selected furniture before evaluation")
    items = build_items_from_placements(placements)
    result = evaluate_layout_cost(room, items)
    ox, oy = layout.room.origin
    regions = []
    def add(kind, key, points, sid="", primary=False):
        regions.append({"kind": kind, "key": key, "scenario_id": sid, "primary": primary,
                        "points": [{"x": x*CELL_SIZE_M+ox, "y": y*CELL_SIZE_M+oy} for x, y in points]})
    for s in result.safety.scenarios:
        add(s.kind, s.source_key, s.points, s.id, s.primary)
    for door in room.doors:
        for part in polygon_parts(room.door_front(door)):
            add("door_front", door.key, list(part.exterior.coords)[:-1])
    for item in items:
        if item.key == "bed":
            add("bed_head", item.key, bed_head_polygon(item))
    area = room.polygon.area*CELL_SIZE_M**2
    return EvaluationV2(revision=layout.revision, area_m2=area, tatami=area/1.62,
        total=result.total, breakdown=[{"name": k, "value": v} for k, v in result.breakdown.items()],
        violations=result.violations, safety=safety_payload(result.safety).model_dump(),
        natural_cost=result.natural_cost, mitigations=[m.model_dump() for m in mitigation_payload(room, placements)], regions=regions)


def optimize_v2(payload):
    request = OptimizationV2.model_validate(payload)
    room, placements = request.layout.to_domain()
    solutions = generate_candidates(room, placements, fixed_keys=set(request.fixed_keys),
                                    **request.model_dump(exclude={"layout", "fixed_keys"}))
    ox, oy = request.layout.room.origin
    results = []
    original = {p.key: p for p in request.layout.placements}
    for solution in solutions:
        validate_layout(room, build_items_from_placements(solution.placements))
        output = []
        for key, p in solution.placements.items():
            item = build_items_from_placements({key: p})[0]
            value = PlacementV2(key=key, x_m=item.center[0]*CELL_SIZE_M+ox, y_m=item.center[1]*CELL_SIZE_M+oy,
                                rotation_deg=p.rotation*90, placed=True, restraint=p.restraint)
            before = original[key]
            unchanged = before.placed and all(abs(a-b) < 1e-8 for a, b in ((value.x_m, before.x_m), (value.y_m, before.y_m), (value.rotation_deg, before.rotation_deg)))
            if key in request.fixed_keys:
                value = before.model_copy()
            else:
                value.installation_confirmed = before.installation_confirmed and unchanged
            output.append(value.model_dump())
        results.append({"evaluation_version": 3, "placements": output, "cost": solution.cost, "valid": True,
                        "safety": safety_payload(solution.safety).model_dump(), "natural_cost": solution.natural_cost,
                        "violations": solution.violations})
    return results


def register_v2(application):
    @application.get("/api/v2/catalog")
    def catalog():
        return catalog_v2()

    @application.post("/api/v2/evaluate", response_model=EvaluationV2)
    def evaluate(layout: LayoutV2):
        try:
            return evaluate_v2(layout)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.post("/api/v2/optimization-jobs", response_model=JobV2, status_code=202)
    def optimize(request: OptimizationV2):
        room, placements = request.layout.to_domain()
        try:
            validate_layout(room, build_items_from_placements({k: placements[k] for k in request.fixed_keys}))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return application.state.polygon_jobs.submit(request)

    @application.get("/api/v2/optimization-jobs/{job_id}", response_model=JobV2)
    def job(job_id: str):
        return application.state.polygon_jobs.get(job_id)
