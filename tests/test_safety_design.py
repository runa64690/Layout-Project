from copy import deepcopy
from dataclasses import asdict, replace
import math

import pytest

from api_contract import LayoutDTO, evaluate_payload, optimize_payload, PlacementDTO
from design_models import (CELL_SIZE_M, Room, WallOpening, WallSide, PlacedFurniture,
                           build_items_from_placements, build_furniture_from_placement, validate_layout)
from layout_safety import assess_safety, build_hazard_scenarios, bed_head_polygon, HazardScenario
from layout_service import evaluate_layout
from mcmc_solver import MCMCSolver
from spatial_geometry import intersection_area, polygon_area, rect_polygon
from wall_alignment import alignment_cost, wall_placements


def p(key, x, y, rotation=0, **kwargs):
    return PlacedFurniture(key, key, x, y, rotation, True, **kwargs)


def room():
    return Room(16, 16, doors=[WallOpening('door', 'Door', WallSide.LEFT, 12, 2, True)])


def test_primary_exposure_tracks_facing_and_keeps_reverse_scenario():
    r = room()
    placements = {'shelf': p('shelf', 4, 4), 'bed': p('bed', 3, 8)}
    facing = evaluate_layout(r, placements).score
    placements['shelf'].rotation = 2
    away = evaluate_layout(r, placements).score
    assert facing.safety.primary_overlap_area_m2 > away.safety.primary_overlap_area_m2
    assert facing.rank > away.rank
    # Turning away does not remove the conservative rear-fall hazard.
    assert away.safety.overlap_area_m2 > 0


@pytest.mark.parametrize('rotation', [0, .37, .5, 1.83, 3.999])
def test_display_and_safety_share_exact_clipped_polygons(rotation):
    placements = {'shelf': p('shelf', 1.1, 1.2, rotation), 'bed': p('bed', 8, 8)}
    result = evaluate_layout(room(), placements)
    hazards = {s.id: s for s in result.score.safety.scenarios}
    for region in result.regions:
        if region.scenario_id:
            assert region.points == hazards[region.scenario_id].points
            assert all(-1e-6 <= x <= 16+1e-6 and -1e-6 <= y <= 16+1e-6 for x, y in region.points)
    assert not any(r.kind == 'window_scatter' for r in result.regions)


def test_bed_head_is_inside_bed_at_arbitrary_rotation():
    bed = build_furniture_from_placement('bed', p('bed', 4, 4, .37))
    head = bed_head_polygon(bed)
    assert polygon_area(head) == pytest.approx(8)
    assert intersection_area(head, bed.footprint) == pytest.approx(polygon_area(head))


def test_wall_backed_retains_lateral_but_not_wallward_scenario():
    r = room()
    shelf = build_furniture_from_placement('shelf', p('shelf', 4, .08))
    directions = {s.direction for s in build_hazard_scenarios(r, [shelf])}
    assert directions == {'NORTH', 'EAST', 'WEST'}
    shelf.gy = 4
    assert len(build_hazard_scenarios(r, [shelf])) == 4


def test_fall_closes_only_exit_while_original_layout_is_legal():
    r = Room(12, 12, doors=[WallOpening('door', 'Door', WallSide.LEFT, 5, 2, True)])
    placements = {'shelf': p('shelf', 4, 5), 'bed': p('bed', 5, 8)}
    items = build_items_from_placements(placements)
    validate_layout(r, items)
    result = assess_safety(r, items)
    assert not any(i.kind == 'escape_blocked' and i.scenario_id == 'baseline' for i in result.issues)
    assert any(i.kind == 'escape_blocked' and i.scenario_id == 'shelf:WEST' for i in result.issues)
    assert result.route_checks == 1 + len(result.scenarios)
    assert result.failed_route_checks < result.route_checks


def test_ceiling_drop_exposes_bed_without_blocking_baseline_floor():
    placements = {'bed': p('bed', 4, 4), 'ceiling_light': p('ceiling_light', 5, 5)}
    result = evaluate_layout(room(), placements).score.safety
    assert any(i.kind == 'exposure' and i.source_key == 'ceiling_light' for i in result.issues)
    assert not any(i.kind == 'escape_blocked' and i.scenario_id == 'baseline' for i in result.issues)


def test_no_exit_is_unassessed_never_met():
    result = evaluate_layout(Room(16,16), {'chair': p('chair', 4, 4)}).score.safety
    assert result.status == 'not_evaluated'
    assert result.route_checks == 0
    assert result.unassessed


