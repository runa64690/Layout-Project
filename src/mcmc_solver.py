from __future__ import annotations

import math
import random
from dataclasses import dataclass

from design_models import (
    FURNITURE_PRESETS,
    FurniturePreset,
    PlacedFurniture,
    Room,
    clone_placements,
    get_rotated_size,
)
from layout_cost import LayoutScore, evaluate_layout_from_placements


@dataclass
class LayoutSolution:
    placements: dict[str, PlacedFurniture]
    cost: float
    score_breakdown: dict[str, float]
    violations: list[str]
    accepted_steps: int
    source_sample_index: int


class MCMCSolver:
    def __init__(self, beta: float = 1.2, invalid_penalty: float = 1000.0) -> None:
        self.beta = beta
        self.invalid_penalty = invalid_penalty

    def generate_layout_candidates(
        self,
        room: Room,
        placements: dict[str, PlacedFurniture],
        fixed_keys: set[str] | None = None,
        candidate_count: int = 3,
        sample_count: int = 600,
        burn_in: int = 150,
        sample_stride: int = 12,
        mmr_lambda: float = 0.75,
        rng_seed: int | None = None,
    ) -> list[LayoutSolution]:
        rng = random.Random(rng_seed)
        fixed = set() if fixed_keys is None else set(fixed_keys)
        current = self._randomize_missing(room, clone_placements(placements), fixed, rng)
        current_solution = self._evaluate(room, current)
        accepted_steps = 0
        samples: list[LayoutSolution] = []

        for step in range(sample_count):
            neighbor = self._propose_neighbor(room, current, fixed, rng)
            neighbor_solution = self._evaluate(room, neighbor)
            delta = neighbor_solution.cost - current_solution.cost

            if delta <= 0 or rng.random() < math.exp(-self.beta * delta):
                current = neighbor
                current_solution = neighbor_solution
                accepted_steps += 1

            if step >= burn_in and (step - burn_in) % sample_stride == 0:
                samples.append(
                    LayoutSolution(
                        placements=clone_placements(current),
                        cost=current_solution.cost,
                        score_breakdown=dict(current_solution.score_breakdown),
                        violations=list(current_solution.violations),
                        accepted_steps=accepted_steps,
                        source_sample_index=step,
                    )
                )

        ranked = self._dedupe_by_signature(sorted(samples, key=lambda sample: sample.cost))
        return self._select_diverse_candidates(room, ranked, candidate_count, mmr_lambda)

    def _randomize_missing(
        self,
        room: Room,
        placements: dict[str, PlacedFurniture],
        fixed_keys: set[str],
        rng: random.Random,
    ) -> dict[str, PlacedFurniture]:
        for key, placement in placements.items():
            if key in fixed_keys and placement.placed:
                continue
            if placement.placed and placement.gx is not None and placement.gy is not None:
                continue
            self._assign_random_location(room, key, placement, placements, rng)
        return placements

    def _assign_random_location(
        self,
        room: Room,
        key: str,
        placement: PlacedFurniture,
        placements: dict[str, PlacedFurniture],
        rng: random.Random,
    ) -> None:
        preset = FURNITURE_PRESETS[key]
        candidates = [(gx, gy, rotation) for rotation in range(4) for gx in range(room.grid_w) for gy in range(room.grid_h)]
        rng.shuffle(candidates)
        for gx, gy, rotation in candidates:
            placement.rotation = rotation
            if self._can_place(room, key, gx, gy, placements):
                placement.gx = gx
                placement.gy = gy
                placement.placed = True
                return

        gw, gd = get_rotated_size(preset.gw, preset.gd, 0)
        placement.gx = max(0, min(room.grid_w - gw, 0))
        placement.gy = max(0, min(room.grid_h - gd, 0))
        placement.rotation = 0
        placement.placed = True

    def _can_place(
        self,
        room: Room,
        key: str,
        gx: int,
        gy: int,
        placements: dict[str, PlacedFurniture],
    ) -> bool:
        preset = FURNITURE_PRESETS[key]
        rotation = placements[key].rotation
        gw, gd = get_rotated_size(preset.gw, preset.gd, rotation)
        if gx < 0 or gy < 0 or gx + gw > room.grid_w or gy + gd > room.grid_h:
            return False
        for anchor_x, anchor_y in room.door_anchor_cells():
            if gx <= anchor_x < gx + gw and gy <= anchor_y < gy + gd:
                return False
        for other_key, other in placements.items():
            if other_key == key or not other.placed or other.gx is None or other.gy is None:
                continue
            other_preset = FURNITURE_PRESETS[other_key]
            other_gw, other_gd = get_rotated_size(other_preset.gw, other_preset.gd, other.rotation)
            if not (
                gx + gw <= other.gx
                or other.gx + other_gw <= gx
                or gy + gd <= other.gy
                or other.gy + other_gd <= gy
            ):
                return False
        return True

    def _propose_neighbor(
        self,
        room: Room,
        placements: dict[str, PlacedFurniture],
        fixed_keys: set[str],
        rng: random.Random,
    ) -> dict[str, PlacedFurniture]:
        movable = [key for key in placements if key not in fixed_keys]
        if not movable:
            return clone_placements(placements)

        proposal = clone_placements(placements)
        move_type = rng.choice(("translate", "rotate", "swap"))
        if move_type == "swap" and len(movable) >= 2:
            left_key, right_key = rng.sample(movable, 2)
            left = proposal[left_key]
            right = proposal[right_key]
            left.gx, right.gx = right.gx, left.gx
            left.gy, right.gy = right.gy, left.gy
            left.rotation, right.rotation = right.rotation, left.rotation
            return proposal

        key = rng.choice(movable)
        placement = proposal[key]
        if move_type == "rotate":
            placement.rotation = (placement.rotation + rng.choice((1, 3))) % 4
            return proposal

        dx = rng.randint(-2, 2)
        dy = rng.randint(-2, 2)
        if placement.gx is None or placement.gy is None:
            placement.gx = 0
            placement.gy = 0
        placement.gx += dx
        placement.gy += dy
        return proposal

    def _evaluate(self, room: Room, placements: dict[str, PlacedFurniture]) -> LayoutSolution:
        try:
            score = evaluate_layout_from_placements(room, placements)
            return LayoutSolution(
                placements=clone_placements(placements),
                cost=score.total,
                score_breakdown=score.breakdown,
                violations=score.violations,
                accepted_steps=0,
                source_sample_index=0,
            )
        except ValueError as exc:
            penalty = self.invalid_penalty + self._soft_geometry_penalty(room, placements)
            return LayoutSolution(
                placements=clone_placements(placements),
                cost=penalty,
                score_breakdown={"invalid_layout": penalty},
                violations=[str(exc)],
                accepted_steps=0,
                source_sample_index=0,
            )

    def _soft_geometry_penalty(self, room: Room, placements: dict[str, PlacedFurniture]) -> float:
        penalty = 0.0
        occupied: list[tuple[str, int, int, int, int]] = []
        for key, placement in placements.items():
            if placement.gx is None or placement.gy is None:
                penalty += 250.0
                continue
            preset = FURNITURE_PRESETS[key]
            gw, gd = get_rotated_size(preset.gw, preset.gd, placement.rotation)
            if placement.gx < 0:
                penalty += abs(placement.gx) * 25.0
            if placement.gy < 0:
                penalty += abs(placement.gy) * 25.0
            if placement.gx + gw > room.grid_w:
                penalty += (placement.gx + gw - room.grid_w) * 25.0
            if placement.gy + gd > room.grid_h:
                penalty += (placement.gy + gd - room.grid_h) * 25.0
            occupied.append((key, placement.gx, placement.gy, gw, gd))

        for index, (_, ax, ay, aw, ad) in enumerate(occupied):
            for _, bx, by, bw, bd in occupied[index + 1 :]:
                if not (ax + aw <= bx or bx + bw <= ax or ay + ad <= by or by + bd <= ay):
                    overlap_w = min(ax + aw, bx + bw) - max(ax, bx)
                    overlap_h = min(ay + ad, by + bd) - max(ay, by)
                    penalty += max(1, overlap_w * overlap_h) * 50.0
        for door_x, door_y in room.door_anchor_cells():
            for _, ax, ay, aw, ad in occupied:
                if ax <= door_x < ax + aw and ay <= door_y < ay + ad:
                    penalty += 150.0
        return penalty

    def _signature(self, placements: dict[str, PlacedFurniture]) -> tuple[tuple[str, int, int, int], ...]:
        signature: list[tuple[str, int, int, int]] = []
        for key in sorted(placements):
            placement = placements[key]
            signature.append((key, placement.gx or -1, placement.gy or -1, placement.rotation))
        return tuple(signature)

    def _dedupe_by_signature(self, samples: list[LayoutSolution]) -> list[LayoutSolution]:
        deduped: list[LayoutSolution] = []
        seen: set[tuple[tuple[str, int, int, int], ...]] = set()
        for sample in samples:
            signature = self._signature(sample.placements)
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(sample)
        return deduped

    def _layout_distance(
        self,
        room: Room,
        left: dict[str, PlacedFurniture],
        right: dict[str, PlacedFurniture],
    ) -> float:
        total = 0.0
        for key in left:
            a = left[key]
            b = right[key]
            if a.gx is None or a.gy is None or b.gx is None or b.gy is None:
                total += 1.0
                continue
            total += abs(a.gx - b.gx) / max(1, room.grid_w)
            total += abs(a.gy - b.gy) / max(1, room.grid_h)
            rotation_delta = min((a.rotation - b.rotation) % 4, (b.rotation - a.rotation) % 4)
            total += rotation_delta / 4.0
        return total / max(1, len(left))

    def _select_diverse_candidates(
        self,
        room: Room,
        ranked: list[LayoutSolution],
        candidate_count: int,
        mmr_lambda: float,
    ) -> list[LayoutSolution]:
        if len(ranked) <= candidate_count:
            return ranked

        pool = ranked[: max(candidate_count * 8, candidate_count)]
        selected = [pool[0]]
        remaining = pool[1:]
        max_cost = max(sample.cost for sample in pool) or 1.0

        while remaining and len(selected) < candidate_count:
            best_index = 0
            best_score = float("-inf")
            for index, candidate in enumerate(remaining):
                relevance = 1.0 - (candidate.cost / max_cost)
                diversity = min(
                    self._layout_distance(room, candidate.placements, chosen.placements)
                    for chosen in selected
                )
                mmr_score = mmr_lambda * relevance + (1.0 - mmr_lambda) * diversity
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_index = index
            selected.append(remaining.pop(best_index))
        return selected
