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

1. **審美的主訴の選択（オート判定つき）** — 画像から主訴の候補を信頼度つきで自動提示。手動で確定・追加も可能。
2. **推奨治療の提示** — 確定した主訴に対し、**歯列矯正・補綴治療に限定**して治療選択肢を提示（美容整形・外科的処置は対象外。該当時は専門医相談を注記）。
3. **術前術後シミュレーション動画 + レポート** — モーフィング動画と主訴・推奨治療を 1 つの HTML レポート（＋連携用 JSON）に統合。

> ⚠️ **免責**: 本モードの出力は記録・患者説明・シミュレーションの補助を目的とした参考情報であり、確定診断・治療方針の決定を代替しません。オート判定は画像解析に基づく補助的な候補で、必ず歯科医師の診察・検査による確認が必要です。

## 使い方

```bash
# 主訴コードの一覧（カテゴリ・オート対応・提示治療カテゴリつき）
python dental.py --list-complaints

# 術前/術後画像 → オート判定 + 推奨治療 + シミュレーション動画 + レポート
python dental.py --before pre.jpg --after post.jpg --case-id C001 -o report/

# 術前のみ。オート判定に+手動で主訴を追加
python dental.py --before pre.jpg --complaints crowding,discoloration -o report/

# オート判定を切り、主訴を手動指定
python dental.py --before pre.jpg --no-auto --complaints missing_tooth -o report/
```

出力フォルダには `report.html`（患者説明用・画像埋め込み）、`case.json`（カルテ連携用）、
両画像があれば `simulation.mp4` が生成されます。

### 主なオプション

| オプション | 説明 |
| --- | --- |
| `--before` / `--after` | 術前 / 術後（またはシミュレーション）画像。両方あると動画を生成 |
| `--complaints` | 術者が確定した主訴コード（カンマ区切り） |
| `--auto` / `--no-auto` | オート判定の有効/無効（既定: 有効） |
| `--auto-min-confidence` | 採用する最小信頼度（既定 0.35） |
| `--case-id` / `--patient` | 症例 ID / 患者ラベル（個人情報の取り扱いに注意） |
| `-m` / `--fps` / `--transition` / `--hold` | シミュレーション動画のモーフィング設定 |

### オート判定の仕組み（OpenCV ヒューリスティック）

学習済みモデル不要。顔を検出できれば下顔面中央を口元 ROI、検出できなければ口腔内
接写とみなして画像中央を解析します。ROI 内で歯（高明度・低彩度）と歯肉（赤系）を色で
分離し、次の候補を信頼度つきで算出します。

- 歯の黄色味（LAB の b\*）→ **変色**
- 歯肉と歯の面積比 → **ガミースマイル**
- 歯列内の暗部 → **金属修復物（銀歯）**
- 歯列重心の左右ずれ → **正中の不一致**

照明・ホワイトバランス・顔の向き・トリミングの影響を受けるため、結果はあくまで候補です。

## ライブラリとして使う

```python
from morph_video.dental import run_case

result = run_case(
    before="pre.jpg",
    after="post.jpg",
    complaints=["crowding", "discoloration"],  # 術者が確定した主訴
    auto=True,                                  # 画像からの主訴オート判定
    case_id="C001",
    output_dir="report",
    method="flow",
)
print([f.code for f in result.auto_findings])   # オート候補
print(result.selected_codes)                    # 確定主訴
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
