from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

from models import(
    Furniture,
    FurniturePreset,
    PlacedFurniture,
    Room,
    get_rotated_size,
    rotate_direction,
    validate_layout,
)
from risk import evaluate_layout_risk

ProgressCallback = Callable[[int, int], None]

@dataclass
class LayoutSolution:
    placements: dict[str, PlacedFurniture]
    energy: float
    risk_score: float
    risk_breakdown: dict[str, float]
    violations: list[str]
    valid: bool

class SimulatesAnnealingGenerator:
    def __init__(self) -> None:
        self.initial_temperature = 5.0
        self.alpha = 0.98
        self.iterations = 250
        self.penalty_weight = 1000.0
        self.out_of_bounds_weight = 1000.0
        self.overlap_weight = 1000.0

    def generate_candidates(
        self,
        room: Room,
        presets: dict[str, FurniturePreset],
        candidate_count: int = 3,
        runs: int | None = None,
        iterations: int | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event = None,
    ) -> list[LayoutSolution]:
        runs = candidate_count if runs is None else runs
        iterations = self.iterations if iterations is None else iterations

        solutions: list[LayoutSolution] = []
        for run in range(runs):
            if cancel_event is not None and cancel_event.is_set():
                break

            solution = self._run_single(room, presets, iterations, cancel_event)
            solutions.append(solution)

            if progress_callback is not None:
                progress_callback(len(solutions), runs)

        solutions.sort(key=lambda sol: sol.energy)
        return solutions[:candidate_count]
    
    def _run_single(
            self,
            room: Room,
            presets: dict[str, FurniturePreset],
            iterations: int,
            cancel_event,
    ) -> LayoutSolution:
        current_placements = self._random_initial_placements(room, presets)
        current_solution = self._evaluate_solution(room, presets, current_placements)
        best_solution = current_solution
        temperature = self.initial_temperature

        for step in range(iterations):
            if cancel_event is not None and cancel_event.is_set():
                break

            neighbor_placements = self._neighbor(room, presets, current_placements)
            neighbor_solution = self._evaluate_solution(room, presets, neighbor_placements)
            delta = neighbor_solution.energy - current_solution.energy

            
