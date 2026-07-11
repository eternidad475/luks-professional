# CASEFLOW STUDIO™ — Phase 2 Production Audit
2026-07-11 / base: `60b6915`. すべて現行コードの読解・実測に基づく（推測なし）。実測値は headless Chromium 駆動または grep による。

## 1. Architecture Map（現状把握）

| 領域 | 実装 | 所在 |
|---|---|---|
| App shell | 単一HTML 1.72MB・84 script block・段階的バージョンレイヤ（v4.7→v9.6）が `window.go`/`renderResult` 等を28層ラップ | `caseflow_studio_v96.html` |
| Rendering flow | `go(id)` → screen class 切替 → 各 `renderX()`。結果画面は v9.6 が `renderResultImages`+`buildEditGrid` を再実行 | 5176, 20700+ |
| Generation flow (PRIMARY — 変更禁止) | `generateSimulation` → `produceImage`（preflight 700ms cap → AI or ローカル）→ `pushSimResult` → 自動Library保存 → `go('result')` | 20600–20900 |
| Visual Simulation pipeline | `buildClinicalPrompt`（口腔内/標準の2経路）→ `buildSimulationPayload` → val.town proxy（Gemini 2.5 Flash Image）→ `finalizeAIImage`（口唇マスク合成=顔貌保持） | 18977–20250 |
| Secondary refinement | `runSecondaryRefinement`：`_primaryDataUrl` から常に再精密化・ソフトマット合成・アーティファクト自動棄却 | 24900+ |
| Teeth Design (Phase1) | 結果画面の静的ホスト → Glass popup（横カルーセル+黄金比+光学プレビュー）→ 二次精密化へ | cf-p1-* blocks |
| Morphing pipeline | `CaseFlowMorphEngine`＋MediaPipe landmarks、warp/texture handoff、MediaRecorder export 12Mbps | 9000–15000帯 |
| Prompt builder | 単一 `buildClinicalPrompt`＋断片（teeth-type/intent/bracket/KB）。挿入点は各1箇所 | 同上 |
| Library | localStorage `caseflow_project_library_v55`（60回ガード付き quota eviction）＋Supabase `library_items`（48h TTL, `cleanup_expired_library`） | 20400+, 28900+ |
| Photo Manager | `state.photos[]`＋Gallery カード＋`openPhotoManager` モーダル。並べ替え=選択順のみ、D&D無し | 11500+ |
| Auth | Supabase auth（メール+電話）。`cfGateV2` ログインウォール、consent gate | 21400+, 26400+ |
| Billing | Stripe Checkout/Portal/Webhook（`api/stripe/*`）＋`cfConsumeToken`/`cfRefundGeneration`（migration 06） | api/, 20150 |
| Supabase | migrations 01–18＋7日招待期限（`20260717000019`、**DB未適用**） | supabase/ |
| Vercel Functions | `api/stripe/*`, `api/dental_outline`, `api/dental_event_plan`。rewrites+headers は `vercel.json` | api/ |
| PWA / SW | shell-only precache（患者画像は非キャッシュ）。`cfsw-v5-rollback-0711`。iOS 追加導線あり | sw.js |
| State | `window.state` 単一オブジェクト＋`cfPersist`（sessionStorage meta 4h + IndexedDB 画像） | 22400+ |
| Animation | CSS keyframes（cfBgEdge/cfBgFloat/cfBgShift）＋film grain＋palette JS（--c1/--c2, color-mix） | 23–120, 5700+ |

## 2. 実測メトリクス

- HTML: **1,721,526 B**（gzip後 ~380KB 推定）。landing 390KB / admin 55KB
- `addEventListener` **356**（大半は初期化時1回。動的再バインドは Gallery/Library 再レンダリング系）
- 無条件 `setInterval` **12**（cfPersist 4s 変化検知＋30s フル保存、トークンバッジ 60s、ほか帯: 27181/28620/28661/28795 は要精査）
- `MutationObserver` **6**（13969 / 16758 / 21409 / 21559(attr限定・安全) / **28085: nav を childList+subtree 監視しつつ callback が applyNav で nav を書換え得る=凍結パターン類似・要リファクタ** / 29151）
- `backdrop-filter` **63**箇所（iOS 合成コスト。重なりは最大2層で許容内だが Library グリッドで多数同時表示）
- `window.go` ラッパ **28層**（機能は正常。保守性リスクとして§6）

