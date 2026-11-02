using System;
using System.Collections.Generic;
using UnityEngine;

namespace FurnitureLayout
{
    // Pure drag geometry. Distances/angles are UX assumptions, not safety rules.
    public sealed class WallSnap
    {
        public const float EnterDistanceM=.15f, LeaveDistanceM=.25f, GapM=.02f;
        public const float EnterAngle=10, LeaveAngle=15;
        static readonly string[] Walls={"LEFT","RIGHT","BOTTOM","TOP"};
        static readonly Vector2[] Normals={Vector2.up,Vector2.right,Vector2.down,Vector2.left};
        static readonly Vector2[] WallNormals={Vector2.left,Vector2.right,Vector2.down,Vector2.up};
        int activeWall=-1, activeFace=-1;
        public bool Active => activeWall>=0;
        public void Reset() { activeWall=activeFace=-1; }
        static int[] Faces(FurnitureDefinition d)
        {
            if (d.furniture_type=="STORAGE" || d.furniture_type=="TV_STAND") return new[]{2};
            if (d.furniture_type!="BED") return Array.Empty<int>();
            int head=Array.IndexOf(new[]{"NORTH","EAST","SOUTH","WEST"},d.pillow_side);
            var faces=new List<int>{head<0?3:head};
            foreach (int face in d.gw>=d.gd ? new[]{0,2} : new[]{1,3}) if (!faces.Contains(face)) faces.Add(face);
            return faces.ToArray();
        }
        static Vector2 Rotate(Vector2 v,float quarters)
        {
            float a=quarters*Mathf.PI/2,c=Mathf.Cos(a),s=Mathf.Sin(a);
            return new Vector2(c*v.x+s*v.y,-s*v.x+c*v.y);
        }
        static Vector2[] Face(Placement p,FurnitureDefinition d,int face)
        {
            var center=new Vector2(p.gx,p.gy)+GridCoordinates.Size(d,p.rotation)/2;
            var normal=Normals[face]; bool horizontal=face%2==0;
            var offset=normal*(horizontal?d.gd:d.gw)/2;
            var tangent=(horizontal?Vector2.right:Vector2.up)*(horizontal?d.gw:d.gd)/2;
            return new[]{center+Rotate(offset-tangent,p.rotation),center+Rotate(offset+tangent,p.rotation)};
        }
        static float Gap(RoomData room,Vector2 p,int wall) => wall==0?p.x:wall==1?room.grid_w-p.x:wall==2?p.y:room.grid_h-p.y;
        static bool Solid(RoomData room,Placement p,FurnitureDefinition d,int face,int wall)
        {
            var points=Face(p,d,face); int axis=wall<2?1:0;
            float lo=Mathf.Min(points[0][axis],points[1][axis]),hi=Mathf.Max(points[0][axis],points[1][axis]);
            float limit=wall<2?room.grid_h:room.grid_w;
            if (lo < -GridCoordinates.Epsilon || hi>limit+GridCoordinates.Epsilon) return false;
            foreach (var openings in new[]{room.doors,room.windows})
                foreach (var o in openings)
                    if (o.placed && o.wall==Walls[wall] && lo<o.offset+o.length && hi>o.offset) return false;
            return true;
        }
        bool TryFace(LayoutState state,Placement raw,int wall,int face,bool retained,out Placement snapped,out float metric)
        {
            snapped=null; metric=float.PositiveInfinity;
            var d=state.Catalog.Find(raw.key); var room=state.Data.room; float cell=state.Catalog.cell_size_m;
            float angle=Vector2.Angle(Rotate(Normals[face],raw.rotation),WallNormals[wall]);
            var points=Face(raw,d,face);
            float gap=Mathf.Max(Gap(room,points[0],wall),Gap(room,points[1],wall))*cell;
            if (angle>(retained?LeaveAngle:EnterAngle) || gap>(retained?LeaveDistanceM:EnterDistanceM)) return false;
            if (!Solid(room,raw,d,face,wall)) return false;
            var p=raw.Copy(); var center=new Vector2(p.gx,p.gy)+GridCoordinates.Size(d,p.rotation)/2;
            var n=Normals[face]; var w=WallNormals[wall];
            p.rotation=Mathf.Repeat(Mathf.Round((Mathf.Atan2(n.y,n.x)-Mathf.Atan2(w.y,w.x))/(Mathf.PI/2)),4);
            var size=GridCoordinates.Size(d,p.rotation); p.gx=center.x-size.x/2; p.gy=center.y-size.y/2;
            float desired=GapM/cell;
            if (wall==0) p.gx=desired;
            else if (wall==1) p.gx=room.grid_w-size.x-desired;
            else if (wall==2) p.gy=desired;
            else p.gy=room.grid_h-size.y-desired;
            if (!Solid(room,p,d,face,wall) || !state.CanPlace(p,state.Data.placements)) return false;
            metric=gap/EnterDistanceM+angle/EnterAngle; snapped=p; return true;
        }
        public Placement Resolve(LayoutState state,Placement raw,bool enabled)
        {
            if (!enabled) { Reset(); return raw; }
            if (Active && TryFace(state,raw,activeWall,activeFace,true,out var held,out _)) return held;
            Reset(); Placement best=raw; float minimum=float.PositiveInfinity;
            foreach (int face in Faces(state.Catalog.Find(raw.key)))
                for (int wall=0;wall<Walls.Length;wall++)
                    if (TryFace(state,raw,wall,face,false,out var candidate,out float metric) && metric<minimum)
                    { minimum=metric; best=candidate; activeWall=wall; activeFace=face; }
            return best;
        }
    }
}
