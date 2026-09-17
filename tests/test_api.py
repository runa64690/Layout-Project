from concurrent.futures import Future
from copy import deepcopy
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import create_app, JobStore
from api_contract import LayoutDTO, OptimizationDTO, optimize_payload
from design_models import FURNITURE_PRESETS, build_items_from_placements
from layout_cost import evaluate_layout_cost, total_fall_hazard_overlap_cells
from layout_service import evaluate_layout
from mcmc_solver import MCMCSolver


class ImmediateExecutor:
    def submit(self, func, *args):
        future = Future()
        try:
            future.set_result(func(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, **kwargs):
        pass


@pytest.fixture
def client():
    with TestClient(create_app(ImmediateExecutor, cors_origins=["https://layout.example"])) as client:
        yield client


@pytest.fixture
def layout():
    return {
        "schema_version": 1, "revision": 7,
        "room": {"grid_w": 16, "grid_h": 16, "ceiling_height_m": 2.5,
                 "doors": [{"key": "door_1", "wall": "LEFT", "offset": 5, "length": 2}],
                 "windows": [{"key": "window_1", "wall": "TOP", "offset": 5, "length": 2}]},
        "placements": [
            {"key": "shelf", "gx": 10, "gy": 10, "rotation": 0, "placed": True},
            {"key": "bed", "gx": 3, "gy": 8, "rotation": 0, "placed": True},
            {"key": "table", "gx": 8, "gy": 3, "rotation": 0, "placed": True},
            {"key": "tv_unit", "gx": 12, "gy": 3, "rotation": 0, "placed": True},
            {"key": "chair", "gx": 6, "gy": 3, "rotation": 0, "placed": True},
            {"key": "ceiling_light", "gx": 8, "gy": 3, "rotation": 0, "placed": True},
        ],
    }


def test_catalog_has_authoritative_rules_and_models(client):
    response = client.get("/api/v1/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["cell_size_m"] == .25
    for definition in data["furniture"]:
        preset = FURNITURE_PRESETS[definition["key"]]
        assert definition["gw"] == preset.gw
        assert definition["model_id"] == preset.key
        assert definition["ceiling_mounted"] == preset.ceiling_mounted
    assert next(d for d in data["furniture"] if d["key"] == "tv_unit")["pairwise_rules"][0]["other_key"] == "table"


@pytest.mark.parametrize("rotation", range(4))
@pytest.mark.parametrize("wall", ["LEFT", "RIGHT", "TOP", "BOTTOM"])
def test_evaluation_matches_core_and_ui_service(client, layout, rotation, wall):
    layout["placements"][0]["rotation"] = rotation
    layout["room"]["doors"][0]["wall"] = wall
    layout["room"]["windows"] = []
    request = LayoutDTO.model_validate(layout)
    room, placements = request.to_domain()
    items = build_items_from_placements(placements)
    expected = evaluate_layout_cost(room, items)
    ui_result = evaluate_layout(room, placements)
    response = client.post("/api/v1/evaluate", json=layout)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["revision"] == 7
    assert data["total"] == expected.total == ui_result.score.total
    assert {t["name"]: t["value"] for t in data["breakdown"]} == expected.breakdown
    assert data["violations"] == expected.violations
    assert data["fall_overlap_cells"] == total_fall_hazard_overlap_cells(items)
    assert any(r["kind"] == "door_front" for r in data["regions"])


def test_no_exit_and_ceiling_overlap_do_not_crash(client, layout):
    layout["room"]["doors"] = []
    assert client.post("/api/v1/evaluate", json=layout).status_code == 200
    layout["placements"][-1]["key"] = "chair"
    assert client.post("/api/v1/evaluate", json=layout).status_code == 422


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema_version=2),
    lambda d: d["room"].update(grid_w=100000),
    lambda d: d["room"].update(grid_w=16.5),
    lambda d: d["room"]["doors"][0].update(offset=16),
    lambda d: d["room"]["windows"][0].update(wall="LEFT"),
    lambda d: d["placements"][0].update(key="unknown"),
    lambda d: d["placements"][0].update(rotation=4),
    lambda d: d["placements"][0].update(gx=-1),
    lambda d: d["placements"][0].update(gx=3, gy=8),
    lambda d: d["placements"][0].update(placed=False),
    lambda d: d["placements"][0].update(gx=0, gy=5),
    lambda d: d["placements"][0].update(model_id="visual-only"),
])
def test_invalid_inputs_return_422(client, layout, change):
    change(layout)
    assert client.post("/api/v1/evaluate", json=layout).status_code == 422


def search_request(layout):
    return {"layout": layout, "fixed_keys": ["bed"], "candidate_count": 3,
            "sample_count": 70, "burn_in": 15, "sample_stride": 5, "rng_seed": 42}


