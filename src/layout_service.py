"""UI-free application operations shared by Tkinter and the HTTP adapter."""
from __future__ import annotations

from dataclasses import dataclass
from spatial_geometry import bounds, rect_polygon

from design_models import FurnitureType, Room, PlacedFurniture, build_items_from_placements
from layout_cost import (
    LayoutScore, evaluate_layout_cost, total_fall_hazard_overlap_cells,
    build_fall_zone_polygon, build_bed_head_zone_polygon,
)
from layout_geometry import build_door_front_rect, build_window_scatter_rect
from mcmc_solver import MCMCSolver, LayoutSolution


@dataclass
class DisplayRegion:
    kind: str
    key: str
    rect: tuple[float, float, float, float]
    points: list[tuple[float, float]]


@dataclass
class LayoutEvaluation:
    score: LayoutScore
    fall_overlap_cells: float
    regions: list[DisplayRegion]


def evaluate_layout(room: Room, placements: dict[str, PlacedFurniture]) -> LayoutEvaluation:
    items = build_items_from_placements(placements)
    score = evaluate_layout_cost(room, items)
    regions = []
    for item in items:
        polygon = build_fall_zone_polygon(item)
        if polygon is not None:
            regions.append(DisplayRegion("fall", item.key, bounds(polygon), polygon))
        if item.furniture_type == FurnitureType.BED:
            polygon = build_bed_head_zone_polygon(item)
            regions.append(DisplayRegion("bed_head", item.key, bounds(polygon), polygon))
    for kind, openings, builder in (
        ("door_front", room.doors, build_door_front_rect),
        ("window_scatter", room.windows, build_window_scatter_rect),
    ):
        for opening in openings:
            rect = builder(room, opening)
            if rect is not None:
                regions.append(DisplayRegion(kind, opening.key, rect, rect_polygon(rect)))
    return LayoutEvaluation(score, total_fall_hazard_overlap_cells(items), regions)


def generate_candidates(
    room: Room, placements: dict[str, PlacedFurniture], *,
    fixed_keys: set[str] | None = None, candidate_count: int = 3,
    sample_count: int = 900, burn_in: int = 250, sample_stride: int = 15,
    rng_seed: int | None = None, continuous: bool = True,
) -> list[LayoutSolution]:
    return MCMCSolver(continuous=continuous).generate_layout_candidates(
        room, placements, fixed_keys=fixed_keys, candidate_count=candidate_count,
        sample_count=sample_count, burn_in=burn_in, sample_stride=sample_stride,
        rng_seed=rng_seed,
    )
