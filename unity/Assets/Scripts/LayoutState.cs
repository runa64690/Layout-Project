using System;
using System.Collections.Generic;
using UnityEngine;

namespace FurnitureLayout
{
    // No GameObjects, networking or camera state in the editable document.
    public sealed class LayoutState
    {
        public readonly Catalog Catalog;
        public LayoutData Data { get; private set; }
        public readonly HashSet<string> FixedKeys = new HashSet<string>();
        public event Action Changed;
        public LayoutState(Catalog catalog)
        {
            Catalog = catalog;
            Data = new LayoutData { placements = Array.ConvertAll(catalog.furniture, d => new Placement { key = d.key }) };
        }
        public Placement Find(string key) => Array.Find(Data.placements, p => p.key == key);
        public void Touch() { Data.revision++; Changed?.Invoke(); }
        public void SetFixed(string key, bool value)
        {
            if (value && Find(key).placed) FixedKeys.Add(key); else FixedKeys.Remove(key);
            Touch();
        }
        public bool Place(Placement candidate, bool enforceDoorFront = true)
        {
            if (!CanPlace(candidate, Data.placements, enforceDoorFront)) return false;
            int index = Array.FindIndex(Data.placements, p => p.key == candidate.key);
            Data.placements[index] = candidate.Copy();
            Touch();
            return true;
        }
        public void Remove(string key)
        {
            Find(key).placed = false;
            FixedKeys.Remove(key);
            Touch();
        }
        public bool Apply(Candidate candidate)
        {
            if (!candidate.valid || candidate.placements == null || candidate.placements.Length != Data.placements.Length) return false;
            var keys = new HashSet<string>();
            foreach (var p in candidate.placements)
                if (!keys.Add(p.key) || Find(p.key) == null || !p.placed || !CanPlace(p, candidate.placements, false)) return false;
            Data.placements = Array.ConvertAll(candidate.placements, p => p.Copy());
            Touch();
            return true;
        }
        public bool CanPlace(Placement p, Placement[] others, bool enforceDoorFront = true)
        {
            var d = Catalog.Find(p.key);
            if (d == null || p.rotation < 0 || p.rotation > 3) return false;
            var size = GridCoordinates.Size(d, p.rotation);
            var rect = new RectInt(p.gx, p.gy, size.x, size.y);
            if (rect.xMin < 0 || rect.yMin < 0 || rect.xMax > Data.room.grid_w || rect.yMax > Data.room.grid_h) return false;
            foreach (var other in others)
            {
                if (other.key == p.key || !other.placed) continue;
                var od = Catalog.Find(other.key);
                if (od == null) return false;
                if (od.ceiling_mounted != d.ceiling_mounted) continue;
                var os = GridCoordinates.Size(od, other.rotation);
                if (rect.Overlaps(new RectInt(other.gx, other.gy, os.x, os.y))) return false;
            }
            if (!d.ceiling_mounted)
                foreach (var door in Data.room.doors)
                    if (door.placed && rect.Overlaps(DoorRect(Data.room, door, enforceDoorFront))) return false;
            return true;
        }
        public static RectInt DoorRect(RoomData room, Opening door, bool front)
        {
            bool vertical = door.wall == "LEFT" || door.wall == "RIGHT";
            int limit = vertical ? room.grid_h : room.grid_w;
            int width = front ? Math.Min(4, limit) : door.length;
            int start = front ? Mathf.Clamp(Mathf.FloorToInt(door.offset + door.length / 2f - width / 2f), 0, limit - width) : door.offset;
            int depth = front ? 2 : 1;
            switch (door.wall)
            {
                case "LEFT": return new RectInt(0, start, depth, width);
                case "RIGHT": return new RectInt(room.grid_w - depth, start, depth, width);
                case "BOTTOM": return new RectInt(start, 0, width, depth);
                default: return new RectInt(start, room.grid_h - depth, width, depth);
            }
        }
        public bool MoveOpening(string key, string wall, int offset)
        {
            var all = new List<Opening>(Data.room.doors); all.AddRange(Data.room.windows);
            var opening = all.Find(o => o.key == key);
            if (opening == null) return false;
            int limit = wall == "LEFT" || wall == "RIGHT" ? Data.room.grid_h : Data.room.grid_w;
            if (offset < 0 || offset + opening.length > limit) return false;
            foreach (var o in all)
                if (o != opening && o.placed && o.wall == wall && offset < o.offset + o.length && o.offset < offset + opening.length) return false;
            string oldWall = opening.wall; int oldOffset = opening.offset;
            opening.wall = wall; opening.offset = offset;
            foreach (var p in Data.placements)
                if (p.placed && !CanPlace(p, Data.placements, false))
                { opening.wall = oldWall; opening.offset = oldOffset; return false; }
            Touch(); return true;
        }
    }
}
