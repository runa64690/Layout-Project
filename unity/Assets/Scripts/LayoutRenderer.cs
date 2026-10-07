using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace FurnitureLayout
{
    public sealed class LayoutRenderer : MonoBehaviour
    {
        public ModelLibrary Models;
        public bool ShowCeiling = true;
        public bool UseModels = true;
        public bool ShowGrid = false;
        public string SelectedKey;
        LayoutState state;
        Transform roomRoot, furnitureRoot, regionRoot;
        GameObject preview, previewFootprint, hiddenFurniture;
        string previewKey;
        readonly Dictionary<string, GameObject> furnitureObjects = new Dictionary<string, GameObject>();
        readonly Dictionary<Material, Material> previewMaterials = new Dictionary<Material, Material>();
        const float DragOpacity = .45f;
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
            if (properties == null) properties=new MaterialPropertyBlock();
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
        void OnDestroy()
        {
            if (state != null) state.Changed -= Redraw;
            ClearPreview();
        }
        static void Release(Object value)
        {
            if (value == null) return;
            if (Application.isPlaying) Destroy(value); else DestroyImmediate(value);
        }
        static void Clear(Transform root)
        {
            for (int i=root.childCount-1;i>=0;i--)
            {
                var child=root.GetChild(i).gameObject; child.SetActive(false); Release(child);
            }
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
            ClearPreview();
            Clear(roomRoot); Clear(furnitureRoot); Clear(regionRoot); furnitureObjects.Clear();
            var room = state.Data.room; float cell = state.Catalog.cell_size_m;
            float w = room.grid_w * cell, h = room.grid_h * cell;
            Box(roomRoot, new Vector3(w/2, -.035f, h/2), new Vector3(w,.06f,h), new Color(.84f,.86f,.84f));
            if (ShowGrid) for (int x=0; x<=room.grid_w; x++) Box(roomRoot, new Vector3(x*cell, .001f, h/2), new Vector3(.007f,.003f,h), new Color(.65f,.7f,.69f));
            if (ShowGrid) for (int y=0; y<=room.grid_h; y++) Box(roomRoot, new Vector3(w/2, .001f, y*cell), new Vector3(w,.003f,.007f), new Color(.65f,.7f,.69f));
            DrawWall("LEFT", room.grid_h); DrawWall("RIGHT", room.grid_h);
            DrawWall("BOTTOM", room.grid_w); DrawWall("TOP", room.grid_w);
            for (int i=0; i<state.Data.placements.Length; i++)
            {
                var p = state.Data.placements[i]; var d = state.Catalog.Find(p.key);
                if (!p.placed || (d.ceiling_mounted && !ShowCeiling)) continue;
                furnitureObjects[p.key]=DrawFurniture(p,d,colors[i % colors.Length],furnitureRoot);
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
        GameObject DrawFurniture(Placement p, FurnitureDefinition d, Color color, Transform parent, bool interactive = true)
        {
            float cell = state.Catalog.cell_size_m;
            var root = new GameObject(d.label); root.transform.SetParent(parent, false);
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
                if (!fitted) Release(fit.gameObject);
            }
            if (!fitted) Box(root.transform, Vector3.up*dimensions.y/2, dimensions, color);
            // Interaction geometry is always the catalog box, regardless of visual detail.
            if (interactive)
            {
                var collider = root.AddComponent<BoxCollider>(); collider.center = Vector3.up*dimensions.y/2; collider.size = dimensions;
                root.AddComponent<FurnitureHit>().Key = p.key;
            }
            root.transform.position = GridCoordinates.BottomCenter(p,d,state.Data.room,cell);
            root.transform.rotation = GridCoordinates.Rotation(p.rotation);
            Box(root.transform, new Vector3(0,dimensions.y+.008f,dimensions.z*.38f), new Vector3(dimensions.x*.35f,.016f,dimensions.z*.14f), Color.white);
            if (interactive && p.key == SelectedKey)
                Box(root.transform, new Vector3(0,dimensions.y+.021f,0), new Vector3(dimensions.x+.025f,.012f,.02f), Color.cyan);
            return root;
        }
        public void Preview(Placement p, bool valid)
        {
            var d=state.Catalog.Find(p.key);
            float cell=state.Catalog.cell_size_m;
            if (preview == null || previewKey != p.key)
            {
                ClearPreview();
                previewKey=p.key;
                int index=System.Array.FindIndex(state.Data.placements,item=>item.key==p.key);
                preview=DrawFurniture(p,d,colors[Mathf.Max(0,index)%colors.Length],transform,false);
                preview.name="Drag preview";
                MakeTransparent(preview);
                // Suppress the original visual until the drop is committed or cancelled.
                if (furnitureObjects.TryGetValue(p.key,out hiddenFurniture)) hiddenFurniture.SetActive(false);
                previewFootprint=Box(preview.transform,new Vector3(0,.008f,0),
                    new Vector3(d.gw*cell,.012f,d.gd*cell),Color.green);
                previewFootprint.name="Placement indicator";
            }
            // Reuse the same visual and materials for the entire drag.
            preview.transform.position=GridCoordinates.BottomCenter(p,d,state.Data.room,cell);
            preview.transform.rotation=GridCoordinates.Rotation(p.rotation);
            properties.Clear(); properties.SetColor("_BaseColor",valid ? Color.green : Color.red);
            previewFootprint.GetComponent<Renderer>().SetPropertyBlock(properties);
        }
        void MakeTransparent(GameObject root)
        {
            foreach (var collider in root.GetComponentsInChildren<Collider>(true)) collider.enabled=false;
            foreach (var renderer in root.GetComponentsInChildren<Renderer>(true))
            {
                var materials=renderer.sharedMaterials;
                for (int i=0;i<materials.Length;i++)
                {
                    var source=materials[i];
                    if (source == null) continue;
                    if (!previewMaterials.TryGetValue(source,out var transparent))
                    {
                        transparent=new Material(source) { name=source.name+" (drag)", hideFlags=HideFlags.DontSave };
                        transparent.SetFloat("_Surface",1);
                        transparent.SetFloat("_Blend",0);
                        transparent.SetFloat("_AlphaClip",0);
                        transparent.DisableKeyword("_ALPHATEST_ON");
                        transparent.SetFloat("_SrcBlend",(float)BlendMode.SrcAlpha);
                        transparent.SetFloat("_DstBlend",(float)BlendMode.OneMinusSrcAlpha);
                        transparent.SetFloat("_SrcBlendAlpha",(float)BlendMode.One);
                        transparent.SetFloat("_DstBlendAlpha",(float)BlendMode.OneMinusSrcAlpha);
                        transparent.SetFloat("_ZWrite",0);
                        transparent.SetOverrideTag("RenderType","Transparent");
                        transparent.renderQueue=(int)RenderQueue.Transparent;
                        transparent.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                        transparent.DisableKeyword("_ALPHAPREMULTIPLY_ON");
                        transparent.DisableKeyword("_ALPHAMODULATE_ON");
                        transparent.SetShaderPassEnabled("ShadowCaster",false);
                        transparent.SetShaderPassEnabled("DepthOnly",false);
                        transparent.SetShaderPassEnabled("DepthNormals",false);
                        if (source.HasProperty("_BaseColor"))
                        {
                            var color=source.GetColor("_BaseColor"); color.a*=DragOpacity;
                            transparent.SetColor("_BaseColor",color);
                        }
                        previewMaterials.Add(source,transparent);
                    }
                    materials[i]=transparent;
                    // Preserve per-submesh overrides as well as the model's textures.
                    var block=new MaterialPropertyBlock(); renderer.GetPropertyBlock(block,i);
                    FadeOverride(block);
                    if (!block.isEmpty) renderer.SetPropertyBlock(block,i);
                }
                renderer.sharedMaterials=materials;
                var globalBlock=new MaterialPropertyBlock(); renderer.GetPropertyBlock(globalBlock);
                FadeOverride(globalBlock); renderer.SetPropertyBlock(globalBlock);
                renderer.shadowCastingMode=ShadowCastingMode.Off;
            }
        }
        static void FadeOverride(MaterialPropertyBlock block)
        {
            if (!block.HasColor("_BaseColor")) return;
            var color=block.GetColor("_BaseColor"); color.a*=DragOpacity;
            block.SetColor("_BaseColor",color);
        }
        public void ClearPreview()
        {
            if (hiddenFurniture != null) hiddenFurniture.SetActive(true);
            hiddenFurniture=null;
            if (preview != null) { preview.SetActive(false); Release(preview); }
            preview=null; previewFootprint=null; previewKey=null;
            foreach (var material in previewMaterials.Values) Release(material);
            previewMaterials.Clear();
        }
        public void ShowRegions(Region[] regions)
        {
            Clear(regionRoot);
            if (regions == null) return;
            float cell = state.Catalog.cell_size_m;
            foreach (var r in regions)
            {
                Color color = r.kind == "fall" ? new Color(.94f,.48f,.35f) : r.kind == "door_front" ? new Color(.35f,.74f,.55f) : new Color(.43f,.65f,.92f);
                var points = r.points;
                if (points == null || points.Length < 3) points = new[] {
                    new RegionPoint {x=r.x0,y=r.y0}, new RegionPoint {x=r.x1,y=r.y0},
                    new RegionPoint {x=r.x1,y=r.y1}, new RegionPoint {x=r.x0,y=r.y1} };
                var clipped = new List<Vector2>();
                foreach (var point in points) clipped.Add(new Vector2(point.x,point.y));
                // Clip the polygon itself; clamping vertices distorts oblique regions.
                clipped=Clip(clipped,0,0,true); clipped=Clip(clipped,0,state.Data.room.grid_w,false);
                clipped=Clip(clipped,1,0,true); clipped=Clip(clipped,1,state.Data.room.grid_h,false);
                for (int i=0;i<clipped.Count;i++)
                {
                    var a=clipped[i]*cell; var b=clipped[(i+1)%clipped.Count]*cell;
                    var delta=b-a;
                    if (delta.sqrMagnitude<.000001f) continue;
                    var line=Box(regionRoot,new Vector3((a.x+b.x)/2,.014f,(a.y+b.y)/2),new Vector3(.02f,.012f,delta.magnitude),color);
                    line.transform.rotation=Quaternion.Euler(0,Mathf.Atan2(delta.x,delta.y)*Mathf.Rad2Deg,0);
                }
            }
        }
        static List<Vector2> Clip(List<Vector2> points,int axis,float limit,bool minimum)
        {
            var result=new List<Vector2>();
            if (points.Count==0) return result;
            var previous=points[points.Count-1];
            float d0=(previous[axis]-limit)*(minimum?1:-1);
            foreach (var current in points)
            {
                float d1=(current[axis]-limit)*(minimum?1:-1);
                if ((d0>=0)!=(d1>=0)) result.Add(Vector2.Lerp(previous,current,d0/(d0-d1)));
                if (d1>=0) result.Add(current);
                previous=current; d0=d1;
            }
            return result;
        }
    }
}
