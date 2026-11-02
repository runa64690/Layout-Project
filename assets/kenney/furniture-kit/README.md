# Kenney Furniture Kit

Furniture Kit **2.0**（配布物の作成日時: 2018-10-20）。配布元はKenneyです。同梱の [License.txt](License.txt) に **CC0** と記載され、個人・教育・商用利用が許可されています。クレジットは任意です。

## 配置とGit管理

| 場所 | 内容 | Git管理 |
| --- | --- | --- |
| `License.txt` | 配布物に同梱されたライセンス原文 | 対象 |
| `README.md` | 配置・利用手順 | 対象 |
| `source/Models/GLTF format/` | 家具140種類のGLB | 対象外（手元で選定するための配布物） |
| `source/Models/` のその他の形式 | FBX、DAE、OBJ・MTL、STL | 対象外 |
| `source/Isometric/`、`source/Side/` | 家具の確認用画像 | 対象外 |
| `source/Preview.png`、`source/Sample.png`、`source/*.url` | プレビューと配布元へのショートカット | 対象外 |
| プロジェクトの `web/public/models/*.glb` | アプリで採用したGLB | 対象外 |
| プロジェクトの `web/public/models/kenney-license.txt` | 配布用ライセンス | 対象 |
| プロジェクトの `unity/Assets/KenneyFurniture/*.fbx` | Unityで採用したモデル | 対象外 |
| プロジェクトの `unity/Assets/KenneyFurniture/*.meta` | モデルのGUIDとインポート設定 | 対象 |

`source/` と3DモデルはGitからの取得では復元されません。[モデルを復元する手順](#モデルを復元する手順)で配置します。モデルが無い場合、Webは家具を箱で表示します。配布パッケージのZIPをこのディレクトリに置く場合もGit管理対象外です。

## 家具を追加する手順

1. `source/Side/` または `source/Isometric/` の画像で候補を選びます。
2. 対応する `source/Models/GLTF format/<名前>.glb` を `web/public/models/` にコピーします。配布物は残しておきます。
3. `web/src/furniture_models.js` の `MODEL_REGISTRY` にAPIの `model_id` とURL、必要な向きの補正値を登録します。ブラウザーから `source/` を直接参照しないでください。
4. 寸法、正面、接地、回転、箱表示との一致を確認します。手順の詳細は [Web部屋編集ガイド](../../../docs/web-room-editor.md) を参照してください。
5. 登録変更と必要なドキュメントをGit管理対象にします。GLB本体はコミットされません。`web/public/models/kenney-license.txt` は配布元のライセンスのコピーで、Webビルドにも同梱されます。

採用済み: `bedSingle.glb` → `web/public/models/bed-single.glb`（`model_id: bed`）。枕を評価上の頭側（回転0°で-X）へ揃えるため、Y軸に90°の補正を登録しています。

採用済み: `chair.glb` → `web/public/models/chair.glb`（`model_id: chair`、Y軸180°補正）、`tableCoffeeSquare.glb` → `web/public/models/table-coffee-square.glb`（`model_id: table`）。Unityに追加された椅子とローテーブルに対応します。

採用済み: `televisionModern.glb` → `web/public/models/television-modern.glb`（`model_id: tv_unit`、Y軸180°補正）。Unityの `KenneyTV.prefab` と同じ薄型テレビを、Webの「テレビ台」項目で表示します。

未登録の候補の例: `cabinetTelevision.glb`（収納台）。`table.glb` は別形状で、現在のテーブル表示には使用していません。

本棚の既存変換スクリプトは `unity/Assets/KenneyFurniture/bookcaseOpen.fbx` を参照したままです。UnityのPrefab、モデルの `.meta`、既存のWeb本棚GLBは移動していません。

## モデルを復元する手順

クローン直後はモデル本体がありません。`source/` を配置してから、次の順に復元します。

1. **Unityを開く前に**、`source/Models/FBX format/` の次のFBXを `unity/Assets/KenneyFurniture/` にコピーします: `bedSingle`、`bookcaseOpen`、`chair`、`tableCoffee`、`tableCoffeeSquare`、`televisionAntenna`、`televisionModern`、`televisionVintage`。FBXが無いままUnityを開くと、対応する `.meta` が削除されるためです。削除された場合は `git restore` で戻してからFBXを置きます。
2. `source/Models/GLTF format/` のGLBを、上記「採用済み」の名前で `web/public/models/` にコピーします。
3. `web/` で `npm run models:convert` を実行し、本棚の `bookcase-open.glb` を生成します。

## 配布物を再配置する場合

配布元: Kenney（同梱 `Kenney.url`: https://www.kenney.nl/）。同梱の説明リンクは https://kenney.nl/documentation/model-kits です。

Furniture Kit 2.0を取得・展開し、`Models/`、`Isometric/`、`Side/`、プレビュー画像・ショートカットを `source/` 内に置きます。バージョンが異なる場合は、採用済みモデルを自動で上書きせず、形状とライセンスの変更を確認してください。
