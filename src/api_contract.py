"""Versioned JSON contract. Arrays are intentional: Unity JsonUtility supports them."""
from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from design_models import (
    CELL_SIZE_M, FURNITURE_PRESETS, Room, WallOpening, WallSide, PlacedFurniture,
    build_items_from_placements, validate_layout,
)
from layout_service import evaluate_layout, generate_candidates


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpeningDTO(DTO):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(default="Opening", max_length=100)
    wall: Literal["LEFT", "RIGHT", "TOP", "BOTTOM"]
    offset: int = Field(ge=0, le=64, strict=True)
    length: int = Field(ge=1, le=64, strict=True)
    placed: bool = True


class RoomDTO(DTO):
    grid_w: int = Field(ge=4, le=64, strict=True)
    grid_h: int = Field(ge=4, le=64, strict=True)
    ceiling_height_m: float = Field(default=2.5, ge=2, le=10)
    doors: list[OpeningDTO] = Field(default_factory=list, max_length=32)
    windows: list[OpeningDTO] = Field(default_factory=list, max_length=32)

    def to_domain(self) -> Room:
        def convert(values):
            return [WallOpening(**(v.model_dump() | {"wall": WallSide(v.wall)})) for v in values]
        return Room(self.grid_w, self.grid_h, doors=convert(self.doors), windows=convert(self.windows))

    @model_validator(mode="after")
    def check_openings(self):
        room = self.to_domain()
        openings = room.doors + room.windows
        if len({o.key for o in openings}) != len(openings):
            raise ValueError("Opening keys must be unique")
        for o in openings:
            room.validate_opening(o)
        for i, a in enumerate(openings):
            for b in openings[i + 1:]:
                if a.placed and b.placed and a.wall == b.wall:
                    if a.offset < b.offset + b.length and b.offset < a.offset + a.length:
                        raise ValueError("Wall openings overlap")
        return self


class PlacementDTO(DTO):
    key: str = Field(min_length=1, max_length=64)
    gx: int = Field(default=0, ge=-64, le=64, strict=True)
    gy: int = Field(default=0, ge=-64, le=64, strict=True)
    rotation: int = Field(default=0, ge=0, le=3, strict=True)
    placed: bool = False


class LayoutDTO(DTO):
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0, le=2147483647, strict=True)
    room: RoomDTO
    placements: list[PlacementDTO] = Field(min_length=1, max_length=len(FURNITURE_PRESETS))

    @model_validator(mode="after")
    def check_keys(self):
        keys = [p.key for p in self.placements]
        if len(set(keys)) != len(keys):
            raise ValueError("Furniture keys must be unique (one instance per catalog entry in v1)")
        if set(keys) - FURNITURE_PRESETS.keys():
            raise ValueError("Unknown furniture key")
        return self

    def to_domain(self):
        # Keep request order: seeded MCMC uses insertion order.
        placements = {
            p.key: PlacedFurniture(p.key, FURNITURE_PRESETS[p.key].label,
                                   p.gx if p.placed else None, p.gy if p.placed else None,
                                   p.rotation, p.placed)
            for p in self.placements
        }
        return self.room.to_domain(), placements


class OptimizationDTO(DTO):
    layout: LayoutDTO
    fixed_keys: list[str] = Field(default_factory=list, max_length=len(FURNITURE_PRESETS))
    candidate_count: int = Field(default=3, ge=1, le=10, strict=True)
    sample_count: int = Field(default=900, ge=2, le=5000, strict=True)
    burn_in: int = Field(default=250, ge=0, le=4999, strict=True)
    sample_stride: int = Field(default=15, ge=1, le=5000, strict=True)
    rng_seed: int | None = Field(default=None, ge=0, le=2147483647, strict=True)

    @model_validator(mode="after")
    def check_search(self):
        if self.burn_in >= self.sample_count:
            raise ValueError("burn_in must be less than sample_count")
        placed = {p.key for p in self.layout.placements if p.placed}
        if len(set(self.fixed_keys)) != len(self.fixed_keys) or set(self.fixed_keys) - placed:
            raise ValueError("fixed_keys must be unique and refer to placed furniture")
        return self


class ScoreTerm(DTO):
    name: str
    value: float


class RegionDTO(DTO):
    kind: str
    key: str
    x0: int
    y0: int
    x1: int
    y1: int


class EvaluationDTO(DTO):
    schema_version: Literal[1] = 1
    revision: int
    total: float
    breakdown: list[ScoreTerm]
    violations: list[str]
    fall_overlap_cells: int
    regions: list[RegionDTO]


class CandidateDTO(DTO):
    placements: list[PlacementDTO]
    cost: float
    score_breakdown: list[ScoreTerm]
    violations: list[str]
    valid: bool
    accepted_steps: int
    source_sample_index: int


class JobDTO(DTO):
    schema_version: Literal[1] = 1
    id: str
    revision: int
    status: Literal["queued", "running", "succeeded", "failed"]
    candidates: list[CandidateDTO] = Field(default_factory=list)
    error: str | None = None


def catalog_payload():
    return {
        "schema_version": 1, "cell_size_m": CELL_SIZE_M,
        "furniture": [asdict(p) | {"model_id": p.key} for p in FURNITURE_PRESETS.values()],
    }


def evaluate_payload(layout: LayoutDTO) -> EvaluationDTO:
    room, placements = layout.to_domain()
    if any(not p.placed for p in placements.values()):
        raise ValueError("Place all furniture in the request before evaluation")
    result = evaluate_layout(room, placements)
    return EvaluationDTO(
        revision=layout.revision, total=result.score.total,
        breakdown=[ScoreTerm(name=k, value=v) for k, v in result.score.breakdown.items()],
        violations=result.score.violations, fall_overlap_cells=result.fall_overlap_cells,
        regions=[RegionDTO(kind=r.kind, key=r.key, x0=r.rect[0], y0=r.rect[1],
                           x1=r.rect[2], y1=r.rect[3]) for r in result.regions],
    )


def optimize_payload(payload: dict) -> list[dict]:
    """Top-level, pickleable process-worker entry point (including on Windows)."""
    request = OptimizationDTO.model_validate(payload)
    room, placements = request.layout.to_domain()
    solutions = generate_candidates(
        room, placements, fixed_keys=set(request.fixed_keys),
        **request.model_dump(exclude={"layout", "fixed_keys"}),
    )
    results = []
    for s in solutions:
        valid = True
        try:
            validate_layout(room, build_items_from_placements(s.placements))
        except ValueError:
            valid = False
        candidate = CandidateDTO(
            placements=[PlacementDTO(key=p.key, gx=p.gx if p.gx is not None else 0,
                                     gy=p.gy if p.gy is not None else 0,
                                     rotation=p.rotation, placed=p.placed)
                        for p in s.placements.values()],
            cost=s.cost, score_breakdown=[ScoreTerm(name=k, value=v) for k, v in s.score_breakdown.items()],
            violations=s.violations, valid=valid,
            accepted_steps=s.accepted_steps, source_sample_index=s.source_sample_index,
        )
        results.append(candidate.model_dump())
    return results
