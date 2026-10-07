using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace FurnitureLayout
{
    public sealed class LayoutApplication : MonoBehaviour
    {
        LayoutState state;
        LayoutApiClient api;
        LayoutRenderer view;
        LayoutInput input;
        Camera roomCamera;
        Text status, selection, angleLabel;
        Slider angleSlider;
        InputField address;
        RectTransform panel, content;
        CanvasScaler scaler;
        Transform candidatePanel;
        Button generateButton, evaluateButton, connectButton, resumeButton, discardButton;
        string pendingJob;
        LayoutData jobLayout;
        int evaluationRevision = -1, evaluationSerial;
        bool polling;
        Font font;
        [Serializable] class ApiConfig { public string base_url = "http://127.0.0.1:8000"; }

        void Start()
        {
            Application.targetFrameRate = Application.isMobilePlatform ? 30 : 60;
            api=gameObject.AddComponent<LayoutApiClient>();
            var config=Resources.Load<TextAsset>("ApiConfig");
            if (config != null) api.BaseUrl=JsonUtility.FromJson<ApiConfig>(config.text).base_url;
            api.BaseUrl=PlayerPrefs.GetString("layout.api",api.BaseUrl);
            roomCamera=Camera.main;
            view=gameObject.AddComponent<LayoutRenderer>();
            input=gameObject.AddComponent<LayoutInput>(); input.Camera=roomCamera; input.View=view;
            input.SelectionChanged=Select; input.Message=SetStatus;
            BuildUI();
            StartCoroutine(Connect());
        }
        void Update()
        {
            if (panel == null) return;
            bool wide=Screen.width >= Screen.height;
            panel.anchorMin=Vector2.zero; panel.anchorMax=wide ? new Vector2(.3f,1) : new Vector2(1,.43f);
            panel.offsetMin=panel.offsetMax=Vector2.zero;
            roomCamera.rect=wide ? new Rect(.3f,0,.7f,1) : new Rect(0,.43f,1,.57f);
            scaler.matchWidthOrHeight=wide ? 1 : 0;
        }
        void BuildUI()
        {
            font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var canvasObject=new GameObject("Layout UI",typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));
            canvasObject.GetComponent<Canvas>().renderMode=RenderMode.ScreenSpaceOverlay;
            scaler=canvasObject.GetComponent<CanvasScaler>(); scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution=new Vector2(1280,800);
            var events=new GameObject("EventSystem",typeof(EventSystem),typeof(StandaloneInputModule));
            panel=Rect("Panel",canvasObject.transform);
            panel.gameObject.AddComponent<Image>().color=new Color(.075f,.105f,.14f,.98f);
            var scroll=panel.gameObject.AddComponent<ScrollRect>(); scroll.horizontal=false;
            var viewport=Rect("Viewport",panel); Stretch(viewport);
            viewport.gameObject.AddComponent<RectMask2D>();
            content=Rect("Content",viewport); content.anchorMin=new Vector2(0,1); content.anchorMax=Vector2.one;
            content.pivot=new Vector2(.5f,1); content.offsetMin=content.offsetMax=Vector2.zero;
            var vertical=content.gameObject.AddComponent<VerticalLayoutGroup>();
            vertical.padding=new RectOffset(16,16,18,18); vertical.spacing=8;
            vertical.childControlHeight=true; vertical.childForceExpandHeight=false; vertical.childForceExpandWidth=true;
            content.gameObject.AddComponent<ContentSizeFitter>().verticalFit=ContentSizeFitter.FitMode.PreferredSize;
            scroll.viewport=viewport; scroll.content=content;
            Label("ROOM / LAYOUT",content,26);
            Label("Move furniture. Compare layouts.",content,16);
            address=Field(api.BaseUrl,content);
            connectButton=Button("Connect",content,()=>StartCoroutine(Connect()));
            selection=Label("Loading furniture catalog...",content);
            evaluateButton=Button("Evaluate",content,()=>StartCoroutine(Evaluate()));
            generateButton=Button("Generate 3 candidates",content,()=>StartCoroutine(Generate()));
            resumeButton=Button("Resume result retrieval",content,()=> { if (!polling && pendingJob != null) StartCoroutine(Poll()); });
            resumeButton.gameObject.SetActive(false);
            discardButton=Button("Discard search / start again",content,()=>
            {
                if (polling) return;
                FinishJob(); SetStatus("Search detached. Your edited layout is kept.");
            });
            discardButton.gameObject.SetActive(false);
            candidatePanel=Rect("Candidates",content);
            var group=candidatePanel.gameObject.AddComponent<VerticalLayoutGroup>(); group.spacing=6; group.childForceExpandHeight=false;
            status=Label("Connecting...",content,17);
            SetReady(false);
        }
        void AddEditingControls(Catalog catalog)
        {
            // Insert editing controls before evaluation actions in the scroll panel.
            var controls=Rect("Editing",content); controls.SetSiblingIndex(selection.transform.GetSiblingIndex()+1);
            var group=controls.gameObject.AddComponent<VerticalLayoutGroup>(); group.spacing=6; group.childForceExpandHeight=false;
            foreach (var definition in catalog.furniture)
            {
                string key=definition.key;
                Button(definition.label,controls,()=>Select(key));
            }
            angleLabel=Label("Angle: 0.0 degrees",controls,16);
            angleSlider=AngleSlider(controls);
            Button("Rotate -1 degree",controls,()=> { input.Rotate(-1); RefreshAngle(); });
            Button("Rotate +1 degree",controls,()=> { input.Rotate(1); RefreshAngle(); });
            Button("Remove selected",controls,()=> { if (input.SelectedKey != null) state.Remove(input.SelectedKey); });
            Button("Toggle fixed for search",controls,()=>
            {
                if (input.SelectedKey == null) return;
                var p=state.Find(input.SelectedKey);
                if (!p.placed) { SetStatus("Place furniture before fixing it for search."); return; }
                state.SetFixed(p.key,!state.FixedKeys.Contains(p.key)); Select(p.key);
            });
            Button("Move door (click wall)",controls,()=>SelectOpening("door_1"));
            Button("Move window (click wall)",controls,()=>SelectOpening("window_1"));
            Button("Show / hide ceiling furniture",controls,()=> { view.ShowCeiling=!view.ShowCeiling; view.Redraw(); });
            Button("Show / hide reference grid",controls,()=> { view.ShowGrid=!view.ShowGrid; view.Redraw(); });
            Button("Models / boxes",controls,()=> { view.UseModels=!view.UseModels; view.Redraw(); });
            Label("Drag / tap: free placement\nAngle slider: rotate freely\nRight drag: orbit | Wheel: zoom\nTwo fingers: orbit and pinch to zoom\nGreen wall: door | Blue wall: window",controls,15);
        }
        Slider AngleSlider(Transform parent)
        {
            var root=Rect("Angle slider",parent);
            root.gameObject.AddComponent<LayoutElement>().preferredHeight=36;
            var background=root.gameObject.AddComponent<Image>(); background.color=new Color(.2f,.27f,.34f);
            var slider=root.gameObject.AddComponent<Slider>(); slider.minValue=0; slider.maxValue=360; slider.wholeNumbers=false;
            var area=Rect("Handle area",root); Stretch(area); area.offsetMin=new Vector2(12,0); area.offsetMax=new Vector2(-12,0);
            var handle=Rect("Handle",area); handle.sizeDelta=new Vector2(22,0);
            var graphic=handle.gameObject.AddComponent<Image>(); graphic.color=new Color(.3f,.8f,.85f);
            slider.handleRect=handle; slider.targetGraphic=graphic;
            slider.onValueChanged.AddListener(degrees=> { input.SetAngle(degrees); RefreshAngle(); });
            return slider;
        }
        void RefreshAngle()
        {
            if (angleSlider==null || state==null) return;
            var p=input.SelectedKey==null ? null : state.Find(input.SelectedKey);
            angleSlider.interactable=p!=null;
            float degrees=p==null ? 0 : p.rotation*90;
            angleSlider.SetValueWithoutNotify(degrees);
            angleLabel.text=p==null ? "Select furniture to rotate" : "Angle: "+degrees.ToString("F1")+" degrees";
        }
        IEnumerator Connect()
        {
            if (state != null) { SetStatus("Catalog is connected. Restart to change the server."); yield break; }
            string url=address.text.Trim().TrimEnd('/');
            if (!Uri.TryCreate(url,UriKind.Absolute,out var uri) || (uri.Scheme!="http" && uri.Scheme!="https"))
            { SetStatus("Enter an http:// or https:// API address."); yield break; }
            api.BaseUrl=url; connectButton.interactable=false; SetStatus("Connecting...");
            yield return api.Get<Catalog>("catalog",catalog=>
            {
                if (catalog.schema_version!=1 || catalog.furniture==null || catalog.furniture.Length==0 || Math.Abs(catalog.cell_size_m-.25f)>.00001f)
                { SetStatus("Unsupported catalog version or grid size."); return; }
                if (!catalog.continuous_placement) { SetStatus("Restart the updated Python API to enable free placement and rotation."); return; }
                state=new LayoutState(catalog); view.Initialize(state); input.State=state; input.FrameRoom();
                state.Changed+=OnEdited;
                AddEditingControls(catalog); Select(catalog.furniture[0].key); SetReady(true);
                address.interactable=false; PlayerPrefs.SetString("layout.api",url); PlayerPrefs.Save();
                SetStatus("Select furniture, then click or drag on the floor.\nOr generate candidates for the empty room.");
            },SetStatus);
            connectButton.interactable=state==null;
        }
        void SetReady(bool ready) { evaluateButton.interactable=ready; generateButton.interactable=ready; }
        void Select(string key)
        {
            input.SelectedKey=key; input.SelectedOpening=null; view.SelectedKey=key; view.Redraw();
            RefreshAngle();
            selection.text=state.Catalog.Find(key).label+(state.FixedKeys.Contains(key) ? " [fixed]" : " [movable]");
        }
        void SelectOpening(string key)
        {
            input.SelectedOpening=key; input.SelectedKey=null; view.SelectedKey=null; view.Redraw();
            selection.text=key+": click a wall to move"; RefreshAngle();
        }
        void OnEdited()
        {
            RefreshAngle();
            if (evaluationRevision>=0 && evaluationRevision!=state.Data.revision)
                SetStatus("Layout changed. Previous evaluation is for an older layout; evaluate again.");
            if (jobLayout!=null && jobLayout.revision!=state.Data.revision)
                foreach (var text in candidatePanel.GetComponentsInChildren<Text>())
                    if (!text.text.Contains("older layout")) text.text+=" (older layout)";
        }
        IEnumerator Evaluate()
        {
            if (state==null) yield break;
            var snapshot=state.Data.Copy(); int serial=++evaluationSerial;
            evaluateButton.interactable=false; SetStatus("Evaluating...");
            yield return api.Post<Evaluation>("evaluate",snapshot,result=>
            {
                if (serial!=evaluationSerial) return;
                if (result.schema_version!=1 || result.revision!=snapshot.revision) { SetStatus("Evaluation response does not match the request."); return; }
                evaluationRevision=result.revision;
                var text=new StringBuilder();
                if (result.revision!=state.Data.revision) text.AppendLine("OLDER LAYOUT — evaluate again.");
                text.AppendLine($"Total cost: {result.total:F3}");
                foreach (var term in result.breakdown) text.AppendLine($"{term.name}: {term.value:F3}");
                text.AppendLine($"Fall overlap cells: {result.fall_overlap_cells}");
                foreach (var violation in result.violations) text.AppendLine("• "+violation);
                SetStatus(text.ToString());
                if (result.revision==state.Data.revision) view.ShowRegions(result.regions);
            },SetStatus);
            evaluateButton.interactable=true;
        }
        IEnumerator Generate()
        {
            if (state==null || polling || pendingJob!=null) yield break;
            jobLayout=state.Data.Copy();
            var request=new OptimizationRequest { layout=jobLayout, fixed_keys=state.FixedKeys.OrderBy(k=>k).ToArray() };
            generateButton.interactable=false; SetStatus("Submitting candidate search...");
            foreach (Transform child in candidatePanel) Destroy(child.gameObject);
            yield return api.Post<OptimizationJob>("optimization-jobs",request,job=>
            {
                if (job.schema_version!=1 || job.revision!=jobLayout.revision || string.IsNullOrEmpty(job.id))
                { SetStatus("Invalid search response."); return; }
                pendingJob=job.id;
            },SetStatus);
            if (pendingJob!=null) yield return Poll();
            else generateButton.interactable=true;
        }
        IEnumerator Poll()
        {
            polling=true; resumeButton.gameObject.SetActive(false); discardButton.gameObject.SetActive(false);
            while (pendingJob!=null)
            {
                OptimizationJob result=null; string failure=null;
                yield return api.Get<OptimizationJob>("optimization-jobs/"+pendingJob,job=>result=job,error=>failure=error);
                if (failure!=null)
                {
                    SetStatus(failure+"\nEdits are kept. Resume retrieval, or discard this search.");
                    resumeButton.gameObject.SetActive(true); discardButton.gameObject.SetActive(true); polling=false; yield break;
                }
                if (result.schema_version!=1 || result.id!=pendingJob || result.revision!=jobLayout.revision)
                { SetStatus("Search response does not match the request."); FinishJob(); yield break; }
                if (result.status=="failed") { SetStatus(result.error); FinishJob(); yield break; }
                if (result.status=="succeeded")
                {
                    bool older=result.revision!=state.Data.revision;
                    SetStatus(older ? "Candidates use an older layout. Applying one replaces furniture positions; current door/window positions are kept and checked." : "Choose a candidate to apply it.");
                    int valid=0;
                    foreach (var candidate in result.candidates ?? Array.Empty<Candidate>())
                    {
                        var value=candidate;
                        var button=Button($"Apply candidate {++valid} — {value.cost:F2}"+(older ? " (older layout)" : ""),candidatePanel,()=>
                        {
                            // Fixed keys currently selected by the user must still be respected.
                            foreach (var key in state.FixedKeys)
                            {
                                var current=state.Find(key); var proposed=Array.Find(value.placements,p=>p.key==key);
                                if (proposed==null || current.gx!=proposed.gx || current.gy!=proposed.gy || current.rotation!=proposed.rotation)
                                { SetStatus("Candidate changes currently fixed furniture. Unfix it or generate again."); return; }
                            }
                            if (state.Apply(value)) StartCoroutine(Evaluate());
                            else SetStatus("Candidate conflicts with the current room or has invalid geometry. Generate again.");
                        });
                        button.interactable=value.valid;
                    }
                    if (result.candidates==null || !result.candidates.Any(c=>c.valid)) SetStatus("No valid candidates found. Change the room/fixed furniture or try again.");
                    FinishJob(); yield break;
                }
                SetStatus("Search "+result.status+". You can keep editing.");
                yield return new WaitForSecondsRealtime(1);
            }
            polling=false;
        }
        void FinishJob() { pendingJob=null; polling=false; generateButton.interactable=true; resumeButton.gameObject.SetActive(false); discardButton.gameObject.SetActive(false); }
        void SetStatus(string message) { if (status != null) status.text=message ?? "Unknown error"; }
        static RectTransform Rect(string name,Transform parent)
        {
            var rect=new GameObject(name,typeof(RectTransform)).GetComponent<RectTransform>(); rect.SetParent(parent,false); return rect;
        }
        static void Stretch(RectTransform rect) { rect.anchorMin=Vector2.zero; rect.anchorMax=Vector2.one; rect.offsetMin=rect.offsetMax=Vector2.zero; }
        Text Label(string value,Transform parent,int size=18)
        {
            var rect=Rect("Text",parent); var text=rect.gameObject.AddComponent<Text>();
            text.text=value; text.font=font; text.fontSize=size; text.color=new Color(.91f,.94f,.97f); text.raycastTarget=false;
            text.horizontalOverflow=HorizontalWrapMode.Wrap; text.verticalOverflow=VerticalWrapMode.Truncate;
            return text;
        }
        Button Button(string label,Transform parent,UnityEngine.Events.UnityAction action)
        {
            var rect=Rect(label,parent); rect.gameObject.AddComponent<Image>().color=new Color(.16f,.25f,.32f);
            var layout=rect.gameObject.AddComponent<LayoutElement>(); layout.preferredHeight=42; layout.minHeight=42;
            var button=rect.gameObject.AddComponent<Button>(); button.onClick.AddListener(action);
            var text=Label(label,rect,17); Stretch(text.rectTransform); text.alignment=TextAnchor.MiddleCenter;
            return button;
        }
        InputField Field(string value,Transform parent)
        {
            var rect=Rect("API address",parent); rect.gameObject.AddComponent<Image>().color=new Color(.12f,.18f,.23f);
            rect.gameObject.AddComponent<LayoutElement>().preferredHeight=42;
            var field=rect.gameObject.AddComponent<InputField>(); var text=Label(value,rect,16); Stretch(text.rectTransform);
            text.rectTransform.offsetMin=new Vector2(8,0); text.rectTransform.offsetMax=new Vector2(-8,0);
            text.alignment=TextAnchor.MiddleLeft; field.textComponent=text; field.text=value;
            return field;
        }
    }
}
