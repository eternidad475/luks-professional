# morph-video

複数の画像をモーフィングでつないで 1 本の動画にする CLI / Python ライブラリです。

モーフィング方式を **3 つ**から選べます。

| 方式 | `--method` | 特徴 |
| --- | --- | --- |
| オプティカルフロー | `flow` (既定) | Farneback フローで画素の動きを推定し、変形しながら合成。手作業の対応点指定なしで自然な変形。人物・風景など一般写真向け。 |
| 特徴点ベース | `feature` | ORB 特徴点の対応 + Delaunay 三角形分割によるワープ。はっきりした構造のある画像で正確な「変形」。対応点不足時は自動でクロスフェードに退避。 |
| クロスフェード | `crossfade` | 単純なアルファブレンド。最速。変形はせず重ねて溶けるだけ。 |

## セットアップ

```bash
pip install -r requirements.txt
```

> `opencv-python` の代わりに、GUI 不要の環境では `opencv-python-headless` でも動作します。

## 使い方

```bash
# オプティカルフロー方式 (既定)。引数の順番がそのまま遷移順になる
python morph.py a.jpg b.jpg c.jpg -o out.mp4

# ディレクトリ内の画像を名前順にすべて使用 + 特徴点方式 + ループ
python morph.py images/ -m feature --loop -o out.mp4

# クロスフェードで素早く確認 (24fps)
python morph.py "shots/*.png" -m crossfade --fps 24 -o out.mp4
```

### 主なオプション

| オプション | 既定 | 説明 |
| --- | --- | --- |
| `-o, --output` | `morph.mp4` | 出力動画ファイル |
| `-m, --method` | `flow` | `flow` / `feature` / `crossfade` |
| `--fps` | `30` | 出力フレームレート |
| `--transition` | `1.0` | 1 遷移にかける秒数 |
| `--hold` | `0.5` | 各画像を静止表示する秒数 |
| `--size` | 先頭画像 | 出力解像度 (`1280x720` の形式) |
| `--easing` | `ease_in_out` | 遷移カーブ (`linear` / `ease_in` / `ease_out` / `ease_in_out` / `ease_in_out_sine`) |
| `--loop` | off | 末尾から先頭へ戻る遷移を追加（ループ再生向け） |

特徴点方式の調整: `--max-features` / `--ratio` / `--min-matches`
フロー方式の調整: `--flow-winsize` / `--flow-levels`

入力画像はサイズが違っても自動で先頭画像（または `--size`）の解像度に揃えられます。

## ライブラリとして使う

```python
from morph_video import build_video

build_video(
    inputs=["a.jpg", "b.jpg", "c.jpg"],
    output="out.mp4",
    method="feature",     # "flow" / "feature" / "crossfade"
    fps=30,
    transition_seconds=1.2,
    hold_seconds=0.4,
    loop=True,
)
```

個別の方式を直接使うこともできます。

```python
from morph_video import get_morpher

m = get_morpher("flow")
m.prepare(img1, img2)        # ペアごとの前計算
frame = m.frame(img1, img2, t=0.5)   # 中間フレーム (t は 0..1)
```

## 仕組み

- **flow**: img1→img2 と img2→img1 の双方向オプティカルフローを求め、中間時刻 `t` で両画像を変形させてからクロスディゾルブします。
- **feature**: 両画像から ORB 特徴点を検出・マッチングし、RANSAC で外れ値を除去。四隅・辺の中点を加えて画像全体を覆い、Delaunay 三角形ごとにアフィン変換でワープして合成します。
- **crossfade**: 重み付き平均 `(1-t)·img1 + t·img2`。

## 補足

- 出力コーデックは `mp4v`（`.mp4`）です。
- きれいなモーフィングのコツ: 構図・被写体の位置・明るさが近い画像同士を並べると、特に `flow` / `feature` で破綻が少なくなります。

---

# 歯科臨床モード（記録・シミュレーション）

術前術後の記録撮影・患者説明用に、上記のモーフィング（術前→術後の変化可視化）へ
次の機能を追加した CLI `dental.py` / モジュール `morph_video.dental` を同梱しています。

1. **マクロ／ミクロの 2 バージョン評価** — 画像を「マクロ（顔貌とスマイル）」「ミクロ（歯と歯肉）」の 2 種類で扱い、それぞれ専用の審美評価項目を算出。
2. **撮影・アップロードの両対応（Web UI）** — スマホ（iPhone 等）のカメラで直接撮影する方法と、一眼レフ等で撮影した画像をアップロードする方法の両方に対応。
3. **審美的主訴の選択（自動評価から導出）** — 評価結果から主訴の候補を自動抽出。手動で確定・追加も可能。
4. **推奨治療の提示** — 確定した主訴に対し、**歯列矯正・補綴治療に限定**して治療選択肢を提示（美容整形・外科的処置は対象外。該当時は専門医相談を注記）。
5. **術前術後シミュレーション動画 + レポート** — マクロ/ミクロ各々のモーフィング動画と評価・主訴・推奨治療を 1 つの HTML レポート（＋連携用 JSON）に統合。

### マクロ評価（顔貌とスマイル）

| 項目 | 内容 |
| --- | --- |
| 正中線の一致 | 顔の中心線（両目から推定）と前歯正中のラインのずれ |
| スマイルライン | 上顎切縁を結ぶラインの湾曲方向（下唇カーブとの調和）と左右対称性 |
| スマイル幅 / バッカルコリドー | 口角間に対する歯列の見える幅のバランス |
| 歯の露出量 | 上顎前歯の見える量・歯肉露出（ガミー傾向） |

