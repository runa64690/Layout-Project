using System;
using System.IO;
using FurnitureLayout;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

public static class LayoutProjectSetup
{
    const string ScenePath="Assets/Scenes/Layout.unity";
    [MenuItem("Layout/Setup project")]
    public static void Setup()
    {
        Directory.CreateDirectory("Assets/Settings"); Directory.CreateDirectory("Assets/Scenes");
        Directory.CreateDirectory("Assets/Resources"); Directory.CreateDirectory("Assets/Models");
        var pipeline=AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/LayoutURP.asset");
        if (pipeline==null)
        {
            var renderer=ScriptableObject.CreateInstance<UniversalRendererData>();
            AssetDatabase.CreateAsset(renderer,"Assets/Settings/LayoutRenderer.asset");
            pipeline=UniversalRenderPipelineAsset.Create(renderer);
            pipeline.msaaSampleCount=2; pipeline.renderScale=1;
            pipeline.supportsHDR=false; pipeline.shadowDistance=15;
            AssetDatabase.CreateAsset(pipeline,"Assets/Settings/LayoutURP.asset");
        }
        GraphicsSettings.defaultRenderPipeline=pipeline;
        QualitySettings.renderPipeline=pipeline;
        var material=AssetDatabase.LoadAssetAtPath<Material>("Assets/Resources/LayoutMaterial.mat");
        if (material==null)
        {
            material=new Material(Shader.Find("Universal Render Pipeline/Lit"));
            material.SetFloat("_Smoothness",.25f);
            AssetDatabase.CreateAsset(material,"Assets/Resources/LayoutMaterial.mat");
        }
        var library=AssetDatabase.LoadAssetAtPath<ModelLibrary>("Assets/Resources/ModelLibrary.asset");
        if (library==null)
        {
            // Bundled sample demonstrates visual replacement without changing catalog geometry.
            var shelf=new GameObject("Sample bookshelf");
            for (int i=0;i<5;i++) Part(shelf.transform,new Vector3(0,i*.35f,0),new Vector3(1,.04f,.5f),material);
            Part(shelf.transform,new Vector3(-.48f,.7f,0),new Vector3(.04f,1.44f,.5f),material);
            Part(shelf.transform,new Vector3(.48f,.7f,0),new Vector3(.04f,1.44f,.5f),material);
            Part(shelf.transform,new Vector3(0,.7f,-.23f),new Vector3(1,1.44f,.04f),material);
            var prefab=PrefabUtility.SaveAsPrefabAsset(shelf,"Assets/Models/SampleShelf.prefab");
            UnityEngine.Object.DestroyImmediate(shelf);
            library=ScriptableObject.CreateInstance<ModelLibrary>();
            library.entries=new[] { new ModelLibrary.Entry { modelId="shelf",prefab=prefab } };
            AssetDatabase.CreateAsset(library,"Assets/Resources/ModelLibrary.asset");
        }
        if (!File.Exists(ScenePath))
        {
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var camera=new GameObject("Main Camera",typeof(Camera)); camera.tag="MainCamera";
            camera.GetComponent<Camera>().backgroundColor=new Color(.08f,.12f,.16f);
            camera.GetComponent<Camera>().clearFlags=CameraClearFlags.SolidColor;
            camera.AddComponent<UniversalAdditionalCameraData>();
            var light=new GameObject("Sun",typeof(Light)); light.transform.rotation=Quaternion.Euler(45,-30,0);
            light.GetComponent<Light>().type=LightType.Directional; light.GetComponent<Light>().intensity=1.3f;
            new GameObject("Layout Application",typeof(LayoutApplication));
            RenderSettings.ambientLight=new Color(.65f,.65f,.65f);
            EditorSceneManager.SaveScene(scene,ScenePath);
        }
        EditorBuildSettings.scenes=new[] { new EditorBuildSettingsScene(ScenePath,true) };
        PlayerSettings.companyName="LayoutResearch"; PlayerSettings.productName="Furniture Layout";
        PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android,"org.layoutresearch.furniture");
        PlayerSettings.Android.minSdkVersion=AndroidSdkVersions.AndroidApiLevel26;
        PlayerSettings.Android.targetArchitectures=AndroidArchitecture.ARM64;
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android,ScriptingImplementation.IL2CPP);
        PlayerSettings.defaultInterfaceOrientation=UIOrientation.AutoRotation;
        PlayerSettings.insecureHttpOption=InsecureHttpOption.DevelopmentOnly;
        AssetDatabase.SaveAssets(); AssetDatabase.Refresh();
        Debug.Log("LAYOUT_SETUP_OK");
    }
    static void Part(Transform parent,Vector3 position,Vector3 size,Material material)
    {
        var part=GameObject.CreatePrimitive(PrimitiveType.Cube); part.transform.SetParent(parent);
        part.transform.localPosition=position; part.transform.localScale=size; part.GetComponent<Renderer>().sharedMaterial=material;
    }
    [MenuItem("Layout/Build Web")]
    public static void BuildWeb() { Setup(); Build(BuildTarget.WebGL,"Builds/Web"); }
    [MenuItem("Layout/Build Android development APK")]
    public static void BuildAndroid() { Setup(); Build(BuildTarget.Android,"Builds/Android/Layout.apk"); }
    static void Build(BuildTarget target,string path)
    {
        if (!BuildPipeline.IsBuildTargetSupported(BuildPipeline.GetBuildTargetGroup(target),target)) throw new InvalidOperationException("Install the Unity build module for "+target);
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        var report=BuildPipeline.BuildPlayer(new BuildPlayerOptions { scenes=new[] {ScenePath},locationPathName=path,target=target,options=BuildOptions.Development });
        if (report.summary.result!=BuildResult.Succeeded) throw new InvalidOperationException("Build failed: "+report.summary.result);
    }
    [MenuItem("Layout/Run contract smoke checks")]
    public static void SmokeChecks()
    {
        Setup();
        var d=new FurnitureDefinition {key="shelf",gw=4,gd=2,h_cell=7};
        var room=new RoomData();
        for (int r=0;r<4;r++)
        {
            var p=new Placement {key="shelf",gx=2,gy=3,rotation=r,placed=true};
            var size=GridCoordinates.Size(d,r);
            var center=GridCoordinates.BottomCenter(p,d,room,.25f);
            Check(Mathf.Approximately(center.x,(2+size.x/2f)*.25f),"center X");
            Check(Mathf.Approximately(center.z,(3+size.y/2f)*.25f),"center Z");
            var expected=new[] {Vector3.forward,Vector3.right,Vector3.back,Vector3.left}[r];
            Check(Vector3.Distance(GridCoordinates.Rotation(r)*Vector3.forward,expected)<.0001f,"rotation");
        }
        var catalog=new Catalog {schema_version=1,cell_size_m=.25f,furniture=new[] {d,new FurnitureDefinition {key="lamp",gw=2,gd=2,h_cell=1,ceiling_mounted=true}}};
        var state=new LayoutState(catalog);
        Check(state.Place(new Placement {key="shelf",gx=4,gy=3,placed=true}),"floor placement");
        Check(state.Place(new Placement {key="lamp",gx=4,gy=3,placed=true}),"ceiling separate from floor");
        Check(!state.Place(new Placement {key="shelf",gx=-1,gy=3,placed=true}),"bounds rejection");
        Check(!state.Place(new Placement {key="shelf",gx=0,gy=5,placed=true}),"door rejection");
        Check(Mathf.Approximately(GridCoordinates.BottomCenter(state.Find("lamp"),catalog.Find("lamp"),room,.25f).y,2.25f),"ceiling height");
        var snapshot=state.Data.Copy(); snapshot.placements[0].gx=9;
        Check(state.Find("shelf").gx==4,"request snapshots independent");
        var response=JsonUtility.FromJson<Evaluation>("{\"schema_version\":1,\"revision\":3,\"total\":2.5,\"breakdown\":[{\"name\":\"clearance\",\"value\":2.5}],\"regions\":[],\"violations\":[]}");
        Check(response.breakdown[0].name=="clearance" && response.revision==3,"JSON response");
        foreach (var wall in new[] {"LEFT","RIGHT","BOTTOM","TOP"})
        {
            var door=new Opening {key="check",wall=wall,offset=5,length=2};
            var rect=LayoutState.DoorRect(room,door,true);
            Check(rect.width*rect.height==8 && rect.xMin>=0 && rect.yMin>=0 && rect.xMax<=room.grid_w && rect.yMax<=room.grid_h,"door geometry "+wall);
        }
        var fractional=new Placement {key="shelf",gx=2.125f,gy=3.375f,rotation=.5f,placed=true};
        Check(state.Place(fractional),"fractional placement and 45 degree rotation");
        var roundTrip=state.Data.Copy().placements[0];
        Check(roundTrip.gx==fractional.gx && roundTrip.rotation==fractional.rotation,"fractional JSON round trip");
        Check(!state.Place(new Placement {key="shelf",gx=float.NaN,gy=3,placed=true}),"nonfinite rejection");
        Check(!state.Place(new Placement {key="shelf",gx=8,gy=8,rotation=.5f,placed=true}),"rotated bounds rejection");
        var table=new FurnitureDefinition {key="table",gw=3,gd=2,h_cell=3};
        var a=GridCoordinates.Corners(new Placement {gx=2,gy=2,rotation=.5f},d);
        var b=GridCoordinates.Corners(new Placement {gx=4,gy=4,rotation=.5f},table);
        Check(!GridCoordinates.Overlaps(a,b),"empty bounding-box corners do not collide");
        Check(GridCoordinates.Overlaps(a,GridCoordinates.Corners(new Placement {gx=2.1f,gy=2.1f,rotation=.5f},table)),"oblique overlap rejection");
        Check(!GridCoordinates.Overlaps(GridCoordinates.Corners(new Placement {gx=.125f,gy=.25f},d),
            GridCoordinates.Corners(new Placement {gx=4.125f,gy=.25f},table)),"touching edges allowed");
        var cellPoint=GridCoordinates.Cell(new Vector3(.3125f,0,.4375f),.25f);
        Check(cellPoint==new Vector2(1.25f,1.75f),"pointer coordinates do not snap");
        var inputObject=new GameObject("Continuous input smoke");
        var input=inputObject.AddComponent<LayoutInput>();
        input.State=state; input.View=inputObject.AddComponent<LayoutRenderer>(); input.SelectedKey="shelf";
        var beforeCenter=GridCoordinates.BottomCenter(state.Find("shelf"),d,state.Data.room,.25f);
        input.SetAngle(63.25f);
        Check(Mathf.Abs(state.Find("shelf").rotation*90-63.25f)<.0001f,"arbitrary input angle");
        Check(Vector3.Distance(beforeCenter,GridCoordinates.BottomCenter(state.Find("shelf"),d,state.Data.room,.25f))<.00001f,"rotation keeps center");
        UnityEngine.Object.DestroyImmediate(inputObject);
        string contracts=Path.GetFullPath("../contracts");
        var apiCatalog=JsonUtility.FromJson<Catalog>(File.ReadAllText(Path.Combine(contracts,"catalog.json")));
        var apiLayout=JsonUtility.FromJson<LayoutData>(File.ReadAllText(Path.Combine(contracts,"layout.json")));
        var apiEvaluation=JsonUtility.FromJson<Evaluation>(File.ReadAllText(Path.Combine(contracts,"evaluation.json")));
        var apiJob=JsonUtility.FromJson<OptimizationJob>(File.ReadAllText(Path.Combine(contracts,"optimization-result.json")));
        Check(apiCatalog.furniture.Length==6 && apiCatalog.Find("shelf").model_id=="shelf","Python catalog contract");
        Check(apiLayout.placements.Length==6 && apiLayout.room.windows[0].wall=="TOP","Python layout contract");
        Check(apiEvaluation.breakdown.Length>0 && apiEvaluation.revision==apiLayout.revision,"Python evaluation contract");
        Check(apiJob.status=="succeeded" && apiJob.candidates.Length>0 && apiJob.candidates[0].placements.Length==6,"Python job contract");
        Check(Resources.Load<ModelLibrary>("ModelLibrary").Find("shelf")!=null,"bundled visual prefab");
        DragSmokeChecks();
        Debug.Log("LAYOUT_SMOKE_OK");
    }
    [MenuItem("Layout/Run drag smoke checks")]
    public static void DragSmokeChecks()
    {
        var d=new FurnitureDefinition {key="shelf",label="Shelf",model_id="shelf",gw=4,gd=2,h_cell=7};
        var room=new RoomData();
        foreach (float rotation in new[] {0f,.5f,1f,1.37f,2.5f,3.999f})
            foreach (var point in new[] {new Vector2(-100,-100),new Vector2(100,100),new Vector2(-100,100),new Vector2(100,-100),new Vector2(3.125f,4.375f)})
            {
                var p=new Placement {rotation=rotation};
                Check(GridCoordinates.ClampToRoom(p,d,room,point),"drag fits at rotation "+rotation);
                foreach (var corner in GridCoordinates.Corners(p,d))
                    Check(corner.x>=-.00001f && corner.y>=-.00001f && corner.x<=room.grid_w+.00001f && corner.y<=room.grid_h+.00001f,"drag corners stay inside");
                if (point.x>0 && point.x<4 && point.y<5)
                    Check(p.gx==point.x && p.gy==point.y,"interior movement does not snap");
            }
        Check(!GridCoordinates.ClampToRoom(new Placement(),new FurnitureDefinition {gw=20,gd=2},room,Vector2.zero),"oversize drag is rejected");
        Check(!GridCoordinates.ClampToRoom(new Placement(),d,room,new Vector2(float.NaN,0)),"nonfinite drag is rejected");
        var state=new LayoutState(new Catalog {cell_size_m=.25f,furniture=new[] {d}});
        Check(state.Place(new Placement {key="shelf",gx=4,gy=3,rotation=.5f,placed=true}),"drag initial placement");
        var host=new GameObject("Drag smoke");
        try
        {
            var view=host.AddComponent<LayoutRenderer>(); view.Initialize(state);
            foreach (bool models in new[] {true,false})
            {
                view.UseModels=models; view.Redraw();
                var original=host.transform.Find("Furniture").GetChild(0).gameObject;
                var originalPosition=original.transform.position;
                var p=state.Find("shelf").Copy();
                GridCoordinates.ClampToRoom(p,d,state.Data.room,new Vector2(100,100));
                int revision=state.Data.revision;
                view.Preview(p,true);
                var ghost=host.transform.Find("Drag preview");
                Check(ghost!=null && !original.activeSelf,"ghost replaces original while dragging");
                Check((ghost.Find("Visual fit")!=null)==models,"preview uses current model mode");
                Check(Vector3.Distance(ghost.position,GridCoordinates.BottomCenter(p,d,state.Data.room,.25f))<.00001f,"model follows clamped drag");
                Check(state.Data.revision==revision && state.Find("shelf").gx==4,"preview does not commit layout");
                foreach (var collider in ghost.GetComponentsInChildren<Collider>()) Check(!collider.enabled,"preview cannot intercept selection");
                Material allocated=null;
                foreach (var renderer in ghost.GetComponentsInChildren<Renderer>())
                {
                    if (renderer.name=="Placement indicator") continue;
                    var mat=renderer.sharedMaterial; allocated=mat;
                    Check(mat.renderQueue==(int)UnityEngine.Rendering.RenderQueue.Transparent && mat.GetFloat("_ZWrite")==0,"transparent render state");
                    var block=new MaterialPropertyBlock(); renderer.GetPropertyBlock(block);
                    float alpha=block.HasColor("_BaseColor") ? block.GetColor("_BaseColor").a : mat.GetColor("_BaseColor").a;
                    Check(alpha>0 && alpha<1,"model is translucent");
                }
                foreach (var renderer in original.GetComponentsInChildren<Renderer>(true))
                    Check(renderer.sharedMaterial.GetFloat("_Surface")==0,"original materials stay opaque");
                int instance=ghost.GetInstanceID();
                p.gx=6; p.gy=6; view.Preview(p,false);
                Check(host.transform.Find("Drag preview").GetInstanceID()==instance,"reuse ghost while dragging");
                var indicator=new MaterialPropertyBlock(); ghost.Find("Placement indicator").GetComponent<Renderer>().GetPropertyBlock(indicator);
                Check(indicator.GetColor("_BaseColor")==Color.red,"invalid overlap indicator");
                view.ClearPreview();
                Check(original.activeSelf && original.transform.position==originalPosition,"cancel restores original");
                Check(allocated==null,"temporary materials released on cancel");
            }
            var drop=state.Find("shelf").Copy(); drop.gx=6; drop.gy=6;
            view.Preview(drop,true);
            Check(state.Place(drop),"drop commits");
            Check(host.transform.Find("Drag preview")==null,"committed drop clears ghost");
            Check(host.transform.Find("Furniture").GetChild(0).gameObject.activeSelf,"committed furniture visible");
            var invalid=drop.Copy(); invalid.gx=0; invalid.gy=5;
            view.Preview(invalid,false);
            Check(!state.Place(invalid),"overlap with door still rejected"); view.ClearPreview();
            Check(state.Find("shelf").gx==6 && state.Find("shelf").gy==6,"invalid drop keeps last placement");
        }
        finally { UnityEngine.Object.DestroyImmediate(host); }
        Debug.Log("LAYOUT_DRAG_SMOKE_OK");
    }
    static void Check(bool condition,string message) { if (!condition) throw new InvalidOperationException("Smoke check failed: "+message); }
}