def test_seeded_job_matches_direct_solver_and_preserves_input(client, layout):
    body = search_request(layout)
    before = deepcopy(body)
    request = OptimizationDTO.model_validate(body)
    room, placements = request.layout.to_domain()
    expected = MCMCSolver().generate_layout_candidates(room, placements, fixed_keys={"bed"},
                candidate_count=3, sample_count=70, burn_in=15, sample_stride=5, rng_seed=42)
    response = client.post("/api/v1/optimization-jobs", json=body)
    assert response.status_code == 202
    job = client.get("/api/v1/optimization-jobs/" + response.json()["id"]).json()
    assert job["status"] == "succeeded"
    assert job["revision"] == layout["revision"]
    assert len(job["candidates"]) == len(expected)
    for actual, target in zip(job["candidates"], expected):
        assert actual["cost"] == target.cost
        assert actual["accepted_steps"] == target.accepted_steps
        assert {t["name"]: t["value"] for t in actual["score_breakdown"]} == target.score_breakdown
        for p in actual["placements"]:
            t = target.placements[p["key"]]
            assert (p["gx"], p["gy"], p["rotation"]) == (t.gx, t.gy, t.rotation)
            if p["key"] == "bed":
                assert p == layout["placements"][1]
    assert before == body


def test_real_spawn_worker_and_polling(layout):
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/optimization-jobs", json=search_request(layout))
        assert response.status_code == 202
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = client.get("/api/v1/optimization-jobs/" + response.json()["id"]).json()
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(.05)
        assert job["status"] == "succeeded", job
        assert job["candidates"] == optimize_payload(search_request(layout))


@pytest.mark.parametrize("updates", [
    {"burn_in": 100}, {"sample_count": 999999}, {"fixed_keys": ["missing"]},
    {"fixed_keys": ["bed", "bed"]}, {"rng_seed": -1},
])
def test_invalid_search_options(client, layout, updates):
    body = search_request(layout) | updates
    assert client.post("/api/v1/optimization-jobs", json=body).status_code == 422


def test_fixed_invalid_geometry_rejected(client, layout):
    layout["placements"][1]["gx"] = -1
    assert client.post("/api/v1/optimization-jobs", json=search_request(layout)).status_code == 422


def test_failure_and_unknown_job_do_not_return_success(layout):
    class FailedExecutor(ImmediateExecutor):
        def submit(self, *args):
            future = Future()
            future.set_exception(RuntimeError("private worker details"))
            return future
    with TestClient(create_app(FailedExecutor)) as client:
        created = client.post("/api/v1/optimization-jobs", json=search_request(layout)).json()
        result = client.get("/api/v1/optimization-jobs/" + created["id"]).json()
        assert result["status"] == "failed"
        assert "private" not in result["error"]
        assert client.get("/api/v1/optimization-jobs/missing").status_code == 404


def test_capacity_and_expiry(layout):
    class PendingExecutor:
        def submit(self, *args):
            return Future()
    request = OptimizationDTO.model_validate(search_request(layout))
    store = JobStore(PendingExecutor(), capacity=1, ttl_seconds=0)
    job = store.submit(request)
    with pytest.raises(HTTPException) as exc:
        store.submit(request)
    assert exc.value.status_code == 503
    store.records[job.id].future.set_result([])
    with pytest.raises(HTTPException) as exc:
        store.get(job.id)
    assert exc.value.status_code == 404
    assert store.submit(request).id != job.id


def test_cors(client):
    headers = {"Origin": "https://layout.example", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    response = client.options("/api/v1/evaluate", headers=headers)
    assert response.headers["access-control-allow-origin"] == "https://layout.example"
    headers["Origin"] = "https://unlisted.example"
    assert client.options("/api/v1/evaluate", headers=headers).status_code == 400


def test_completed_jobs_can_be_evicted_without_blocking_new_work(layout):
    store = JobStore(ImmediateExecutor(), capacity=1)
    request = OptimizationDTO.model_validate(search_request(layout))
    first = store.submit(request)
    second = store.submit(request)
    assert first.id != second.id
    assert store.get(second.id).status == "succeeded"
    with pytest.raises(HTTPException) as exc:
        store.get(first.id)
    assert exc.value.status_code == 404


def test_missing_fixed_placement_is_rejected(client, layout):
    layout["placements"][1]["placed"] = False
    assert client.post("/api/v1/optimization-jobs", json=search_request(layout)).status_code == 422


def test_empty_initial_layout_can_generate(client, layout):
    for p in layout["placements"]:
        p["placed"] = False
    request = search_request(layout) | {"fixed_keys": []}
    created = client.post("/api/v1/optimization-jobs", json=request)
    assert created.status_code == 202
    job = client.get("/api/v1/optimization-jobs/" + created.json()["id"]).json()
    assert job["status"] == "succeeded"
    assert any(candidate["valid"] for candidate in job["candidates"])


def test_existing_tkinter_imports():
    import layout_app
    assert layout_app.evaluate_layout is evaluate_layout
