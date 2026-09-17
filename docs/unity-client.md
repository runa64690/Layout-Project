# UnityクライアントとPython API

Unityが配置編集・3D表示、Pythonが評価・MCMCを担当します。Pythonの既存UIも同じ `layout_service` を呼びます。既存の評価ルール変更は維持しています。扉前・窓周辺の表示領域は `layout_geometry` に分離しており、領域が表示されること自体は、その領域が現在の評価項目に含まれることを意味しません。

## 起動

リポジトリルートで実行します。APIだけなら、Matplotlib・ProcTHORなどのインストールは不要です。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-api.txt
.venv/Scripts/python.exe -m uvicorn api:app --app-dir src --host 127.0.0.1 --port 8000 --workers 1
```

既に `.venv` がある場合、仮想環境作成は省略します。API仕様は `http://127.0.0.1:8000/docs`、実際の入出力例は [contracts](../contracts/) にあります。

1. Unity Hubで **Unity 6000.3.6f1** のライセンスを有効にする。
2. このリポジトリの `unity` フォルダーをプロジェクトとして開く。
3. パッケージ読込後、メニュー **Layout → Setup project** を実行する。
4. `Assets/Scenes/Layout.unity` を開き、Playを押す。
5. 初期API接続先は `http://127.0.0.1:8000`。接続に失敗した場合は画面のURLを修正し、Connectを押す。

SetupはURP設定・実行シーン・描画マテリアル・モデルライブラリ・サンプル本棚Prefabを作成します。既に存在するこれらのアセットは上書きしません。生成された `Assets/Settings`、`Assets/Scenes`、`Assets/Resources`、`Assets/Models` と `.meta` はコミット対象です。`Library` やビルド成果物は対象外です。

既存のPython UIは引き続き `python src/main.py` で起動します。

## 操作

- 家具名を選び、床面をクリック／タップして配置。配置済み家具をドラッグして移動。
- Rotateで90度回転。緑のプレビューは配置可能、赤は重なり・部屋外・扉前の制約違反。
- Removeで未配置に戻す。Toggle fixedで候補生成時に動かさない家具を指定。
- Move door／Move windowを選び、壁付近をクリックして開口部を移動。扉は緑、窓は青。
- マウス右ドラッグでカメラ回転、ホイールで拡大縮小。スマホは2本指の移動・ピンチで操作。
- Ceilingボタンで天井家具の表示を切り替え。床面と天井では家具の重なりを別々に扱う。
- Evaluateで配置を評価。Generateで未配置家具も含めた候補を生成。最初からGenerateを押してもよい。
- 結果はApplyを押したときだけ適用。計算中の編集は止めない。
- 通信失敗時も配置を保持。候補取得中の失敗はResumeで同じジョブを再取得、Discardで結果待ちを解除。

Discardはサーバーの計算を強制停止しません。ジョブは終了後に期限切れになります。再起動後の配置保存・復元は初期版の対象外です。

## データ契約

`schema_version: 1`。グリッドは25cm、回転は `0..3`（北→東→南→西）。

| 対象 | フィールドと規則 |
|---|---|
| 部屋 | `grid_w`, `grid_h` は4～64セル。`ceiling_height_m` は表示用の天井高さ、初期値2.5m |
| 開口部 | `key`, `label`, `wall`, `offset`, `length`, `placed`。壁はLEFT/RIGHT/TOP/BOTTOM |
| 家具 | `key`, `gx`, `gy`, `rotation`, `placed`。初期版はカタログ1種類につき1個 |
| 座標 | `gx,gy` は回転後の占有矩形の左下。UnityのX,Zに変換。UnityのYが高さ |
| 未配置 | `placed:false`。Unityは座標を整数0として送信し、Pythonアダプターが未配置へ変換 |
| 版番号 | `revision` は編集ごとに増加し、評価・ジョブ応答にも返す |
| 評価内訳 | `[{"name":"...","value":...}]`。Unity JsonUtilityで扱える配列形式 |
| 表示領域 | `kind,key,x0,y0,x1,y1`。グリッドの端点座標。表示時に部屋内へクリップ |

評価APIは要求内の家具がすべて配置済みであることを求めます。家具セットは現在のカタログの部分集合でも構いません。未知の家具、重複ID、壁開口の重なり、不正な座標・回転などは422を返します。家具モデルIDやメッシュは配置・評価要求に含めません。

### API

| メソッド | パス | 応答 |
|---|---|---|
| GET | `/api/v1/catalog` | 家具定義・評価ルール・モデルID |
| POST | `/api/v1/evaluate` | 合計・内訳・違反・転倒重複セル数・表示領域 |
| POST | `/api/v1/optimization-jobs` | 202とジョブID・対象revision |
| GET | `/api/v1/optimization-jobs/{id}` | queued/running/succeeded/failedと候補 |

候補生成の既定値は候補3個、900ステップ、burn-in 250、間隔15。APIのシード省略時は非固定、Unity UIは再現しやすいよう42を送ります。候補は確率的探索のため要求数より少ない場合があります。幾何制約違反の候補は `valid:false` として返し、UnityではApplyできません。

移動可能な家具に幾何制約違反があっても候補生成要求は受け付けます。固定家具の違反は事前に拒否します。候補の順序・スコアは既存MCMCを維持します。新規配置プレビューは既存Tkinterと同じ扉前制約を持ち、候補適用時は既存評価と同じ確定制約を確認します。

