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