## 3. UX Audit（画面別・説明不要UIまでの距離）

| 画面 | 主な摩擦 | 提案(PR候補) |
|---|---|---|
| Home | 良好。CTA明確 | – |
| Start | 3カード構成明快 | – |
| Simulator | ①アップロード2枠と Cases の関係が初見で不明 ②主訴カード未選択エラーが生成押下後に判明 | 未選択時は生成ボタンを disabled+理由表示（PR-UX1） |
| Result | ①5軸スライダーと Teeth Design と Refine の役割分担が説明依存 ②サムネ長押し選択が発見不能 | セクション見出し+一行ガイド、長押しヒントの初回コーチマーク（PR-UX2） |
| Library | 検索/フィルタ/一括操作なし（§9） | PR-LIB1 |
| Morphing | ランドマーク編集UIの学習コスト大 | ガイドオーバレイ（PR-M2） |
| 招待/Account | 良好 | – |
| エラー系 | AI失敗が toast のみで復旧導線なし | §11 エラーパネル（PR-ERR1） |

## 4. Mobile (iPhone PWA)

- ✅ safe-area: 37箇所で env() 使用、100dvh 13箇所、`--real-vh` フォールバックあり
- ✅ overscroll: body固定+画面内スクロール。SW shell-only
- ⚠️ Dynamic Island: 固定トークンバッジ(z=2147483000)が landscape で島と重なる端末あり → `env(safe-area-inset-top)` は使用済みだが landscape 時の inset-left 未考慮（PR-MOB1）
- ⚠️ キーボード: simCustomPrompt 入力時に生成ボタンが隠れる（visualViewport 未使用）→ PR-MOB1
- ⚠️ Pull-to-Refresh: standalone では抑止済み、Safariタブでは既定動作（許容）

## 5. Desktop

- `.app` が 480px 固定列。広幅は余白のみ → 情報設計改善余地大：Result で Before/After と編集軸の2カラム化、Library グリッド列可変（PR-DT1、CSS only で実現可）

## 6. Code Quality / 保守性

- 単一ファイル・多層ラッパは「動く歴史」だが変更コスト高。**動作不変のモジュール化**は §PR-CQ1: 主要ブロックを `<script src>` 分割（SW precache 更新込み）から着手し、`window.go` ラッパ 28層は「合成1関数+フック配列」へ段階統合（挙動同一のリグレッションテスト必須）
- 重複ユーティリティ: `esc()` 5実装 / `loadImage` 4実装 / sleep 3実装 → 共通化候補（挙動同一）

## 7. Performance findings（Primary Routing 以外）

| 種別 | 発見 | 対処 |
|---|---|---|
| Duplicate fetch | 生成1回あたり `/simulate` へ **2リクエスト**（本生成＋problemList スクリーニング。src毎キャッシュ有→初回のみ） | 仕様として文書化。バックエンド負荷が問題なら screening を軽量エンドポイントへ（PR-PF2） |
| Interval leak候補 | 27181 の `_iv`（招待コード表示）と 28620/28661/28795 帯は画面離脱後も稼働の可能性 | 精査+画面非活性時 pause（PR-PF1） |
| MutationObserver 28085 | nav 書換ループの潜在リスク（凍結事故と同型） | attr限定 or フック化（PR-PF1・優先） |
| Heavy DOM query | `renderSimGallery` が結果毎に全再構築＋長押しタイマ再付与 | 差分更新は挙動リスクあり→現状維持、計測のみ |
| Image cache | サムネは downscale 済（600/384px）。`galleryThumb` の原寸 dataURL 直挿しが photos 多数で重い | PR-PF3: gallery 表示用 384px サムネ生成 |
| Layout shift | 結果画像 onload 時の高さ変動 | aspect-ratio 予約（PR-UX2 に同梱） |
| Unused assets | `icons/icon-*.png(v1)` は旧HTML参照用に温存が正当。`caseflow_palette_shell.html` 参照なし → 削除候補（要確認） |
| Bundle | 1.72MB HTML。§6 分割で初回パース改善（SW 更新と同時に） |

