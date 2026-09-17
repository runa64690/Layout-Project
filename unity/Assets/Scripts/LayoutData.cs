using System;
using UnityEngine;

namespace FurnitureLayout
{
    [Serializable] public class ClearanceRule { public int min_cells; public string mode; }
    [Serializable] public class PairwiseRule { public string other_key; public int min_distance_cells, max_distance_cells; }
    [Serializable] public class FurnitureDefinition
    {
        public string key, label, furniture_type, fall_dir, pillow_side, model_id;
        public int gw, gd, h_cell;
        public bool conversation_seat, ceiling_mounted;
        public ClearanceRule clearance;
        public PairwiseRule[] pairwise_rules;
    }
    [Serializable] public class Catalog
    {
        public int schema_version;
        public float cell_size_m;
        public FurnitureDefinition[] furniture;
        public FurnitureDefinition Find(string key) => Array.Find(furniture, p => p.key == key);
    }
    [Serializable] public class Opening
    {
        public string key, label, wall;
        public int offset, length = 2;
        public bool placed = true;
    }
    [Serializable] public class RoomData
    {
        public int grid_w = 12, grid_h = 12;
        public float ceiling_height_m = 2.5f;
        public Opening[] doors = { new Opening { key = "door_1", label = "Door", wall = "LEFT", offset = 5 } };
        public Opening[] windows = { new Opening { key = "window_1", label = "Window", wall = "TOP", offset = 5 } };
    }
    [Serializable] public class Placement
    {
        public string key;
        public int gx, gy, rotation;
        public bool placed;
        public Placement Copy() => (Placement)MemberwiseClone();
    }
    [Serializable] public class LayoutData
    {
        public int schema_version = 1, revision;
        public RoomData room = new RoomData();
        public Placement[] placements;
        public LayoutData Copy() => JsonUtility.FromJson<LayoutData>(JsonUtility.ToJson(this));
    }
    [Serializable] public class OptimizationRequest
    {
        public LayoutData layout;
        public string[] fixed_keys;
        public int candidate_count = 3, sample_count = 900, burn_in = 250, sample_stride = 15, rng_seed = 42;
    }
    [Serializable] public class ScoreTerm { public string name; public float value; }
    [Serializable] public class Region { public string kind, key; public int x0, y0, x1, y1; }
    [Serializable] public class Evaluation
    {
        public int schema_version, revision, fall_overlap_cells;
        public float total;
        public ScoreTerm[] breakdown;
        public string[] violations;
        public Region[] regions;
    }
    [Serializable] public class Candidate
    {
        public Placement[] placements;
        public float cost;
        public ScoreTerm[] score_breakdown;
        public string[] violations;
        public bool valid;
        public int accepted_steps, source_sample_index;
    }
    [Serializable] public class OptimizationJob
    {
        public int schema_version, revision;
        public string id, status, error;
        public Candidate[] candidates;
    }

    // All grid-to-world conversion lives here. Rotation is clockwise from +Z.
    public static class GridCoordinates
    {
        public static Vector2Int Size(FurnitureDefinition d, int rotation) =>
            rotation % 2 == 0 ? new Vector2Int(d.gw, d.gd) : new Vector2Int(d.gd, d.gw);

        public static Vector3 BottomCenter(Placement p, FurnitureDefinition d, RoomData room, float cell)
        {
            var size = Size(d, p.rotation);
            return new Vector3((p.gx + size.x / 2f) * cell,
                d.ceiling_mounted ? room.ceiling_height_m - d.h_cell * cell : 0,
                (p.gy + size.y / 2f) * cell);
        }
        public static Quaternion Rotation(int quarters) => Quaternion.Euler(0, quarters * 90, 0);
        public static Vector2Int Cell(Vector3 world, float cell) =>
            new Vector2Int(Mathf.FloorToInt(world.x / cell), Mathf.FloorToInt(world.z / cell));
    }
}