def test_window_distance_and_protection_do_not_erase_hazards():
    layout = {'room': {'grid_w':16, 'grid_h':16,
        'doors':[{'key':'door','wall':'LEFT','offset':12,'length':2}],
        'windows':[{'key':'window','wall':'BOTTOM','offset':4,'length':4}]},
        'placements':[{'key':'bed','gx':4.,'gy':1.,'placed':True},
                      {'key':'shelf','gx':4.,'gy':7.,'rotation':2.,'placed':True}]}
    before = evaluate_payload(LayoutDTO.model_validate(layout))
    layout['placements'][1].update(restraint='wall_bracket', installation_confirmed=True)
    layout['room']['windows'][0].update(film='present', curtains='present')
    protected = evaluate_payload(LayoutDTO.model_validate(layout))
    assert before.safety == protected.safety
    assert before.total == protected.total
    assert protected.mitigations[1].installation_confirmed
    far = deepcopy(layout)
    far['placements'] = [dict(layout['placements'][0], gy=10.)]
    result = evaluate_payload(LayoutDTO.model_validate(far))
    assert result.safety.window_distances[0].distance_m > before.safety.window_distances[0].distance_m
    assert result.safety.window_distances[0].penalty < before.safety.window_distances[0].penalty


def test_wall_alignment_rewards_face_not_corner_and_skips_window():
    r = room()
    aligned = build_furniture_from_placement('shelf', p('shelf', 4, .08))
    corner = build_furniture_from_placement('shelf', p('shelf', 4, .08, .5))
    assert alignment_cost(r, aligned) < alignment_cost(r, corner)
    assert alignment_cost(r, build_furniture_from_placement('table', p('table', 7, 7))) == 0
    r.windows = [WallOpening('window','Window',WallSide.BOTTOM,4,4,True)]
    assert alignment_cost(r, aligned) > 0
    for candidate in wall_placements(r, 'shelf', p('shelf',4,.08)):
        assert not (candidate.rotation == 0 and candidate.gy < .1 and candidate.gx < 8 and candidate.gx+4 > 4)


def test_unified_door_front_rejects_half_meter_depth():
    r = Room(12,12,doors=[WallOpening('d','Door',WallSide.LEFT,5,2,True)])
    with pytest.raises(ValueError, match='Door'):
        validate_layout(r, build_items_from_placements({'chair':p('chair',1.1,5.2)}))
    validate_layout(r, build_items_from_placements({'chair':p('chair',2,5.2)}))


def test_solver_keeps_best_initial_and_mitigation_and_safety_order():
    r = room()
    original = {'shelf':p('shelf',4,4,restraint='wall_bracket',installation_confirmed=True),
                'chair':p('chair',10,10,restraint='belt',installation_confirmed=True)}
    snapshot = deepcopy(original)
    solver = MCMCSolver()
    initial = solver._evaluate(r, original)
    results = solver.generate_layout_candidates(r, original, fixed_keys={'chair'}, sample_count=50,
                                               burn_in=49, sample_stride=10, rng_seed=4)
    assert results and all(s.valid for s in results)
    assert results[0].rank <= initial.rank
    assert [s.rank for s in results] == sorted(s.rank for s in results)
    for s in results:
        assert s.placements['chair'] == original['chair']
        moved = s.placements['shelf']
        assert moved.restraint == 'wall_bracket'
        if (moved.gx,moved.gy,moved.rotation) != (4,4,0):
            assert not moved.installation_confirmed
    assert original == snapshot


def test_unknown_defaults_and_invalid_confirmation():
    assert PlacementDTO(key='shelf').restraint == 'unknown'
    with pytest.raises(ValueError):
        PlacementDTO(key='shelf', installation_confirmed=True)


def test_opposite_falls_are_not_combined_into_an_impossible_barrier(monkeypatch):
    import layout_safety
    r = Room(6,6,doors=[WallOpening('d','Door',WallSide.BOTTOM,2,2,True)])
    items = build_items_from_placements({'chair':p('chair',2,4)})
    left = HazardScenario('s:left','s','fall','WEST',False,rect_polygon((0,2,3,3)))
    right = HazardScenario('s:right','s','fall','EAST',False,rect_polygon((3,2,6,3)))
    monkeypatch.setattr(layout_safety, 'build_hazard_scenarios', lambda room, items:[left,right])
    independent = assess_safety(r, items)
    assert independent.route_checks == 3
    assert independent.failed_route_checks == 0
    combined = replace(left, points=rect_polygon((0,2,6,3)))
    monkeypatch.setattr(layout_safety, 'build_hazard_scenarios', lambda room, items:[combined])
    assert assess_safety(r, items).failed_route_checks == 1


def test_no_available_access_side_is_reported():
    # A north-facing chair against the north wall has no departure cell.
    result = evaluate_layout(room(), {'chair':p('chair',10,15)}).score.safety
    assert any(i.scenario_id == 'baseline' and i.kind == 'escape_blocked' for i in result.issues)


def test_dense_empty_room_returns_unmet_improvement_not_invalid_geometry():
    r = Room(8,8,doors=[WallOpening('d','Door',WallSide.LEFT,5,2,True)])
    from design_models import FURNITURE_PRESETS
    placements = {key:PlacedFurniture(key,key) for key in FURNITURE_PRESETS}
    candidates = MCMCSolver().generate_layout_candidates(r,placements,sample_count=100,
                                                        burn_in=20,sample_stride=10,rng_seed=42)
    assert candidates
    assert all(c.valid and c.safety.status == 'unmet' for c in candidates)
    for c in candidates:
        validate_layout(r,build_items_from_placements(c.placements))