## 8. Glass UI / Gallé / OPN-A24（デザイン方針監査）

- 現状: 白ガラス+2色radial+粒状+halation。カード間の質感差（result系は濃く、library系は薄い）
- 改善方向（PR-GL1, CSSのみ）: ①`--glass-*` トークン化（blur/border/shadow/depth 4段）②内側1px light-rim+外側多層影の統一 ③hover/touch: transform+光沢スイープ（reduced-motion で無効）④背景ゆらぎ: 既存 cfBgFloat の振幅を scroll 連動係数で微変調（rAF 1本・visibility gate 付き）⑤パレット変更補間: `--c1/--c2` を transition 可能な `@property` 登録（Safari fallback: JS lerp）
- 「背景が認知されない」対策: パレットボタンへ現在2色のライブスウォッチ表示＋初回のみ 600ms の静かな波紋

## 9. Library / Photo Manager（機能ギャップ）

- Library: 検索・種別/日付フィルタ・並び替え・複数選択→一括DL/削除・サムネ画質(600→768) → PR-LIB1（localStorage スキーマ不変・表示層のみ）
- Photo Manager: D&D並べ替え（touch対応）・リネーム・一括削除/カテゴリ変更 → PR-PM1（`state.photos` 順序はモーフ入力順に影響するため、モーフ側は明示選択を維持＝影響なしを確認済み）

## 10. Accessibility

- ✅ ダイアログ系: role/aria-modal/focus-trap/Escape（Phase1系は完備）。旧モーダル（cropModal/photoManager）はトラップ無し → PR-A11Y1
- ⚠️ コントラスト: `--muted` 58% は 4.5:1 未満の背景組合せあり → トークン再調整
- ⚠️ `simConceptCard` 選択状態が色のみ → チェックマーク付与
- reduced-motion: 13箇所対応済み、背景アニメも停止 ✅

## 11. Error Handling

- 現状: AI失敗は toast+console。復旧導線なし
- PR-ERR1: 生成失敗時に result 画面へ「原因（通信/混雑/トークン）＋再試行ボタン＋ローカル生成へ切替」を出すインラインパネル（既存 toastFn は維持、console.error は残すが UI 併設で「console だけ」を解消）

## 12. Production Test 計画（各PR共通ゲート）

Build=inline-script parse (`node --check` 84 blocks) / PWA=SW precache 整合 / Responsive=390/844/1024 スクショ / Lighthouse=CI外で手動（headless計測はモバイル実機と乖離するため参考値扱い） / Memory=12回開閉 DOM 増加0 / Console=pageerror 0 / Offline=shell 起動 / Safari・実機=レビュー時にオーナー確認依頼

## 13. Roadmap（小PR分割）

1. **PR#1（本書）** 監査+計画
2. **PR#2 Teeth Design v2**（本Phase最詳細指定・下記別紙）
3. PR-GL1 Glassトークン+背景認知
4. PR-ERR1 エラーパネル
5. PR-LIB1 Library 検索/選択/一括
6. PR-PM1 Photo Manager D&D
7. PR-MOB1 キーボード/landscape 微修正
8. PR-A11Y1 旧モーダルの trap/contrast
9. PR-PF1 interval/observer 衛生
10. PR-M2 Morphing 品質（warp/ghost/flicker/export は計測ハーネス先行）
11. PR-CQ1 モジュール分割（最後・挙動同一検証つき）

## Remaining / Minor / Debt / Future（要約）

- **Remaining**: 招待7日 migration が DB 未適用。iOS 実機での Teeth Design 動作確認
- **Minor**: nav MutationObserver(28085)、interval 4本の精査、`caseflow_palette_shell.html` 整理
- **Technical Debt**: go() 28層 / esc×5 / 単一1.7MB HTML / v8.1系デッドコード（simV81 UI は不使用画面）
- **Future**: screening 専用軽量エンドポイント、Library の Supabase 全文検索、morph の WebCodecs export