### ミクロ評価（歯と歯肉）

| 項目 | 内容 |
| --- | --- |
| 歯のバランス（黄金比） | 前歯から遠心への見かけ幅の逓減比（理想 ≈0.618） |
| 歯の色と透明感 | 明度 L\*・彩度・色相と、切縁の明度ばらつき（透明感の代理指標） |
| 歯の形態と質感 | 中切歯の縦横比（丸み/角張り）と表面テクスチャ指標 |
| 歯肉のラインと見え方 | 歯肉ラインの左右対称性・色調・露出量（ガミー/色素沈着） |

各項目は `良好 / 要確認 / 参考 / 判定不可` の判定とスコアつきで表示します（いずれも参考値）。

> ⚠️ **免責**: 本モードの出力は記録・患者説明・シミュレーションの補助を目的とした参考情報であり、確定診断・治療方針の決定を代替しません。オート判定は画像解析に基づく補助的な候補で、必ず歯科医師の診察・検査による確認が必要です。

## 使い方（Web UI：撮影 / アップロード）

スマホで直接撮影、または一眼レフ画像のアップロードはブラウザ UI が便利です。

```bash
python webapp.py            # → http://localhost:8000
python webapp.py --host 0.0.0.0 --port 9000
```

- マクロ術前/術後・ミクロ術前/術後の各スロットで「📷 撮影」（端末カメラ）／「⬆ アップロード」（一眼レフ等の画像）を選択
- 「📷 撮影」はブラウザの `getUserMedia` でその場のライブ撮影、「⬆ アップロード」は端末のファイル/写真ライブラリ（一眼レフから取り込んだ画像など）を選択
- 「解析してレポート生成」で評価・推奨治療・シミュレーション動画を生成し、結果ページへ遷移

> スマホのカメラ利用には `localhost` か HTTPS が必要な場合があります（ブラウザのセキュリティ仕様）。LAN 内のスマホから使う場合はリバースプロキシ等で HTTPS 終端してください。

## 使い方（CLI）

```bash
# 主訴コードの一覧（カテゴリ・提示治療カテゴリつき）
python dental.py --list-complaints

# マクロ(顔貌・スマイル)とミクロ(歯・歯肉)の術前/術後からレポート一式
python dental.py \
  --macro-before face_pre.jpg --macro-after face_post.jpg \
  --micro-before teeth_pre.jpg --micro-after teeth_post.jpg \
  --case-id C001 -o report/

# マクロ術前のみ + 手動主訴を追加
python dental.py --macro-before face_pre.jpg --complaints crowding,discoloration -o report/
```

出力フォルダには `report.html`（患者説明用・画像埋め込み）、`case.json`（カルテ連携用）、
各バージョンで術前術後が揃えば `simulation_macro.mp4` / `simulation_micro.mp4` が生成されます。

### 主なオプション

| オプション | 説明 |
| --- | --- |
| `--macro-before` / `--macro-after` | マクロ（顔貌・スマイル）術前 / 術後画像 |
| `--micro-before` / `--micro-after` | ミクロ（歯・歯肉接写）術前 / 術後画像 |
| `--before` / `--after` | `--macro-*` のエイリアス（後方互換） |
| `--complaints` | 術者が確定した主訴コード（カンマ区切り） |
| `--auto` / `--no-auto` | 自動評価の有効/無効（既定: 有効） |
| `--case-id` / `--patient` | 症例 ID / 患者ラベル（個人情報の取り扱いに注意） |
| `-m` / `--fps` / `--transition` / `--hold` | シミュレーション動画のモーフィング設定 |

### 評価の仕組み（OpenCV ヒューリスティック）

学習済みモデル不要。顔を検出できれば両目から顔正中・下顔面中央を口元 ROI とし、検出
できなければ口腔内接写とみなして画像中央を解析します。ROI 内で歯（高明度・低彩度）と
歯肉（赤系）を色で分離し、上記マクロ／ミクロ各項目を算出します。

照明・ホワイトバランス・顔の向き・トリミングの影響を受けるため、結果はあくまで参考値です。

## ライブラリとして使う

```python
from morph_video.dental import run_case

result = run_case(
    macro_before="face_pre.jpg",   # マクロ（顔貌・スマイル）
    macro_after="face_post.jpg",
    micro_before="teeth_pre.jpg",  # ミクロ（歯・歯肉）
    micro_after="teeth_post.jpg",
    complaints=["crowding"],       # 術者が確定した主訴（任意）
    auto=True,                     # マクロ/ミクロの自動評価
    case_id="C001",
    output_dir="report",
    method="flow",
)
for v in result.versions:          # マクロ/ミクロ各バージョン
    print(v.title, [(m.label, m.status) for m in v.evaluation.metrics])
print(result.selected_codes)       # 確定主訴（手動 + 評価由来）

# 評価だけを単体で使う
from morph_video.dental import evaluate_macro, evaluate_micro
import cv2
ev = evaluate_macro(cv2.imread("face_pre.jpg"))
print([(m.label, m.value, m.status) for m in ev.metrics])
```

主訴カタログ・推奨治療ナレッジベースは個別にも参照できます。

```python
from morph_video.dental import list_complaints, recommend

for c in list_complaints():
    print(c.code, c.label, c.category)

rec = recommend("missing_tooth")
for opt in rec.options:   # すべて「歯列矯正」か「補綴治療」
    print(opt.category, opt.name)
```
