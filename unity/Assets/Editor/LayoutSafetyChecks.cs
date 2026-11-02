using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;

namespace FurnitureLayout.Editor
{
    // Batch entry point, without requiring a new Unity package or scene changes.
    public static class LayoutSafetyChecks
    {
        static int assertions;
        static void Check(bool condition,string message)
        { assertions++; if (!condition) throw new Exception(message); }
        static bool Close(float a,float b) => Mathf.Abs(a-b)<.0001f;
        static Placement Shelf(float x=4,float y=.3f,float rotation=0) =>
            new Placement {key="shelf",gx=x,gy=y,rotation=rotation,placed=true};
        static LayoutState State()
        {
            var state=new LayoutState(new Catalog {schema_version=1,evaluation_version=2,cell_size_m=.25f,
                continuous_placement=true,furniture=new[]{
                    new FurnitureDefinition {key="shelf",label="Shelf",gw=4,gd=2,h_cell=7,furniture_type="STORAGE"},
                    new FurnitureDefinition {key="chair",label="Chair",gw=1,gd=1,h_cell=2,furniture_type="SEAT"},
                    new FurnitureDefinition {key="bed",label="Bed",gw=6,gd=4,h_cell=3,furniture_type="BED",pillow_side="WEST"}
                }});
            state.Data.room.grid_w=state.Data.room.grid_h=16;
            state.Data.room.doors=Array.Empty<Opening>(); state.Data.room.windows=Array.Empty<Opening>();
            return state;
        }
        [Serializable] sealed class Report { public string result; public int assertions; public string coverage; }
        public static void Run()
        {
            try
            {
                SnapChecks(); StateChecks(); PointerChecks(); ContractChecks();
                var report=new Report {result="passed",assertions=assertions,
                    coverage="Wall snap; hysteresis; angle; openings; collision; metadata; shared mouse/touch pointer lifecycle; API JSON contracts. No physical device input."};
                string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.."));
                Directory.CreateDirectory(Path.Combine(root,"outputs"));
                File.WriteAllText(Path.Combine(root,"outputs/unity-safety-checks.json"),JsonUtility.ToJson(report,true));
                Debug.Log("LAYOUT SAFETY CHECKS PASSED: "+assertions);
                EditorApplication.Exit(0);
            }
            catch (Exception e) { Debug.LogException(e); EditorApplication.Exit(1); }
        }
        static void SnapChecks()
        {
            var state=State(); var snap=new WallSnap();
            Check(Close(snap.Resolve(state,Shelf(),true).gy,.08f),"Snap enters at 15 cm");
            Check(Close(snap.Resolve(state,Shelf(y:.8f),true).gy,.08f),"Snap hysteresis holds at 20 cm");
            Check(Close(snap.Resolve(state,Shelf(y:1.1f),true).gy,1.1f) && !snap.Active,"Snap releases beyond 25 cm");
            Check(Close(snap.Resolve(state,Shelf(),false).gy,.3f) && !snap.Active,"OFF preserves free placement");
            Check(Close(snap.Resolve(state,Shelf(y:.1f,rotation:5f/90),true).rotation,0),"Small angle aligns");
            snap.Reset();
            var oblique=Shelf(y:.01f,rotation:11f/90);
            Check(Close(snap.Resolve(state,oblique,true).rotation,oblique.rotation),"Outside entry angle remains free");
            snap.Resolve(state,Shelf(y:.01f),true);
            Check(Close(snap.Resolve(state,Shelf(y:.01f,rotation:13f/90),true).rotation,0),"Angle hysteresis holds");
            var release=Shelf(y:.01f,rotation:16f/90);
            Check(Close(snap.Resolve(state,release,true).rotation,release.rotation) && !snap.Active,"Angle releases");
            Check(Close(snap.Resolve(state,Shelf(x:.3f,y:4,rotation:1),true).gx,.08f),"Clockwise back face aligns LEFT");
            snap.Reset();
            state.Data.room.windows=new[]{new Opening {key="w",wall="BOTTOM",offset=4,length=4}};
            Check(Close(snap.Resolve(state,Shelf(),true).gy,.3f) && !snap.Active,"Window is not a wall target");
            state.Data.room.windows=Array.Empty<Opening>();
            state.Data.room.doors=new[]{new Opening {key="d",wall="BOTTOM",offset=4,length=2}};
            Check(!state.CanPlace(Shelf(),state.Data.placements,false),"Generated placement obeys door front");
            Check(Close(snap.Resolve(state,Shelf(),true).gy,.3f),"Door is not a snap target");
            state.Data.room.doors=Array.Empty<Opening>();
            state.Place(new Placement {key="chair",gx=4,gy=0,placed=true});
            Check(Close(snap.Resolve(state,Shelf(),true).gy,.3f) && !snap.Active,"Colliding snap not adopted");
            state.Remove("chair");
            var bed=new Placement {key="bed",gx=.3f,gy=.3f,placed=true};
            var first=snap.Resolve(state,bed,true); snap.Reset(); var second=snap.Resolve(state,bed,true);
            Check(Close(first.gx,second.gx)&&Close(first.gy,second.gy),"Corner selection deterministic");
            Check(Close(first.gx,.08f)||Close(first.gy,.08f),"Bed head or long side snaps");
            var chair=new Placement {key="chair",gx=4,gy=.3f,placed=true}; snap.Reset();
            Check(Close(snap.Resolve(state,chair,true).gy,.3f),"Chair not forced against wall");
        }
        static void StateChecks()
        {
            var state=State(); Check(state.Place(Shelf(y:3)),"Initial placement");
            state.CycleRestraint("shelf"); state.CycleRestraint("shelf");
            Check(state.Find("shelf").restraint=="wall_bracket","Restraint cycle");
            Check(state.ToggleInstallationConfirmation("shelf"),"User confirms installation");
            var unchanged=state.Find("shelf").Copy(); state.Place(unchanged);
            Check(state.Find("shelf").installation_confirmed,"No-op preserves confirmation");
            var moved=unchanged.Copy(); moved.gx+=1; state.Place(moved);
            Check(!state.Find("shelf").installation_confirmed,"Moving requires recheck");
            state.ToggleInstallationConfirmation("shelf"); moved=state.Find("shelf").Copy(); moved.rotation=1;
            state.Place(moved); Check(!state.Find("shelf").installation_confirmed,"Rotation requires recheck");
            state.Data.room.windows=new[]{new Opening {key="w",wall="TOP",offset=1,length=2}};
            state.CycleWindowProtection("w",true); state.CycleWindowProtection("w",true);
            state.CycleWindowProtection("w",false);
            Check(state.Data.Copy().room.windows[0].film=="present","Window metadata JSON round trip");
            state.Place(new Placement {key="chair",gx=12,gy=12,placed=true});
            state.Place(new Placement {key="bed",gx=8,gy=5,placed=true});
            var candidate=new Candidate {valid=true,placements=Array.ConvertAll(state.Data.placements,p=>p.Copy())};
            candidate.placements[0].gx=2; candidate.placements[0].restraint="none";
            state.ToggleInstallationConfirmation("shelf");
            Check(state.Apply(candidate),"Older pose candidate applies");
            Check(state.Find("shelf").restraint=="wall_bracket" && !state.Find("shelf").installation_confirmed,"Apply keeps current mitigation and clears moved confirmation");
            Check(state.Data.room.windows[0].film=="present","Apply keeps current window input");
            state.SetFixed("shelf",true); candidate.placements[0].gx=3;
            Check(!state.Apply(candidate),"Search lock enforced in domain state");
        }
        static object Call(LayoutInput input,string name,params object[] args) =>
            typeof(LayoutInput).GetMethod(name,BindingFlags.Instance|BindingFlags.NonPublic).Invoke(input,args);
        static void PointerChecks()
        {
            var state=State(); var root=new GameObject("Safety test scene");
            var cameraObject=new GameObject("Safety test camera");
            var texture=new RenderTexture(640,480,16);
            try
            {
                var view=root.AddComponent<LayoutRenderer>(); view.UseModels=false; view.Initialize(state);
                var input=root.AddComponent<LayoutInput>();
                var camera=cameraObject.AddComponent<Camera>(); camera.targetTexture=texture;
                camera.orthographic=true; camera.orthographicSize=3;
                camera.transform.position=new Vector3(2,10,2); camera.transform.rotation=Quaternion.Euler(90,0,0);
                input.State=state; input.View=view; input.Camera=camera; input.SelectedKey="shelf";
                // Both mouse and one-finger touch call this same lifecycle.
                var screen=(Vector2)camera.WorldToScreenPoint(new Vector3(1,0,.075f));
                Call(input,"Begin",screen); Call(input,"Move",screen); Call(input,"End",screen,false);
                Check(state.Find("shelf").placed && Close(state.Find("shelf").gy,.08f),"Shared pointer release commits snap preview");
                var before=state.Find("shelf").Copy();
                Call(input,"Begin",screen); var elsewhere=(Vector2)camera.WorldToScreenPoint(new Vector3(2,0,2));
                Call(input,"Move",elsewhere); Call(input,"End",elsewhere,true);
                Check(Close(state.Find("shelf").gx,before.gx)&&Close(state.Find("shelf").gy,before.gy),"Release over UI cancels drag");
                state.Place(Shelf(y:3));
                input.SetAngle(5);
                Check(Close(state.Find("shelf").rotation,5f/90),"Angle control stays free with snap ON");
                input.Rotate(-1);
                Check(Close(state.Find("shelf").rotation,4f/90),"One-degree adjustment remains free");
            }
            finally { UnityEngine.Object.DestroyImmediate(root); UnityEngine.Object.DestroyImmediate(cameraObject); UnityEngine.Object.DestroyImmediate(texture); }
        }
        static void ContractChecks()
        {
            string root=Path.GetFullPath(Path.Combine(Application.dataPath,"../.."));
            var catalog=JsonUtility.FromJson<Catalog>(File.ReadAllText(Path.Combine(root,"contracts/catalog.json")));
            Check(catalog.evaluation_version==2,"Version 2 catalog");
            var evaluation=JsonUtility.FromJson<Evaluation>(File.ReadAllText(Path.Combine(root,"contracts/evaluation.json")));
            Check(evaluation.safety!=null && evaluation.safety.issues!=null && evaluation.mitigations!=null,"Python safety payload deserializes in Unity");
            Check(evaluation.regions.Any(r=>!string.IsNullOrEmpty(r.scenario_id)),"Scenario metadata deserializes");
            var layout=JsonUtility.FromJson<LayoutData>(File.ReadAllText(Path.Combine(root,"contracts/layout.json")));
            var result=JsonUtility.FromJson<OptimizationJob>(File.ReadAllText(Path.Combine(root,"contracts/optimization-result.json")));
            var state=new LayoutState(catalog); state.Data.room=layout.room;
            foreach (var candidate in result.candidates)
                Check(state.Apply(candidate),"Python candidate passes Unity floating-point geometry and door rules");
        }
    }
}
