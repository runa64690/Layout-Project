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
        Debug.Log("LAYOUT_SMOKE_OK");
    }
    static void Check(bool condition,string message) { if (!condition) throw new InvalidOperationException("Smoke check failed: "+message); }
}
