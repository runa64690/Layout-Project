from concurrent.futures import Future
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box

from api import create_app
from api_v2 import LayoutV2, RoomV2, evaluate_v2, optimize_v2
from design_models import build_items_from_placements, validate_layout
from polygon_room import polygon_parts
from wall_alignment import wall_placements


class ImmediateExecutor:
    def submit(self, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, **kwargs):
        pass


def room(points):
    return {"vertices": [{"id": f"v{i}", "x": x, "y": y} for i, (x, y) in enumerate(points)], "doors": [], "windows": []}


def layout(r=None, placements=None):
    return {"schema_version": 2, "revision": 9,
            "room": r or room([(0, 0), (4, 0), (4, 4), (0, 4)]),
            "placements": placements or [{"key": "chair", "x_m": 1, "y_m": 1, "placed": True}]}


@pytest.fixture
def client():
    with TestClient(create_app(ImmediateExecutor)) as c:
        yield c


PRESETS = json.loads((Path(__file__).parents[1] / "contracts" / "room-presets.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", PRESETS, ids=lambda c: f"{c['shape']}-{c['tatami']}")
def test_all_presets_have_exact_area(case):
    data = {"schema_version": 2, "room": {"vertices": case["vertices"]}, "placements": []}
    result = evaluate_v2(LayoutV2.model_validate(data))
    assert result.area_m2 == pytest.approx(case["tatami"]*1.62)
    assert result.tatami == pytest.approx(case["tatami"])


def test_catalog_units_and_evaluation(client):
    c = client.get("/api/v2/catalog").json()
    assert c["schema_version"] == 2
    assert c["furniture"][0]["width_m"] == c["furniture"][0]["gw"]*.25
    result = client.post("/api/v2/evaluate", json=layout())
    assert result.status_code == 200, result.text
    assert result.json()["area_m2"] == 16
    assert result.json()["revision"] == 9
    assert result.json()["evaluation_version"] == 3


@pytest.mark.parametrize("points", [
    [(0, 0), (2, 2), (0, 2), (2, 0)], [(0, 0), (2, 0), (2, 0), (0, 2)],
    [(0, 0), (2, 0), (1, 0), (1, 2), (0, 2)], [(0, 0), (2, 0), (2, 2), (1, 0), (0, 2)],
    [(0, 0), (1, 0), (2, 0)], [(0, 0), (17, 0), (17, 2), (0, 2)],
])
def test_invalid_rings_return_422(client, points):
    assert client.post("/api/v2/evaluate", json=layout(room(points))).status_code == 422


def test_notch_crossing_rejected_even_when_corners_inside(client):
    r = room([(0, 0), (3, 0), (3, 3), (1.6, 3), (1.6, 1.5), (1.4, 1.5), (1.4, 3), (0, 3)])
    data = layout(r, [{"key": "bed", "x_m": 1.5, "y_m": 1.5, "placed": True}])
    assert client.post("/api/v2/evaluate", json=data).status_code == 422


def test_negative_origin_diagonal_wall_and_clockwise_ring(client):
    for points in [[(-3, -2), (1, -2), (0, 1), (-3, 1)], [(-3, 1), (0, 1), (1, -2), (-3, -2)]]:
        r = room(points)
        r["doors"] = [{"key": "d", "edge_id": "v1", "offset_m": .5, "width_m": .8}]
        data = layout(r, [{"key": "chair", "x_m": -2, "y_m": -1, "placed": True, "rotation_deg": 23}])
        response = client.post("/api/v2/evaluate", json=data)
        assert response.status_code == 200, response.text
        domain = RoomV2.model_validate(r).to_domain()
        assert domain.door_front(domain.doors[0]).area*.25**2 == pytest.approx(.4)
        assert response.json()["safety"]["route_checks"] == 1


def test_opening_overlap_unknown_edge_and_overflow(client):
    for opening in [{"key": "d", "edge_id": "missing", "offset_m": 0, "width_m": .8},
                    {"key": "d", "edge_id": "v0", "offset_m": 3.5, "width_m": .8}]:
        data = layout();data["room"]["doors"] = [opening]
        assert client.post("/api/v2/evaluate", json=data).status_code == 422
    data = layout();data["room"]["doors"] = [{"key": "d", "edge_id": "v0", "offset_m": .5, "width_m": .8}]
    data["room"]["windows"] = [{"key": "w", "edge_id": "v0", "offset_m": .9, "width_m": .8}]
    assert client.post("/api/v2/evaluate", json=data).status_code == 422


def test_split_hazards_keep_one_scenario_and_count_routes_once(client):
    r = room([(0, 0), (3, 0), (3, 3), (1.6, 3), (1.6, 1), (1.4, 1), (1.4, 3), (0, 3)])
    r["doors"] = [{"key": "d", "edge_id": "v0", "offset_m": .1, "width_m": .8}]
    data = layout(r, [{"key": "shelf", "x_m": 1.5, "y_m": .75, "placed": True},
                      {"key": "chair", "x_m": .5, "y_m": 2, "placed": True}])
    result = client.post("/api/v2/evaluate", json=data)
    assert result.status_code == 200, result.text
    result = result.json()
    north = [r for r in result["regions"] if r["scenario_id"] == "shelf:NORTH"]
    assert len(north) == 2
    scenarios = {r["scenario_id"] for r in result["regions"] if r["scenario_id"]}
    assert result["safety"]["route_checks"] == len(scenarios)+1


def test_raster_never_walks_through_notch_or_unresolved_neck():
    r = RoomV2.model_validate(room([(0, 0), (1, 0), (1, .4), (2, .4), (2, 0), (3, 0), (3, 1), (2, 1), (2, .6), (1, .6), (1, 1), (0, 1)])).to_domain()
    from layout_safety import _reachable
    assert all(r.polygon.buffer(1e-6).covers(box(x,y,x+1,y+1)) for x,y in r.floor_cells)
    reachable = _reachable(r.floor_cells, {(0, 0)})
    assert (10, 2) not in reachable


def test_diagonal_wall_refinement_aligns_actual_wall():
    r = room([(0, 0), (4, 0), (3, 3), (0, 3)])
    domain, placements = LayoutV2.model_validate(layout(r, [{"key":"shelf","x_m":2,"y_m":1,"placed":True}])).to_domain()
    candidates = list(wall_placements(domain, "shelf", placements["shelf"]))
    assert any(abs(p.rotation-round(p.rotation))>.01 for p in candidates)
    assert any(domain.contains_footprint(build_items_from_placements({"shelf":p})[0].footprint) for p in candidates)


def test_exit_anchors_cannot_jump_over_hazard_in_front_of_door():
    data = room([(0,0),(4,0),(4,4),(0,4)])
    data["doors"] = [{"key":"d","edge_id":"v0","offset_m":1,"width_m":1}]
    domain = RoomV2.model_validate(data).to_domain()
    assert domain.door_anchor_cells()
    assert all(y == 0 for x, y in domain.door_anchor_cells())
    # Geometry uses cells: this blocks only the first 12.5cm, even though
    # deeper cells in the clearance zone are still unobstructed.
    blocked = box(3.9, 0, 8.1, .5)
    assert not domain.exit_cells(blocked)


def test_diagonal_exit_connectors_stay_inside_and_are_hazard_checked():
    data = room([(0,0),(4,0),(3,3),(0,3)])
    data["doors"] = [{"key":"d","edge_id":"v1","offset_m":.5,"width_m":.8}]
    domain = RoomV2.model_validate(data).to_domain()
    assert domain.door_connections
    for lines in domain.door_connections.values():
        assert all(domain.polygon.buffer(1e-6).covers(line) for line in lines)
    assert not domain.exit_cells(domain.door_front(domain.doors[0]))


def test_seeded_job_preserves_fixed_pose_and_all_candidates_fit(client):
    data=layout(room([(0,0),(4,0),(4,2),(2,2),(2,4),(0,4)]),[
        {"key":"chair","x_m":.5,"y_m":3,"rotation_deg":23,"placed":True},
        {"key":"table","placed":False}])
    body={"layout":data,"fixed_keys":["chair"],"sample_count":30,"burn_in":5,"sample_stride":5,"rng_seed":12,"candidate_count":2}
    before=deepcopy(body)
    created=client.post("/api/v2/optimization-jobs",json=body)
    assert created.status_code==202,created.text
    result=client.get("/api/v2/optimization-jobs/"+created.json()["id"]).json()
    assert result["status"]=="succeeded",result
    assert result["candidates"]
    assert result["candidates"]==optimize_v2(body)
    for candidate in result["candidates"]:
        fixed=next(p for p in candidate["placements"] if p["key"]=="chair")
        assert fixed["x_m"]==.5 and fixed["y_m"]==3 and fixed["rotation_deg"]==23
        room_domain,placements=LayoutV2.model_validate(data|{"placements":candidate["placements"]}).to_domain()
        validate_layout(room_domain,build_items_from_placements(placements))
    assert body==before


def test_real_v2_process_worker():
    body={"layout":layout(),"fixed_keys":["chair"],"sample_count":5,"burn_in":1,"sample_stride":1}
    with TestClient(create_app()) as client:
        created=client.post("/api/v2/optimization-jobs",json=body)
        assert created.status_code==202
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            result=client.get("/api/v2/optimization-jobs/"+created.json()["id"]).json()
            if result["status"] in {"failed","succeeded"}:break
            time.sleep(.05)
        assert result["status"]=="succeeded",result
