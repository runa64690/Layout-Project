"""Run: python -m uvicorn api:app --app-dir src --host 127.0.0.1 --port 8000.

Single API process, bounded process pool. Job state is ephemeral and expires after
one hour; deploy with --workers 1. A durable shared queue is a future extension.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api_contract import (
    LayoutDTO, OptimizationDTO, EvaluationDTO, JobDTO,
    catalog_payload, evaluate_payload, optimize_payload,
)
from design_models import build_items_from_placements, validate_layout

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    revision: int
    future: object
    completed_at: float | None = None


class JobStore:
    def __init__(self, executor, capacity=32, ttl_seconds=3600):
        self.executor = executor
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self.records: dict[str, JobRecord] = {}
        self.lock = Lock()

    def _prune(self):
        now = time.monotonic()
        for key, record in list(self.records.items()):
            if record.future.done() and record.completed_at is None:
                record.completed_at = now
            if record.completed_at is not None and now - record.completed_at >= self.ttl_seconds:
                del self.records[key]

    def submit(self, request: OptimizationDTO):
        with self.lock:
            self._prune()
            if len(self.records) >= self.capacity:
                completed = [(key, record) for key, record in self.records.items() if record.completed_at is not None]
                if completed:
                    oldest = min(completed, key=lambda pair: pair[1].completed_at)[0]
                    del self.records[oldest]
                else:
                    raise HTTPException(503, "Job capacity reached; retry later", headers={"Retry-After": "30"})
            job_id = uuid4().hex
            try:
                future = self.executor.submit(optimize_payload, request.model_dump())
            except RuntimeError as exc:
                logger.exception("Cannot submit optimization")
                raise HTTPException(503, "Optimization worker unavailable") from exc
            self.records[job_id] = JobRecord(request.layout.revision, future)
            return JobDTO(id=job_id, revision=request.layout.revision, status="queued")

    def get(self, job_id):
        with self.lock:
            self._prune()
            record = self.records.get(job_id)
            if record is None:
                raise HTTPException(404, "Job not found or expired; submit again")
            future = record.future
            result = JobDTO(id=job_id, revision=record.revision, status="running" if future.running() else "queued")
            if future.done():
                try:
                    result = JobDTO(id=job_id, revision=record.revision, status="succeeded", candidates=future.result())
                except Exception:
                    logger.exception("Optimization job %s failed", job_id)
                    result.status = "failed"
                    result.error = "Candidate generation failed; edit the layout or retry."
            return result


def create_app(executor_factory=None, *, cors_origins=None):
    @asynccontextmanager
    async def lifespan(application):
        executor = (executor_factory() if executor_factory else ProcessPoolExecutor(
            max_workers=2, mp_context=multiprocessing.get_context("spawn")))
        application.state.jobs = JobStore(executor)
        try:
            yield
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    application = FastAPI(title="Furniture Layout API", version="1.0.0", lifespan=lifespan)
    origins = cors_origins if cors_origins is not None else [
        s.strip() for s in os.getenv("LAYOUT_CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",") if s.strip()
    ]
    application.add_middleware(CORSMiddleware, allow_origins=origins,
                               allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @application.get("/api/v1/catalog")
    def catalog():
        return catalog_payload()

    @application.post("/api/v1/evaluate", response_model=EvaluationDTO)
    def evaluate(layout: LayoutDTO):
        try:
            return evaluate_payload(layout)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.post("/api/v1/optimization-jobs", response_model=JobDTO, status_code=202)
    def optimize(request: OptimizationDTO):
        room, placements = request.layout.to_domain()
        try:
            # Movable furniture may be invalid: the optimizer can repair it.
            fixed = {key: placements[key] for key in request.fixed_keys}
            validate_layout(room, build_items_from_placements(fixed))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return application.state.jobs.submit(request)

    @application.get("/api/v1/optimization-jobs/{job_id}", response_model=JobDTO)
    def job(job_id: str):
        return application.state.jobs.get(job_id)

    return application


app = create_app()
