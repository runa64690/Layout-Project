import math
import random

import pytest
from pydantic import ValidationError

from api_contract import LayoutDTO, PlacementDTO, evaluate_payload, optimize_payload
from design_models import PlacedFurniture, Room, build_furniture_from_placement, validate_layout
from layout_cost import build_fall_zone_polygon, score_clearance_violation, _build_occupancy
from mcmc_solver import MCMCSolver
from spatial_geometry import bounds, intersection_area, overlaps, polygon_area, rect_polygon


def item(key, x, y, rotation=0):
    return build_furniture_from_placement(key, PlacedFurniture(key, key, x, y, rotation, True))


@pytest.mark.parametrize("rotation", [0, .1, .5, 1, 1.37, 2.5, 3.999])
def test_rotated_geometry_preserves_area_and_bounds(rotation):
    furniture = item("shelf", 2.125, 3.375, rotation)
    assert polygon_area(furniture.footprint) == pytest.approx(8)
    assert bounds(furniture.footprint) == pytest.approx((furniture.gx, furniture.gy,
                                                      furniture.gx + furniture.gw, furniture.gy + furniture.gd))
    zone = build_fall_zone_polygon(furniture)
    assert polygon_area(zone) == pytest.approx(28)
    assert intersection_area(zone, furniture.footprint) == pytest.approx(0, abs=1e-8)


def test_clockwise_fall_direction_at_45_degrees():
    furniture = item("shelf", 3, 3, .5)
    zone = build_fall_zone_polygon(furniture)
    center = (sum(x for x, y in zone)/4, sum(y for x, y in zone)/4)
    dx, dy = center[0]-furniture.center[0], center[1]-furniture.center[1]
    assert dx > 0 and dx == pytest.approx(dy)


def test_overlapping_bounding_boxes_can_have_disjoint_footprints():
    left, right = item("shelf", 2, 2, .5), item("table", 4, 4, .5)
    assert overlaps(rect_polygon(bounds(left.footprint)), rect_polygon(bounds(right.footprint)))
    assert not overlaps(left.footprint, right.footprint)
    validate_layout(Room(16, 16), [left, right])


def test_touching_is_allowed_but_fractional_overlap_is_rejected():
    left, right = item("shelf", .125, .25), item("table", 4.125, .25)
    validate_layout(Room(16, 16), [left, right])
    right.gx -= .001
    with pytest.raises(ValueError, match="overlap"):
        validate_layout(Room(16, 16), [left, right])


def test_rotated_bounds_and_partial_door_obstruction_are_rejected():
    with pytest.raises(ValueError, match="bounds"):
        validate_layout(Room(12, 12), [item("shelf", 8, 8, .5)])
    room = Room(12, 12, exit_ax=0, exit_ay=5, exit_bx=0, exit_by=7)
    with pytest.raises(ValueError, match="Door"):
        validate_layout(room, [item("chair", .9, 5.1)])


def test_clearance_uses_fractional_area():
    shelf, chair = item("shelf", 2.25, 2.25), item("chair", 3.25, 5.75)
    score, _ = score_clearance_violation(Room(16, 16), [shelf, chair])
    assert score == pytest.approx(.5)


def test_circulation_uses_rotated_footprint_and_ignores_ceiling():
    room = Room(16, 16)
    shelf = item("shelf", 2, 2, .5)
    grid = _build_occupancy(room, [shelf, item("ceiling_light", 10.1, 10.1, .25)])
    assert not grid[2][2]  # empty corner of the bounding box
    assert grid[4][4]
    assert not grid[10][10]


@pytest.mark.parametrize("updates", [{"gx": float("nan")}, {"gy": float("inf")},
                                    {"rotation": 4}, {"rotation": -.01}, {"gx": True}])
def test_nonfinite_or_invalid_placement_is_rejected(updates):
    with pytest.raises(ValidationError):
        PlacementDTO(key="shelf", **updates)


def test_fractional_evaluation_and_fixed_search_round_trip():
    layout = LayoutDTO.model_validate({"room": {"grid_w": 16, "grid_h": 16},
        "placements": [{"key": "shelf", "gx": 2.125, "gy": 3.375, "rotation": .37, "placed": True},
                       {"key": "chair", "gx": 10.2, "gy": 10.3, "rotation": 1.123, "placed": True}]})
    evaluation = evaluate_payload(layout)
    assert math.isfinite(evaluation.total)
    assert len(evaluation.regions[0].points) == 4
    request = {"layout": layout.model_dump(), "fixed_keys": ["shelf"], "candidate_count": 2,
               "sample_count": 40, "burn_in": 5, "sample_stride": 5, "rng_seed": 42}
    results = optimize_payload(request)
    assert results and all(c["valid"] for c in results)
    for result in results:
        fixed = next(p for p in result["placements"] if p["key"] == "shelf")
        assert fixed == layout.placements[0].model_dump()


def test_rotation_proposals_preserve_center_and_fixed_furniture():
    solver = MCMCSolver()
    original = {"shelf": PlacedFurniture("shelf", "Shelf", 4.125, 4.375, .2, True)}
    rng = random.Random(4)
    rotations = 0
    for _ in range(30):
        proposed = solver._propose_neighbor(Room(16, 16), original, set(), rng)
        if proposed["shelf"].rotation != original["shelf"].rotation:
            rotations += 1
            assert build_furniture_from_placement("shelf", proposed["shelf"]).center == pytest.approx(
                build_furniture_from_placement("shelf", original["shelf"]).center)
    assert rotations > 0
    assert solver._propose_neighbor(Room(16, 16), original, {"shelf"}, rng) == original
