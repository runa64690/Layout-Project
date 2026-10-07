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
        public bool continuous_placement;
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
        public float gx, gy, rotation;
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
    [Serializable] public class RegionPoint { public float x, y; }
    [Serializable] public class Region { public string kind, key; public float x0, y0, x1, y1; public RegionPoint[] points; }
    [Serializable] public class Evaluation
    {
        public int schema_version, revision;
        public float fall_overlap_cells;
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
        public const float Epsilon = 1e-6f;
        public static Vector2 Size(FurnitureDefinition d, float rotation)
        {
            float angle = rotation * Mathf.PI / 2;
            float c = Mathf.Abs(Mathf.Cos(angle)), s = Mathf.Abs(Mathf.Sin(angle));
            return new Vector2(d.gw*c + d.gd*s, d.gw*s + d.gd*c);
        }
        // gx/gy are the lower bounds of the rotated footprint, not the pointer position.
        public static bool ClampToRoom(Placement p, FurnitureDefinition d, RoomData room, Vector2 position)
        {
            if (!Finite(position.x) || !Finite(position.y) || !Finite(p.rotation)) return false;
            var size=Size(d,p.rotation);
            float maxX=room.grid_w-size.x, maxY=room.grid_h-size.y;
            if (maxX < -Epsilon || maxY < -Epsilon) return false;
            p.gx=Mathf.Clamp(position.x,0,Mathf.Max(0,maxX));
            p.gy=Mathf.Clamp(position.y,0,Mathf.Max(0,maxY));
            return true;
        }
        public static Vector2[] Corners(Placement p, FurnitureDefinition d)
        {
            var size = Size(d,p.rotation);
            var center = new Vector2(p.gx,p.gy) + size/2;
            float angle = p.rotation*Mathf.PI/2, c = Mathf.Cos(angle), s = Mathf.Sin(angle);
            var local = new[] { new Vector2(-d.gw/2f,-d.gd/2f), new Vector2(d.gw/2f,-d.gd/2f),
                new Vector2(d.gw/2f,d.gd/2f), new Vector2(-d.gw/2f,d.gd/2f) };
            return Array.ConvertAll(local, v => center + new Vector2(c*v.x+s*v.y,-s*v.x+c*v.y));
        }
        public static Vector2[] Corners(RectInt r) => new[] {
            new Vector2(r.xMin,r.yMin), new Vector2(r.xMax,r.yMin),
            new Vector2(r.xMax,r.yMax), new Vector2(r.xMin,r.yMax) };
        public static bool Overlaps(Vector2[] a, Vector2[] b)
        {
            foreach (var polygon in new[] {a,b})
                for (int i=0; i<polygon.Length; i++)
                {
                    var edge=polygon[(i+1)%polygon.Length]-polygon[i];
                    var axis=new Vector2(-edge.y,edge.x).normalized;
                    float amin=float.PositiveInfinity, amax=float.NegativeInfinity;
                    float bmin=float.PositiveInfinity, bmax=float.NegativeInfinity;
                    foreach (var v in a) { float t=Vector2.Dot(v,axis); amin=Mathf.Min(amin,t); amax=Mathf.Max(amax,t); }
                    foreach (var v in b) { float t=Vector2.Dot(v,axis); bmin=Mathf.Min(bmin,t); bmax=Mathf.Max(bmax,t); }
                    if (Mathf.Min(amax,bmax)-Mathf.Max(amin,bmin)<=Epsilon) return false;
                }
            return true;
        }
        public static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);

        public static Vector3 BottomCenter(Placement p, FurnitureDefinition d, RoomData room, float cell)
        {
            var size = Size(d, p.rotation);
            return new Vector3((p.gx + size.x / 2f) * cell,
                d.ceiling_mounted ? room.ceiling_height_m - d.h_cell * cell : 0,
                (p.gy + size.y / 2f) * cell);
        }
        public static Quaternion Rotation(float quarters) => Quaternion.Euler(0, quarters * 90, 0);
        public static Vector2 Cell(Vector3 world, float cell) =>
            new Vector2(world.x / cell, world.z / cell);
    }
}
