from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from design_models import (
    FURNITURE_PRESETS,
    PlacedFurniture,
    Room,
    clone_placements,
    get_rotated_size,
    build_items_from_placements, build_furniture_from_placement, validate_layout,
)
from layout_cost import evaluate_layout_from_placements
from layout_geometry import build_door_front_rect
from spatial_geometry import overlaps, rect_polygon, intersection_area
from layout_safety import SafetyAssessment
from wall_alignment import wall_placements


@dataclass
class LayoutSolution:
    placements: dict[str, PlacedFurniture]
    cost: float
    score_breakdown: dict[str, float]
    violations: list[str]
    accepted_steps: int
    source_sample_index: int
    safety: SafetyAssessment = field(default_factory=SafetyAssessment)
    natural_cost: float = 0.0

    @property
    def valid(self):
        return "invalid_layout" not in self.score_breakdown

    @property
    def rank(self):
        return (not self.valid, *self.safety.priority, self.natural_cost if self.valid else self.cost)


class MCMCSolver:
    def __init__(self, beta: float = 1.2, invalid_penalty: float = 1000000.0, *, continuous: bool = True) -> None:
        self.continuous = continuous
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

        #初期状態を作成,
        current = self._randomize_missing(room, clone_placements(placements), fixed, rng)
        current_solution = self._evaluate(room, current)
        # A failed greedy packing should not force the entire chain to start
        # with stacked furniture. Retry movable furniture; fixed poses survive.
        for _ in range(12):
            if current_solution.valid:
                break
            restart = clone_placements(placements)
            for key, p in restart.items():
                if key not in fixed:
                    p.placed = False
                    p.gx = p.gy = None
            restart = self._randomize_missing(room, restart, fixed, rng)
            alternative = self._evaluate(room, restart)
            if alternative.rank < current_solution.rank:
                current, current_solution = restart, alternative
        # A wall-oriented seed/refinement is outside the symmetric MCMC kernel.
        current_solution = self._refine_walls(room, current_solution, fixed)
        current = clone_placements(current_solution.placements)
        best = current_solution

        accepted_steps = 0
        samples: list[LayoutSolution] = []

        for step in range(sample_count):
            #近傍生成
            neighbor = self._propose_neighbor(room, current, fixed, rng)
            neighbor_solution = self._evaluate(room, neighbor)

            #現在の配置と候補配置について、差を計算。コストが下がればいい配置。コストが下がれば必ず採用される。悪い配置も一定の確率で採用することで、局所最適解から抜け出せる
            delta = neighbor_solution.cost - current_solution.cost

            if delta <= 0 or rng.random() < math.exp(-self.beta * delta):
                current = neighbor
                current_solution = neighbor_solution
                accepted_steps += 1
                current_solution.accepted_steps = accepted_steps
                current_solution.source_sample_index = step
                if current_solution.rank < best.rank:
                    best = current_solution

            if step >= burn_in and (step - burn_in) % sample_stride == 0:
                samples.append(
                    LayoutSolution(
                        placements=clone_placements(current),
                        cost=current_solution.cost,
                        score_breakdown=dict(current_solution.score_breakdown),
                        violations=list(current_solution.violations),
                        accepted_steps=accepted_steps,
                        source_sample_index=step,
                        safety=current_solution.safety,
                        natural_cost=current_solution.natural_cost,
                    )
                )

        samples.append(best)
        ranked = self._dedupe_by_signature(sorted((s for s in samples if s.valid), key=lambda s: s.rank))
        # Refine promising solutions only; always retain the originals.
        ranked += [self._refine_walls(room, s, fixed) for s in ranked[:candidate_count * 2]]
        ranked = self._dedupe_by_signature(sorted(ranked, key=lambda s: s.rank))
        selected = self._select_diverse_candidates(room, ranked, candidate_count, mmr_lambda)
        for solution in selected:
            for key, p in solution.placements.items():
                original = placements[key]
                if (p.gx, p.gy, p.rotation, p.placed) != (original.gx, original.gy, original.rotation, original.placed):
                    p.installation_confirmed = False
        return sorted(selected, key=lambda s: s.rank)

    def _refine_walls(self, room, solution, fixed):
        best = solution
        for key in solution.placements:
            if key in fixed:
                continue
            original = best.placements[key]
            if not original.placed:
                continue
            for placement in wall_placements(room, key, original, discrete=not self.continuous):
                candidate = clone_placements(best.placements)
                candidate[key] = placement
                evaluated = self._evaluate(room, candidate)
                if evaluated.rank < best.rank:
                    evaluated.accepted_steps = solution.accepted_steps
                    evaluated.source_sample_index = solution.source_sample_index
                    best = evaluated
        return best

    def _randomize_missing(
        self,
        room: Room,
        placements: dict[str, PlacedFurniture],
        fixed_keys: set[str],
        rng: random.Random,
    ) -> dict[str, PlacedFurniture]:
        order = sorted(placements, key=lambda k: (FURNITURE_PRESETS[k].ceiling_mounted,
                                                  -FURNITURE_PRESETS[k].gw*FURNITURE_PRESETS[k].gd))
        for key in order:
            placement = placements[key]
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
        if hasattr(room, "boundary"):
            # Try actual wall angles before grid seeds, including thin diagonal
            # rooms where no cardinal placement can fit. Always validate the
            # whole layout before accepting a seed.
            from dataclasses import replace
            seed = replace(placement, gx=room.grid_w/2-preset.gw/2,
                           gy=room.grid_h/2-preset.gd/2, placed=True)
            aligned = list(wall_placements(room, key, seed))
            rng.shuffle(aligned)
            for p in aligned:
                candidate = clone_placements(placements)
                candidate[key] = p
                try:
                    validate_layout(room, build_items_from_placements(candidate))
                except ValueError:
                    continue
                placement.gx, placement.gy, placement.rotation, placement.placed = p.gx, p.gy, p.rotation, True
                return
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
        candidate = clone_placements(placements)
        candidate[key].gx, candidate[key].gy, candidate[key].placed = gx, gy, True
        try:
            validate_layout(room, build_items_from_placements(candidate))
        except ValueError:
            return False
        item = build_furniture_from_placement(key, candidate[key])
        if not item.ceiling_mounted and not hasattr(room, "boundary"):
            for door in room.doors:
                rect = build_door_front_rect(room, door)
                if rect and overlaps(item.footprint, rect_polygon(rect)):
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

        #提案分布。ランダムに移動、回転、入れ替えのどれかを行う
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
            if not self.continuous:
                placement.rotation = (placement.rotation + rng.choice((1, 3))) % 4
                return proposal
            preset = FURNITURE_PRESETS[key]
            old_w, old_d = get_rotated_size(preset.gw, preset.gd, placement.rotation)
            angle_step = rng.choice((1/30, 1/3))
            placement.rotation = (placement.rotation + rng.uniform(-angle_step, angle_step)) % 4
            new_w, new_d = get_rotated_size(preset.gw, preset.gd, placement.rotation)
            if placement.gx is not None and placement.gy is not None:
                placement.gx += (old_w - new_w) / 2
                placement.gy += (old_d - new_d) / 2
            return proposal

        step_size = rng.choice((.2, 2)) if self.continuous else 2
        dx = rng.uniform(-step_size, step_size) if self.continuous else rng.randint(-2, 2)
        dy = rng.uniform(-step_size, step_size) if self.continuous else rng.randint(-2, 2)
        if placement.gx is None or placement.gy is None:
            placement.gx = 0
            placement.gy = 0
        placement.gx += dx
        placement.gy += dy
        return proposal

    def _evaluate(self, room: Room, placements: dict[str, PlacedFurniture]) -> LayoutSolution:
        try:

            #目的関数
            score = evaluate_layout_from_placements(room, placements)

            return LayoutSolution(
                placements=clone_placements(placements),
                cost=score.total, #家具配置のコスト
                score_breakdown=score.breakdown,
                violations=score.violations,
                accepted_steps=0,
                source_sample_index=0,
                safety=score.safety,
                natural_cost=score.natural_cost,
            )
        except ValueError as exc:

            #不正な家具には大きなペナルティ(大きなコスト)を与え、採用されずらくしている
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

        items = [build_furniture_from_placement(key, p) for key, p in placements.items()
                 if p.placed and p.gx is not None and p.gy is not None]
        for index, item in enumerate(items):
            if hasattr(room, "boundary"):
                from shapely.geometry import Polygon
                penalty += Polygon(item.footprint).difference(room.polygon).area * 100
            for other in items[index + 1:]:
                if item.ceiling_mounted == other.ceiling_mounted:
                    penalty += intersection_area(item.footprint, other.footprint) * 50.0
            if not item.ceiling_mounted:
                for door in room.doors:
                    if hasattr(room, "boundary"):
                        penalty += room.door_front(door).intersection(Polygon(item.footprint)).area * 150
                        continue
                    rect = build_door_front_rect(room, door)
                    if rect:
                        penalty += intersection_area(item.footprint, rect_polygon(rect)) * 150.0
        return penalty

    def _signature(self, placements: dict[str, PlacedFurniture]) -> tuple[tuple[str, float, float, float], ...]:
        signature: list[tuple[str, float, float, float]] = []
        for key in sorted(placements):
            placement = placements[key]
            signature.append((key, placement.gx if placement.gx is not None else -1, placement.gy if placement.gy is not None else -1, placement.rotation))
        return tuple(signature)

    def _dedupe_by_signature(self, samples: list[LayoutSolution]) -> list[LayoutSolution]:
        deduped: list[LayoutSolution] = []
        seen: set[tuple[tuple[str, float, float, float], ...]] = set()
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
                # Diversity can choose only within the best remaining safety tier.
                if candidate.safety.priority != min(s.safety.priority for s in remaining):
                    continue
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
