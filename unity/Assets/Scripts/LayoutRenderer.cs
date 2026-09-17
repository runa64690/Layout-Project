using System.Collections.Generic;
using UnityEngine;

namespace FurnitureLayout
{
    public sealed class LayoutRenderer : MonoBehaviour
    {
        public ModelLibrary Models;
        public bool ShowCeiling = true;
        public bool UseModels = true;
        public string SelectedKey;
        LayoutState state;
        Transform roomRoot, furnitureRoot, regionRoot;
        GameObject preview;
        Material material;
        MaterialPropertyBlock properties;
        readonly Color[] colors = { new Color(.73f,.43f,.26f), new Color(.24f,.57f,.72f), new Color(.58f,.49f,.34f), new Color(.25f,.32f,.4f), new Color(.55f,.37f,.67f), new Color(.96f,.77f,.24f) };

        void Awake()
        {
            // Native Unity objects must be created on the main thread after construction.
            properties = new MaterialPropertyBlock();
        }

        public void Initialize(LayoutState value)
        {
            if (state != null) state.Changed -= Redraw;
            state = value;
            material = Resources.Load<Material>("LayoutMaterial");
            Models = Resources.Load<ModelLibrary>("ModelLibrary");
            roomRoot = new GameObject("Room").transform; roomRoot.SetParent(transform);
            furnitureRoot = new GameObject("Furniture").transform; furnitureRoot.SetParent(transform);
            regionRoot = new GameObject("Evaluation regions").transform; regionRoot.SetParent(transform);
            state.Changed += Redraw;
            Redraw();
        }
        void OnDestroy() { if (state != null) state.Changed -= Redraw; }
        static void Clear(Transform root)
        {
            foreach (Transform child in root) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
        }
        GameObject Box(Transform parent, Vector3 center, Vector3 size, Color color, bool collider = false)
        {
            var box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.transform.SetParent(parent, false); box.transform.localPosition = center; box.transform.localScale = size;
            var c = box.GetComponent<Collider>(); c.enabled = collider;
            var r = box.GetComponent<Renderer>(); r.sharedMaterial = material;
            properties.SetColor("_BaseColor", color); r.SetPropertyBlock(properties);
            return box;
        }
        public void Redraw()
        {
            Clear(roomRoot); Clear(furnitureRoot); Clear(regionRoot); ClearPreview();
            var room = state.Data.room; float cell = state.Catalog.cell_size_m;
            float w = room.grid_w * cell, h = room.grid_h * cell;
            Box(roomRoot, new Vector3(w/2, -.035f, h/2), new Vector3(w,.06f,h), new Color(.84f,.86f,.84f));
            for (int x=0; x<=room.grid_w; x++) Box(roomRoot, new Vector3(x*cell, .001f, h/2), new Vector3(.007f,.003f,h), new Color(.65f,.7f,.69f));
            for (int y=0; y<=room.grid_h; y++) Box(roomRoot, new Vector3(w/2, .001f, y*cell), new Vector3(w,.003f,.007f), new Color(.65f,.7f,.69f));
            DrawWall("LEFT", room.grid_h); DrawWall("RIGHT", room.grid_h);
            DrawWall("BOTTOM", room.grid_w); DrawWall("TOP", room.grid_w);
            for (int i=0; i<state.Data.placements.Length; i++)
            {
                var p = state.Data.placements[i]; var d = state.Catalog.Find(p.key);
                if (!p.placed || (d.ceiling_mounted && !ShowCeiling)) continue;
                DrawFurniture(p, d, colors[i % colors.Length]);
            }
        }
        void DrawWall(string wall, int cells)
        {
            var room = state.Data.room; float cell = state.Catalog.cell_size_m;
            var openings = new List<Opening>(room.doors); openings.AddRange(room.windows);
            bool vertical = wall == "LEFT" || wall == "RIGHT";
            for (int i=0; i<cells; i++)
            {
                var opening = openings.Find(o => o.placed && o.wall == wall && i >= o.offset && i < o.offset + o.length);
                var color = opening == null ? new Color(.39f,.45f,.47f) :
                    System.Array.Exists(room.doors, o => o.key == opening.key) ? new Color(.15f,.7f,.48f) : new Color(.22f,.55f,.96f);
                float y = opening == null ? .07f : .015f;
                var center = vertical ? new Vector3(wall == "LEFT" ? 0 : room.grid_w*cell, y, (i+.5f)*cell) :
                    new Vector3((i+.5f)*cell, y, wall == "BOTTOM" ? 0 : room.grid_h*cell);
                Box(roomRoot, center, vertical ? new Vector3(.035f,y*2,cell) : new Vector3(cell,y*2,.035f), color);
            }
        }
        void DrawFurniture(Placement p, FurnitureDefinition d, Color color)
        {
            float cell = state.Catalog.cell_size_m;
            var root = new GameObject(d.label); root.transform.SetParent(furnitureRoot, false);
            var dimensions = new Vector3(d.gw*cell, d.h_cell*cell, d.gd*cell);
            var entry = UseModels && Models != null ? Models.Find(d.model_id) : null;
            bool fitted = false;
            if (entry != null)
            {
                var fit = new GameObject("Visual fit").transform; fit.SetParent(root.transform, false);
                var visual = Instantiate(entry.prefab, fit);
                visual.transform.localPosition = Vector3.zero;
                visual.transform.localRotation = Quaternion.Euler(entry.rotationCorrection);
                foreach (var c in visual.GetComponentsInChildren<Collider>()) c.enabled = false;
                var renderers = visual.GetComponentsInChildren<Renderer>();
                if (renderers.Length > 0)
                {
                    var bounds = renderers[0].bounds;
                    foreach (var r in renderers) bounds.Encapsulate(r.bounds);
                    if (bounds.size.x > .0001f && bounds.size.y > .0001f && bounds.size.z > .0001f)
                    {
                        // The new root is at world origin until the fitting is complete.
                        fit.localScale = new Vector3(dimensions.x/bounds.size.x, dimensions.y/bounds.size.y, dimensions.z/bounds.size.z);
                        fit.localPosition = -Vector3.Scale(new Vector3(bounds.center.x, bounds.min.y, bounds.center.z), fit.localScale);
                        fitted = true;
                    }
                }
                if (!fitted) Destroy(fit.gameObject);
            }
            if (!fitted) Box(root.transform, Vector3.up*dimensions.y/2, dimensions, color);
            // Interaction geometry is always the catalog box, regardless of visual detail.
            var collider = root.AddComponent<BoxCollider>(); collider.center = Vector3.up*dimensions.y/2; collider.size = dimensions;
            root.AddComponent<FurnitureHit>().Key = p.key;
            root.transform.position = GridCoordinates.BottomCenter(p,d,state.Data.room,cell);
            root.transform.rotation = GridCoordinates.Rotation(p.rotation);
            Box(root.transform, new Vector3(0,dimensions.y+.008f,dimensions.z*.38f), new Vector3(dimensions.x*.35f,.016f,dimensions.z*.14f), Color.white);
            if (p.key == SelectedKey)
                Box(root.transform, new Vector3(0,dimensions.y+.021f,0), new Vector3(dimensions.x+.025f,.012f,.02f), Color.cyan);
        }
        public void Preview(Placement p, bool valid)
        {
            ClearPreview();
            var d = state.Catalog.Find(p.key); float cell = state.Catalog.cell_size_m;
            var size = GridCoordinates.Size(d,p.rotation);
            var center = GridCoordinates.BottomCenter(p,d,state.Data.room,cell);
            center.y += .03f;
            preview = Box(transform, center, new Vector3(size.x*cell,.04f,size.y*cell), valid ? Color.green : Color.red);
        }
        public void ClearPreview() { if (preview != null) { preview.SetActive(false); Destroy(preview); preview = null; } }
        public void ShowRegions(Region[] regions)
        {
            Clear(regionRoot);
            if (regions == null) return;
            float cell = state.Catalog.cell_size_m;
            foreach (var r in regions)
            {
                int x0 = Mathf.Clamp(r.x0,0,state.Data.room.grid_w), x1 = Mathf.Clamp(r.x1,0,state.Data.room.grid_w);
                int y0 = Mathf.Clamp(r.y0,0,state.Data.room.grid_h), y1 = Mathf.Clamp(r.y1,0,state.Data.room.grid_h);
                if (x1<=x0 || y1<=y0) continue;
                Color color = r.kind == "fall" ? new Color(.94f,.48f,.35f) : r.kind == "door_front" ? new Color(.35f,.74f,.55f) : new Color(.43f,.65f,.92f);
                // Thin outlines keep the floor and furniture visible.
                float x=(x0+x1)*cell/2, z=(y0+y1)*cell/2, w=(x1-x0)*cell, h=(y1-y0)*cell;
                Box(regionRoot,new Vector3(x,.014f,y0*cell),new Vector3(w,.012f,.02f),color);
                Box(regionRoot,new Vector3(x,.014f,y1*cell),new Vector3(w,.012f,.02f),color);
                Box(regionRoot,new Vector3(x0*cell,.014f,z),new Vector3(.02f,.012f,h),color);
                Box(regionRoot,new Vector3(x1*cell,.014f,z),new Vector3(.02f,.012f,h),color);
            }
        }
    }
}