古い評価は「OLDER LAYOUT」と表示し、現配置に領域を重ねません。古い候補をApplyする場合は現在の部屋・扉・窓を維持して位置の適合を再確認し、現在固定されている家具を変更する候補は拒否します。

### ワーカー運用

APIは **`--workers 1`** で起動します。内部の `ProcessPoolExecutor` は2プロセス、ジョブ記録は最大32件です。ジョブはメモリに保持し、完了を確認してから1時間で期限切れになります。満杯なら古い完了記録から削除して新しい要求を受け付け、32件すべて処理中の場合は503を返します。消失・期限切れは404、計算失敗は `status:failed` です。APIを再起動するとジョブ記録は失われます。

初期版はローカル開発・小規模な試験用です。複数APIプロセスへの拡張時はジョブストアとキューを共有サービスへ移してから増やします。Unityへの秘密鍵埋込みは行いません。外部公開のための認証・アカウント保存・課金管理は実装範囲に含みません。

## 3Dモデル差し替え

1. FBXなどのモデルをUnityへインポートし、URPのマテリアルを設定してPrefabにする。
2. `Assets/Resources/ModelLibrary.asset` にEntryを追加する。
3. APIカタログの `model_id` と同じID（例：`shelf`）とPrefabを指定する。
4. 必要なら `rotationCorrection` でモデルの上方向・正面を補正する。

モデルのRendererの境界をカタログの回転前寸法へ合わせ、底面中心を配置基準に揃えます。見た目側のColliderは無効化し、選択には別のカタログ寸法のBoxColliderを使います。物理シミュレーション用のスクリプトやRigidbodyを含まない表示用Prefabを使ってください。ルートの正面は+Zです。ベッドの枕方向などはカタログ定義と合うようにPrefabを作成します。

未知のモデルID・境界を取得できないモデルは箱で表示します。Models / boxesボタンで表示を比較できます。同梱本棚は差し替え検証用の簡単な形状であり、精細な製品モデルは別途インポートしてください。

## Web・Androidビルド

Unity Hubから同じEditorバージョン用の **Web Build Support** と **Android Build Support（SDK/NDK/OpenJDK含む）** を追加します。

- **Layout → Build Web**：`unity/Builds/Web` に開発ビルドを生成。
- **Layout → Build Android development APK**：`unity/Builds/Android/Layout.apk` にARM64開発APKを生成。
- AndroidはAPI 26以上、URP共通設定。端末では30fpsを目標値として指定（性能保証値ではない）。
- 画面は横向きで左パネル、縦向きで下パネルに切り替え、パネル内をスクロール可能。

配布前に `Assets/Resources/ApiConfig.json` の `base_url` を端末から到達可能なHTTPSのAPIへ変更します。`127.0.0.1` は実機ではそのスマホ自身を指します。開発中にPCへ接続する場合はAPIを `--host 0.0.0.0` で起動し、PCのLANアドレスを使います。HTTPはUnityの開発ビルドのみ許可します。

Web成果物はHTTPサーバーから配信します（HTMLをファイルとして直接開かない）。配信サーバーはUnity出力に対応するMIME・圧縮ヘッダーを設定してください。HTTPSのページからはHTTPSのAPIを呼びます。APIを別オリジンにする場合は、起動前に許可オリジンを指定します。

```powershell
$env:LAYOUT_CORS_ORIGINS = 'https://layout.example.com,http://localhost:8080'
```

WebのCORS・非同期通信は [Unity公式Web通信仕様](https://docs.unity3d.com/6000.3/Documentation/Manual/webgl-networking.html) に従います。URP設定の参考は [Unity公式URP導入手順](https://docs.unity3d.com/6000.3/Documentation/Manual/urp/InstallURPIntoAProject.html) です。

リリースAPK/AABの署名・ストア公開やWebへの実際のデプロイは行っていません。製品版はBuild ProfilesでDevelopment Buildを解除し、配布先に応じた設定・署名を行います。

## 検証

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/export-contracts.py
powershell -NoProfile -File scripts/check-unity-compile.ps1
powershell -NoProfile -File scripts/run-unity.ps1
```

最後のコマンドは非表示のUnityバッチ実行を起動してPIDを返します。終了と `outputs/LayoutProjectSetup.SmokeChecks.log` の `LAYOUT_SMOKE_OK` を確認してください。C#静的コンパイルはEditorの実行・レンダリング・Android/Webビルドの代わりにはなりません。

実機・ブラウザーでの受入確認：

1. 初期部屋で候補を生成し、Apply → Evaluateまで実行する。
2. 固定家具を指定し、再生成しても位置が変わらないことを確認する。
3. 四方向に家具を回転し、寸法・枕方向・領域表示が一致することを確認する。
4. 扉・窓を各壁へ移し、境界・重なり・開口部のブロックを確認する。
5. 床と天井の同位置への配置と、天井家具の表示切替を確認する。
6. Models / boxesを切り替えてもEvaluateの値が変わらないことを確認する。
7. API通信を切り、編集を保持したまま失敗を表示し、復旧後Resumeできることを確認する。
8. 計算中に配置を編集し、古い結果の表示・明示的な候補適用を確認する。
9. Androidの縦横画面、マウス・タッチ、起動時間・メモリ・描画速度を測定する。

2026-09-09の確認では、Pythonの45テスト（Windowsの別プロセス実行を含む）と、実際のUnityアセンブリを参照したC#静的コンパイルが通りました。

この環境ではUnity Editorライセンスが未認証で、Webモジュールも未インストールでした。そのためEditorでの描画、Web/Androidビルド、Android実機の受入確認は未実施です。
