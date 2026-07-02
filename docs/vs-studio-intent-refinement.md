# Visual Simulation Studio — Intent-first 精度改善（v9.7）

> 方針: 生成ロジックの全面刷新ではなく、「無駄な補正を減らし、ユーザー意図と臨床所見を正確に反映する調整」。
> 既存のスライダー・コンセプト・所見表示・合成パイプラインはすべて維持。

## 1. 改修方針

- 優先順位を全生成プロンプトに明文化: ①ユーザー明示指示 → ②視認できる所見 → ③顔貌/口唇/歯列/歯肉の調和 → ④自然な審美 → ⑤理想比率は参考値（黄金比は soft reference）
- 矯正的問題（クロスバイト/overjet/叢生/空隙/捻転/歯軸/正中/arch asymmetry）は「位置・歯軸・アーチ関係の補正」として表現し、補綴的ごまかしを禁止
- 補綴的問題（欠損/矮小歯/サイズ不調和/変色/破折/摩耗/旧修復物）は「形態・サイズ・色調・修復の補正」として表現し、歯列移動だけのごまかしを禁止
- 低視認性領域（口唇で隠れた部位・低解像度）は uncertain として保守的に扱う
- Before の顔貌・口唇・肌・表情・照明は原則保持（既存 FACE IDENTITY LOCK を継続）

## 2. 実装対象（すべて caseflow_studio_v96.html 内・同一IIFE）

| 箇所 | 変更 |
|---|---|
| `buildClinicalScreeningPrompt()` | STEP 5 を追加: 4レイヤー構造化出力＋分類ルール＋dual output（`findings[]` + `structured{}`）。既存の叢生/すきっ歯誤認防止ルール（STEP 2）は完全維持 |
| `buildProblemList()` | `/screen` レスポンスの `structured` を non-enumerable プロパティとして保持（旧バックエンドは配列のみ返す → 完全後方互換） |
| `ensureProblemList()` | `src.structuredFindings` に構造化所見を格納 |
| 新規 `cfComposeIntentBlock()` | intent/所見分類/画像ロール重み/ガードレール文を合成（下記 §4） |
| `buildClinicalPrompt()` | intraoral・facial 両パスの clinician note 直後に intent block を注入 |
| `buildSimulationPayload()` | `intent_mode` / `minimal_change` / `correction_scope` / `image_role` / `structured_findings` をペイロード追加。Minimal ON かつ非抜歯・非ブラケット時は denoising ≤0.60、negative prompt に over-whitening/veneer 系を追加 |
| `buildEditGrid()` | UI 追加（§5） |

## 3. 所見 JSON スキーマ

`/screen` は `{"findings":[{en,ja}], "structured":{...}}` を返す。`structured` は依頼書 §3 のスキーマに準拠:
`facialBalance` / `dentolabialBalance` / `orthodonticFindings` / `restorativeFindings` / `gingivalFindings`（各 confidence 付き）、`priorityClassification`（orthodontic/restorative/gingival/lipFacial/uncertainVisibility）、`additionalImageRecommendations`（needsProfileImage 等4種）、`simulationGuidance`（preserve/modify/avoid）、`summary`、`confidence`。

バックエンド（Modal `/screen`）が旧形式（配列のみ）でも全機能が劣化なしで動作し、`structured` 未提供時はレガシー所見のキーワード分類（`CF_ORTHO_KEYS` / `CF_RESTOR_KEYS`）にフォールバックする。

## 4. 生成プロンプト組み立てロジック（cfComposeIntentBlock）

出力順:
1. PRIORITY ORDER 宣言（黄金比= soft reference 明記）
2. IMAGE ROLE 重みづけ — frontal_smile → 顔貌調和/リップライン/スマイルアーク/切縁/口角/歯肉露出、intraoral_retracted_frontal → 叢生/空隙/捻転/歯軸/正中/overjet/欠損/歯肉ライン、contrastor_anterior_closeup → 切縁ライン/切縁長/透明感/形態/左右差/摩耗/チッピング/サイズ感（高優先精密審美）
3. ORTHODONTIC-PRIORITY 所見 → 位置/歯軸補正として表現、補綴的偽装禁止
4. RESTORATIVE-PRIORITY 所見 → 形態/サイズ/色調補正として表現、移動偽装禁止
5. uncertainVisibility → 保守戦略（未検出でも汎用の hidden-area caution を常時挿入）
6. confidence < 0.55 → 断定回避・ユーザー指示優先
7. structured の preserve/avoid guidance をパススルー
8. モード文（Auto / Balanced / User-first — User-first は「指定外の補正を追加しない・残すと指定されたもの（矮小歯等）は必ず残す」）
9. Minimal-Change 文（不要ホワイトニング/理想化/均一化/唇美化/大規模変更の明示禁止）
10. Correction Scope 文（alignment/shape/shade/gingiva/combined/preserve）
11. ALWAYS AVOID 定型ガードレール（veneer-perfect 回避・identity 保持・biologically plausible）

## 5. 追加した UI（編集パネル・スライダー直下）

- **意図の反映 / User Intent**: Auto（AI所見を優先）/ Balanced（両立・推奨・既定）/ User-first（指示を最優先）
- **最小変更モード** チェックボックス（指定外の補正を強く抑制＋denoising 上限＋negative prompt 強化）
- **補正範囲** セレクト: 総合（既定）/ 歯列位置のみ / 歯冠形態のみ / 色調のみ / 歯肉のみ / 現在の個性を保持
- 追加指示欄の placeholder を意図指定の例に変更（「正中離開だけ閉じたい。矮小歯は残す。…」）
- いずれも既存スライダーと同じく「再生成」ボタンで反映（自動再生成なし）

## 6. 側貌・追加画像について（現状の扱い）

現行の写真カテゴリは facial / focus（＋intraoral / intraoralDark フラグ）で、side profile 専用カテゴリは未実装。スキーマ・プロンプトは profile / frontal_rest / intraoral_occlusal を予約済みで、`additionalImageRecommendations.needsProfileImage` が返れば UI 提示（Phase 次段）に接続できる。側貌の画像ロール追加は Photo Manager のカテゴリ拡張とセットで次フェーズ推奨。

## 7. 後方互換・安全性

- `/screen` 旧レスポンス・所見ゼロ・endpoint 未設定（pixel fallback）のすべてで従来どおり動作
- intent block は try/catch 内で合成し、失敗時は空文字（生成は継続）
- 抜歯矯正モード・ブラケット除去は Minimal-Change の denoising 上限の対象外（必要変化量が大きいため。プロンプト側ガードのみ適用）
