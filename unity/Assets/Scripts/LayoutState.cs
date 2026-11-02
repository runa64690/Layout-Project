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
            Data.placements[index] = KeepMitigation(candidate);
            Touch();
            return true;
        }
        public void Remove(string key)
        {
            Find(key).placed = false;
            Find(key).installation_confirmed = false;
            FixedKeys.Remove(key);
            Touch();
        }
        public bool Apply(Candidate candidate)
        {
            if (!candidate.valid || candidate.placements == null || candidate.placements.Length != Data.placements.Length) return false;
            var keys = new HashSet<string>();
            foreach (var p in candidate.placements)
                if (!keys.Add(p.key) || Find(p.key) == null || !p.placed || !CanPlace(p, candidate.placements, false)) return false;
            foreach (var key in FixedKeys)
                if (!SamePose(Find(key),Array.Find(candidate.placements,p=>p.key==key))) return false;
            Data.placements = Array.ConvertAll(candidate.placements, KeepMitigation);
            Touch();
            return true;
        }
        static bool SamePose(Placement a, Placement b) => a!=null && b!=null &&
            a.gx==b.gx && a.gy==b.gy && a.rotation==b.rotation && a.placed==b.placed;
        Placement KeepMitigation(Placement proposed)
        {
            var current=Find(proposed.key); var result=proposed.Copy();
            result.restraint=current.restraint;
            result.installation_confirmed=current.installation_confirmed && SamePose(current,proposed);
            return result;
        }
        public static readonly string[] Restraints = { "unknown", "none", "wall_bracket", "belt", "pole", "pole_combination", "other" };
        public static readonly string[] Protections = { "unknown", "none", "present" };
        public void CycleRestraint(string key)
        {
            var p=Find(key); if (p==null) return;
            p.restraint=Restraints[(Array.IndexOf(Restraints,p.restraint)+1)%Restraints.Length];
            p.installation_confirmed=false; Touch();
        }
        public bool ToggleInstallationConfirmation(string key)
        {
            var p=Find(key);
            if (p==null || !p.placed || p.restraint=="unknown" || p.restraint=="none") return false;
            p.installation_confirmed=!p.installation_confirmed; Touch(); return true;
        }
        public void CycleWindowProtection(string key, bool film)
        {
            var w=Array.Find(Data.room.windows,o=>o.key==key); if (w==null) return;
            string current=film ? w.film : w.curtains;
            string next=Protections[(Array.IndexOf(Protections,current)+1)%Protections.Length];
            if (film) w.film=next; else w.curtains=next;
            Touch();
        }
        public bool CanPlace(Placement p, Placement[] others, bool enforceDoorFront = true)
        {
            var d = Catalog.Find(p.key);
            if (d == null || !GridCoordinates.Finite(p.gx) || !GridCoordinates.Finite(p.gy) ||
                !GridCoordinates.Finite(p.rotation) || p.rotation < 0 || p.rotation >= 4) return false;
            var polygon = GridCoordinates.Corners(p,d);
            float epsilon = GridCoordinates.Epsilon;
            foreach (var point in polygon)
                if (point.x < -epsilon || point.y < -epsilon || point.x > Data.room.grid_w+epsilon || point.y > Data.room.grid_h+epsilon) return false;
            foreach (var other in others)
            {
                if (other.key == p.key || !other.placed) continue;
                var od = Catalog.Find(other.key);
                if (od == null) return false;
                if (od.ceiling_mounted != d.ceiling_mounted) continue;
                if (GridCoordinates.Overlaps(polygon,GridCoordinates.Corners(other,od))) return false;
            }
            if (!d.ceiling_mounted)
                foreach (var door in Data.room.doors)
                    if (door.placed && GridCoordinates.Overlaps(polygon,GridCoordinates.Corners(DoorRect(Data.room, door, enforceDoorFront)))) return false;
            return true;
        }
        public static RectInt DoorRect(RoomData room, Opening door, bool front)
        {
            bool vertical = door.wall == "LEFT" || door.wall == "RIGHT";
            int limit = vertical ? room.grid_h : room.grid_w;
            // Compatibility argument only: manual and generated placement agree.
            int width = door.length;
            int start = door.offset;
            int depth = 2;
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
