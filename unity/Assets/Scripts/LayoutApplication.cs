using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace FurnitureLayout
{
    public sealed class LayoutApplication : MonoBehaviour
    {
        Text mitigationLabel, scenarioLabel;
        Region[] evaluatedRegions;
        int scenarioIndex;
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
        int screenWidth = -1, screenHeight = -1;
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
            if (panel == null || (screenWidth==Screen.width && screenHeight==Screen.height)) return;
            screenWidth=Screen.width; screenHeight=Screen.height;
            bool wide=Screen.width >= Screen.height;
            panel.anchorMin=Vector2.zero; panel.anchorMax=wide ? new Vector2(.3f,1) : new Vector2(1,.43f);
            panel.offsetMin=panel.offsetMax=Vector2.zero;
            roomCamera.rect=wide ? new Rect(.3f,0,.7f,1) : new Rect(0,.43f,1,.57f);
            scaler.matchWidthOrHeight=wide ? 1 : 0;
        }
        void BuildUI()
        {
            font=Resources.Load<Font>("JapaneseUI");
            if (font==null) font=Font.CreateDynamicFontFromOSFont(
                new[] { "Yu Gothic", "Meiryo", "MS Gothic", "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP", "Droid Sans Japanese" },18);
            var canvasObject=new GameObject("Layout UI",typeof(Canvas),typeof(CanvasScaler),typeof(GraphicRaycaster));
            canvasObject.GetComponent<Canvas>().renderMode=RenderMode.ScreenSpaceOverlay;
            scaler=canvasObject.GetComponent<CanvasScaler>(); scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution=new Vector2(1280,800);
            var events=new GameObject("EventSystem",typeof(EventSystem),typeof(StandaloneInputModule));
            panel=Rect("Panel",canvasObject.transform);
            panel.gameObject.AddComponent<Image>().color=new Color(.075f,.105f,.14f,.98f);
            var scroll=panel.gameObject.AddComponent<ScrollRect>(); scroll.horizontal=false;
            // Wheel/trackpad deltas are in UI units. The default of 1 barely moves a long panel.
            scroll.scrollSensitivity=48;
            scroll.movementType=ScrollRect.MovementType.Clamped;
            var viewport=Rect("Viewport",panel); Stretch(viewport);
            viewport.offsetMax=new Vector2(-22,0);
            viewport.gameObject.AddComponent<RectMask2D>();
            content=Rect("Content",viewport); content.anchorMin=new Vector2(0,1); content.anchorMax=Vector2.one;
            content.pivot=new Vector2(.5f,1); content.offsetMin=content.offsetMax=Vector2.zero;
            var vertical=content.gameObject.AddComponent<VerticalLayoutGroup>();
            vertical.padding=new RectOffset(16,16,18,18); vertical.spacing=8;
            vertical.childControlHeight=true; vertical.childForceExpandHeight=false; vertical.childForceExpandWidth=true;
            content.gameObject.AddComponent<ContentSizeFitter>().verticalFit=ContentSizeFitter.FitMode.PreferredSize;
            scroll.viewport=viewport; scroll.content=content;
            var track=Rect("Scrollbar",panel); track.anchorMin=new Vector2(1,0); track.anchorMax=Vector2.one;
            track.offsetMin=new Vector2(-20,6); track.offsetMax=new Vector2(-4,-6);
            track.gameObject.AddComponent<Image>().color=new Color(.12f,.18f,.23f);
            var scrollbar=track.gameObject.AddComponent<Scrollbar>(); scrollbar.direction=Scrollbar.Direction.BottomToTop;
            var handle=Rect("Handle",track); Stretch(handle);
            var handleImage=handle.gameObject.AddComponent<Image>(); handleImage.color=new Color(.4f,.6f,.68f);
            scrollbar.handleRect=handle; scrollbar.targetGraphic=handleImage;
            scroll.verticalScrollbar=scrollbar;
            scroll.verticalScrollbarVisibility=ScrollRect.ScrollbarVisibility.AutoHide;
            Label("家具の配置と防災",content,26);
            Label("家具を動かして、配置を比較できます。",content,16);
            address=Field(api.BaseUrl,content);
            connectButton=Button("接続",content,()=>StartCoroutine(Connect()));
            selection=Label("家具の一覧を読み込み中…",content);
            evaluateButton=Button("現在の配置を評価",content,()=>StartCoroutine(Evaluate()));
            generateButton=Button("配置候補を3案生成",content,()=>StartCoroutine(Generate()));
            resumeButton=Button("結果の取得を再開",content,()=> { if (!polling && pendingJob != null) StartCoroutine(Poll()); });
            resumeButton.gameObject.SetActive(false);
            discardButton=Button("この探索の結果取得を終了",content,()=>
            {
                if (polling) return;
                FinishJob(); SetStatus("結果の取得を終了しました。編集した配置は保持されています。");
            });
            discardButton.gameObject.SetActive(false);
            candidatePanel=Rect("Candidates",content);
            var group=candidatePanel.gameObject.AddComponent<VerticalLayoutGroup>(); group.spacing=6; group.childForceExpandHeight=false;
            status=Label("接続中…",content,17);
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
                Button(LayoutJapanese.Name(key),controls,()=>Select(key));
            }
            angleLabel=Label("角度：0.0°",controls,16);
            angleSlider=AngleSlider(controls);
            Button("角度を −1°",controls,()=> { input.Rotate(-1); RefreshAngle(); });
            Button("角度を ＋1°",controls,()=> { input.Rotate(1); RefreshAngle(); });
            Button snapButton=null;
            snapButton=Button("壁への吸着：有効",controls,()=>
            {
                input.WallSnapEnabled=!input.WallSnapEnabled;
                snapButton.GetComponentInChildren<Text>().text="壁への吸着："+(input.WallSnapEnabled?"有効":"無効");
            });
            Button("選択した家具を配置から外す",controls,()=> { if (input.SelectedKey != null) state.Remove(input.SelectedKey); });
            Button("探索で動かさない設定を切り替え",controls,()=>
            {
                if (input.SelectedKey == null) return;
                var p=state.Find(input.SelectedKey);
                if (!p.placed) { SetStatus("家具を配置してから「探索で動かさない」を設定してください。"); return; }
                state.SetFixed(p.key,!state.FixedKeys.Contains(p.key)); Select(p.key);
            });
            Button("ドアを移動（移動先の壁をクリック）",controls,()=>SelectOpening("door_1"));
            Button("窓を移動（移動先の壁をクリック）",controls,()=>SelectOpening("window_1"));
            mitigationLabel=Label("防災対策（探索で動かさない設定とは別）",controls,14);
            Button("転倒防止対策の種類を切り替え",controls,()=>
            {
                if (input.SelectedKey!=null) state.CycleRestraint(input.SelectedKey);
                else SetStatus("対策を記録する家具を選んでください。");
            });
            Button("設置状態の確認済み・未確認を切り替え",controls,()=>
            {
                if (input.SelectedKey==null || !state.ToggleInstallationConfirmation(input.SelectedKey))
                    SetStatus("家具を配置し、対策の種類を選んでください。利用者の確認を記録するもので、アプリが強度を確認するものではありません。");
            });
            Button("飛散防止フィルムの有無を切り替え",controls,()=>ChangeWindowProtection(true));
            Button("就寝時のカーテン使用を切り替え",controls,()=>ChangeWindowProtection(false));
            Button("転倒防止対策の公的資料を開く",controls,()=>Application.OpenURL("https://www.tfd.metro.tokyo.lg.jp/content/000010472.pdf#page=14"));
            scenarioLabel=Label("評価後、危険シナリオを1つずつ確認できます。",controls,14);
            Button("次の危険シナリオを表示",controls,()=> { scenarioIndex++; ShowScenario(); });
            Button("天井の家具を表示・非表示",controls,()=> { view.ShowCeiling=!view.ShowCeiling; view.Redraw(); });
            Button("補助グリッドを表示・非表示",controls,()=> { view.ShowGrid=!view.ShowGrid; view.Redraw(); });
            Button("家具モデル・箱表示を切り替え",controls,()=> { view.UseModels=!view.UseModels; view.Redraw(); });
            Label("ドラッグ・タップ：家具を配置\n角度スライダー：自由に回転\n右ドラッグ：視点を回転\n部屋上のホイール：拡大・縮小\n操作パネル上のホイール：スクロール\n2本指：視点回転・ピンチで拡大縮小\n緑の開口部：ドア／青の開口部：窓",controls,15);
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
            angleLabel.text=p==null ? "回転する家具を選んでください" : "角度："+degrees.ToString("F1")+"°";
        }
        IEnumerator Connect()
        {
            if (state != null) { SetStatus("接続済みです。接続先を変更するにはアプリを再起動してください。"); yield break; }
            string url=address.text.Trim().TrimEnd('/');
            if (!Uri.TryCreate(url,UriKind.Absolute,out var uri) || (uri.Scheme!="http" && uri.Scheme!="https"))
            { SetStatus("http:// または https:// で始まるAPIの接続先を入力してください。"); yield break; }
            api.BaseUrl=url; connectButton.interactable=false; SetStatus("接続中…");
            yield return api.Get<Catalog>("catalog",catalog=>
            {
                if (catalog.schema_version!=1 || catalog.furniture==null || catalog.furniture.Length==0 || Math.Abs(catalog.cell_size_m-.25f)>.00001f)
                { SetStatus("家具データの版またはグリッドの大きさが、このアプリに対応していません。"); return; }
                if (!catalog.continuous_placement || catalog.evaluation_version!=2) { SetStatus("更新したPython APIを再起動してください（評価方式の版番号2が必要です）。"); return; }
                state=new LayoutState(catalog); view.Initialize(state); input.State=state; input.FrameRoom();
                state.Changed+=OnEdited;
                AddEditingControls(catalog); Select(catalog.furniture[0].key); SetReady(true);
                address.interactable=false; PlayerPrefs.SetString("layout.api",url); PlayerPrefs.Save();
                SetStatus("家具を選び、床をクリックまたはドラッグして配置してください。\n未配置のまま候補を生成することもできます。");
            },SetStatus);
            connectButton.interactable=state==null;
        }
        void SetReady(bool ready) { evaluateButton.interactable=ready; generateButton.interactable=ready; }
        void Select(string key)
        {
            input.SelectedKey=key; input.SelectedOpening=null; view.SelectedKey=key; view.Redraw();
            RefreshAngle();
            selection.text=LayoutJapanese.Name(key)+(state.FixedKeys.Contains(key) ? "［探索で動かさない］" : "［探索で移動可能］");
            RefreshMitigation();
        }
        void SelectOpening(string key)
        {
            input.SelectedOpening=key; input.SelectedKey=null; view.SelectedKey=null; view.Redraw();
            selection.text=LayoutJapanese.Name(key)+"：移動先の壁をクリックしてください"; RefreshAngle();
            RefreshMitigation();
        }
        void OnEdited()
        {
            RefreshAngle();
            RefreshMitigation();
            evaluatedRegions=null;
            if (scenarioLabel!=null) scenarioLabel.text="配置が変わりました。評価して危険を確認してください。";
            if (evaluationRevision>=0 && evaluationRevision!=state.Data.revision)
                SetStatus("配置が変わりました。表示中の評価は変更前のものです。再評価してください。");
            if (jobLayout!=null && jobLayout.revision!=state.Data.revision)
                foreach (var text in candidatePanel.GetComponentsInChildren<Text>())
                    if (!text.text.Contains("変更前の配置")) text.text+="（変更前の配置）";
        }
        IEnumerator Evaluate()
        {
            if (state==null) yield break;
            var snapshot=state.Data.Copy(); int serial=++evaluationSerial;
            evaluateButton.interactable=false; SetStatus("評価中…");
            yield return api.Post<Evaluation>("evaluate",snapshot,result=>
            {
                if (serial!=evaluationSerial) return;
                if (result.schema_version!=1 || result.evaluation_version!=2 || result.safety==null || result.revision!=snapshot.revision) { SetStatus("評価結果が要求内容と一致しません。再評価してください。"); return; }
                evaluationRevision=result.revision;
                SetStatus((result.revision!=state.Data.revision ? "変更前の配置の評価です。再評価してください。\n" : "")+
                    LayoutJapanese.EvaluationText(result));
                if (result.revision==state.Data.revision) { evaluatedRegions=result.regions; scenarioIndex=0; ShowScenario(); }
            },SetStatus);
            evaluateButton.interactable=true;
        }
        IEnumerator Generate()
        {
            if (state==null || polling || pendingJob!=null) yield break;
            jobLayout=state.Data.Copy();
            var request=new OptimizationRequest { layout=jobLayout, fixed_keys=state.FixedKeys.OrderBy(k=>k).ToArray() };
            generateButton.interactable=false; SetStatus("配置候補の探索を依頼中…");
            foreach (Transform child in candidatePanel) Destroy(child.gameObject);
            yield return api.Post<OptimizationJob>("optimization-jobs",request,job=>
            {
                if (job.schema_version!=1 || job.revision!=jobLayout.revision || string.IsNullOrEmpty(job.id))
                { SetStatus("探索の応答を読み取れませんでした。再実行してください。"); return; }
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
                    SetStatus(failure+"\n編集内容は保持されています。結果の取得を再開するか、この探索の結果取得を終了してください。");
                    resumeButton.gameObject.SetActive(true); discardButton.gameObject.SetActive(true); polling=false; yield break;
                }
                if (result.schema_version!=1 || result.id!=pendingJob || result.revision!=jobLayout.revision)
                { SetStatus("探索結果が要求内容と一致しません。再実行してください。"); FinishJob(); yield break; }
                if (result.status=="failed") { Debug.LogWarning(result.error); SetStatus(LayoutJapanese.ServerError(result.error)); FinishJob(); yield break; }
                if (result.status=="succeeded")
                {
                    bool older=result.revision!=state.Data.revision;
                    SetStatus(older ? "変更前の配置に基づく候補です。適用すると家具の位置を変更します。現在のドア・窓の位置を保持して再確認します。" : "適用する候補を選んでください。");
                    int valid=0;
                    foreach (var candidate in result.candidates ?? Array.Empty<Candidate>())
                    {
                        var value=candidate;
                        var button=Button($"候補 {++valid} を適用\n{value.safety?.Summary ?? "安全条件は未評価です"}"+(older ? "（変更前の配置）" : ""),candidatePanel,()=>
                        {
                            // Fixed keys currently selected by the user must still be respected.
                            foreach (var key in state.FixedKeys)
                            {
                                var current=state.Find(key); var proposed=Array.Find(value.placements,p=>p.key==key);
                                if (proposed==null || current.gx!=proposed.gx || current.gy!=proposed.gy || current.rotation!=proposed.rotation)
                                { SetStatus("「探索で動かさない」家具を変更する候補です。設定を解除するか、候補を再生成してください。"); return; }
                            }
                            if (state.Apply(value)) StartCoroutine(Evaluate());
                            else SetStatus("現在の部屋に配置できない候補です。候補を再生成してください。");
                        });
                        button.interactable=value.valid && value.evaluation_version==2;
                    }
                    if (result.candidates==null || !result.candidates.Any(c=>c.valid)) SetStatus("配置できる候補が見つかりませんでした。部屋や探索で動かさない家具を見直すか、再探索してください。");
                    else if (!result.candidates.Any(c=>c.safety!=null && c.safety.status=="met"))
                        SetStatus("今回評価した条件をすべて満たす候補は見つかりませんでした。表示中の候補には未達の条件が残っています。条件を満たす配置が存在しないと断定するものではありません。適用時に現在の部屋と対策情報で再評価します。");
                    FinishJob(); yield break;
                }
                SetStatus(LayoutJapanese.JobStatus(result.status)+"。配置の編集を続けられます。");
                yield return new WaitForSecondsRealtime(1);
            }
            polling=false;
        }
        void ChangeWindowProtection(bool film)
        {
            if (input.SelectedOpening==null || !state.Data.room.windows.Any(w=>w.key==input.SelectedOpening))
            { SetStatus("「窓を移動」を選んでから、窓の対策を記録してください。"); return; }
            state.CycleWindowProtection(input.SelectedOpening,film);
        }
        void RefreshMitigation()
        {
            if (mitigationLabel==null || state==null) return;
            var p=input.SelectedKey==null?null:state.Find(input.SelectedKey);
            if (p!=null)
            {
                string guidance=p.restraint=="wall_bracket" || p.restraint=="belt" ? "壁の下地と家具の強度、器具の取付条件を確認してください。" :
                    p.restraint=="pole" || p.restraint=="pole_combination" ? "天井の強度と補助器具の組合せ・設置条件を確認してください。" : "器具の説明書と設置条件を確認してください。";
                mitigationLabel.text=$"転倒防止対策：{LayoutJapanese.Restraint(p.restraint)}\n設置状態：{LayoutJapanese.Installation(p.installation_confirmed)}\n{guidance}\n「探索で動かさない」とは別の設定です。";
                return;
            }
            var w=Array.Find(state.Data.room.windows,o=>o.key==input.SelectedOpening);
            mitigationLabel.text=w==null?"家具または窓を選ぶと対策を記録できます。":$"{LayoutJapanese.Name(w.key)}：飛散防止フィルム {LayoutJapanese.Protection(w.film)}\n就寝時のカーテン：{LayoutJapanese.Protection(w.curtains)}\n対策の有無で安全な距離は決まりません。";
        }
        void ShowScenario()
        {
            if (evaluatedRegions==null) return;
            var hazards=evaluatedRegions.Where(r=>r.kind=="fall" || r.kind=="drop").ToArray();
            Region chosen=hazards.Length==0?null:hazards[scenarioIndex%hazards.Length];
            scenarioLabel.text=chosen==null?"評価対象の転倒・落下源はありません。":
                $"危険シナリオ {scenarioIndex%hazards.Length+1}/{hazards.Length}：{LayoutJapanese.Name(chosen.key)}・{LayoutJapanese.Direction(chosen.direction)}\n{(chosen.primary?"主要":"補助")}シナリオ（それぞれ個別に評価）";
            view.ShowRegions(evaluatedRegions.Where(r=>r.kind!="fall" && r.kind!="drop" || r==chosen).ToArray());
        }
        void FinishJob() { pendingJob=null; polling=false; generateButton.interactable=true; resumeButton.gameObject.SetActive(false); discardButton.gameObject.SetActive(false); }
        void SetStatus(string message) { if (status != null) status.text=message ?? "原因不明のエラーが発生しました。"; }
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
            var layout=rect.gameObject.AddComponent<LayoutElement>();
            layout.preferredHeight=label.Contains("\n") ? 88 : 48; layout.minHeight=layout.preferredHeight;
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
