# Phase 2.1 設計書 — Personal / Clinic・患者/Library 紐付け・退会導線

> ステータス: **レビュー承認済み（2026-07-02）→ 2.1a migration 7 適用済み（2026-07-02）**
> （`supabase/migrations/20260705000007_workspaces_foundation.sql` — 本番DB適用完了・バックフィル検証OK）
>
> **レビュー確定事項:**
> 1. 財布移行 = コピー＋旧RPC委譲。**残高コピーは 2.1b の RPC 切替と同一Txで実施**（2.1a〜2.1b 間のドリフト・二重消費を防止。それまで profiles が正）
> 2. **Library は 48時間一時保存で固定**。長期クラウド保存・保存期間延長プランは将来も作らない（プロダクト思想）。48h後は実ファイル削除・metadata/ledger/audit は保持・UI は「ファイル削除済み」表示
> 3. 既存 Stripe 契約は personal workspace 帰属。Clinic への自動移管は非対応（必要時は admin 手動）
> 4. 複数Clinic所属は表示のみ。ただし **active_workspace_id の概念は 2.1 から導入**（保存・生成・Library閲覧はこれを使用）
> 5. 退出/削除された member の作成データは Clinic に残る（規約明記）。表示は「削除済みメンバー」等
> 6. `/api/account/deactivate` serverless 新設（service_role 処理はサーバー側）
> 7. 患者画像はクラウド長期保存しない前提で規約整備。「患者同意を得た画像のみ使用」確認導線を将来追加
> 8. SMS認証は完全撤去（実施済み・`CF_SMS_AUTH_ENABLED=false` でコード温存）
> 9. DB整合性14項目 → migration 7 に複合FK/トリガー/CHECKで実装（下記追記）
>
> **migration 7 での設計変更:** `workspaces` に stripe_customer_id / stripe_subscription_id を**持たせない**ことに変更。Stripe参照は `billing_customers` / `billing_subscriptions` に `workspace_id` を追加して管理する — member への支払い情報露出が RLS 設定ミスでも起こり得ない構造にするため。
> 対象: workspaces / メンバー管理 / patients / cases / library_items / トークン財布の workspace 化 / 退会・退出・削除・解約

---

## 1. 推奨DB設計

中核原則: **すべての臨床データとトークンは user ではなく workspace にぶら下げる**。Personal は「メンバー1人の workspace」であり、Clinic と同じ構造で扱う（分岐は type と role だけ）。

```
auth.users ─ profiles（個人プロフィール・roleは既存のまま）
     │
workspace_members（user⇄workspace, role: owner/admin/member, status）
     │
workspaces（type: personal/clinic, tokens_remaining=財布, plan, stripe参照）
     ├─ patients（workspace_id, patient_code, display_label…）
     │     └─ cases（workspace_id, patient_id, case_title…）
     │            └─ library_items（workspace_id, patient_id?, case_id?, item_type, storage_path…）
     ├─ token_ledger（既存＋workspace_id/patient_id 追加）
     └─ billing_customers / billing_subscriptions（workspace_id 列を追加）
```

依頼書 §3 の構造をそのまま採用し、以下だけ調整を推奨します:

| 調整 | 理由 |
|---|---|
| `workspaces.tokens_remaining` を財布の正とし、`profiles.tokens_remaining` は**移行期間中のみ併存**（§11 移行方針） | Clinic 共有トークンの前提。既存RPC/Webhookの段階的移行のため |
| `patients` に **`patient_code` の workspace 内 unique 制約** | 医院内での患者取り違え防止。識別情報（本名・生年月日・カルテ番号）は引き続き**保存しない**（display_label は匿名ラベル） |
| `library_items.storage_path` は Supabase Storage の **private bucket**（`case-generated-images` / `case-morph-videos`）パス | 現行の localStorage/IndexedDB は端末ローカルで共有・永続不可のため（§10 影響範囲参照） |
| `workspace_invites` テーブルを追加（既存 `invite_codes` はベータ入場用として温存） | 「アプリに入る招待」と「Clinicに入る招待」は寿命も権限も別物 |

## 2. Migration 案（migration 7 — レビュー後に適用）

```sql
-- ============ 20260705000007_workspaces.sql（案）============
create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('personal','clinic')),
  name text not null,
  owner_user_id uuid not null references auth.users(id),
  plan text,
  tokens_remaining integer not null default 0,
  clinic_phone text,             -- 医院代表電話（SMS認証とは無関係）
  clinic_address text,
  stripe_customer_id text,
  stripe_subscription_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz         -- soft delete（閉鎖）
);

create table public.workspace_members (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member' check (role in ('owner','admin','member')),
  status text not null default 'active' check (status in ('active','invited','removed','left')),
  invited_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  removed_at timestamptz,
  removed_by uuid,
  unique (workspace_id, user_id)
);

create table public.patients (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  patient_code text not null,        -- 匿名ID（例: P-0001）。本名・カルテ番号は入れない運用
  display_label text,                -- 匿名ラベル（例: 「30代女性 上顎前歯」）
  sex text, age integer, memo text,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  unique (workspace_id, patient_code)
);

create table public.cases (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  patient_id uuid not null references public.patients(id) on delete cascade,
  case_title text not null,
  treatment_type text,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table public.library_items (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  patient_id uuid references public.patients(id) on delete set null,   -- null = 未整理
  case_id uuid references public.cases(id) on delete set null,
  created_by uuid not null references auth.users(id),
  item_type text not null check (item_type in
    ('visual_simulation','morphing_video','uploaded_image','project','other')),
  title text,
  storage_path text,        -- private bucket 内パス
  thumbnail_path text,
  metadata jsonb,           -- before/after参照・生成パラメータ・ledger_id等
  expires_at timestamptz,   -- 48h一時保存の互換
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);
create index on public.library_items (workspace_id, created_at desc);
create index on public.library_items (workspace_id, patient_id, created_at desc);

create table public.workspace_invites (   -- Clinicメンバー招待（ベータ入場のinvite_codesとは別）
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  code text not null unique,
  invited_email text,
  role text not null default 'member' check (role in ('admin','member')),
  invited_by uuid not null references auth.users(id),
  max_uses integer not null default 1,
  used_count integer not null default 0,
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

-- token_ledger 拡張（workspace_id/case_id は migration 1 で追加済み。patient_id のみ追加）
alter table public.token_ledger add column if not exists patient_id uuid;

-- billing の workspace 対応（additive）
alter table public.billing_customers    add column if not exists workspace_id uuid;
alter table public.billing_subscriptions add column if not exists workspace_id uuid;

-- ---- ヘルパー（RLSから使用。SECURITY DEFINER・(select auth.uid())）----
create function public.ws_role(p_ws uuid) returns text ... ;
  -- workspace_members から自分の active な role を返す（なければ null）
create function public.is_ws_member(p_ws uuid) returns boolean ... ;   -- role问わず active
create function public.is_ws_admin(p_ws uuid)  returns boolean ... ;   -- owner/admin
create function public.is_ws_owner(p_ws uuid)  returns boolean ... ;

-- ---- 自動 personal workspace ----
-- handle_new_user() 拡張: profiles 作成後に
--   workspaces(type=personal, name=display_name||email, owner=new.id, tokens=0) を作成し
--   workspace_members(owner, active) を挿入
-- 既存ユーザーのバックフィル: 全 profiles に personal workspace を作成し
--   profiles.tokens_remaining の残高を workspaces.tokens_remaining へコピー（ledgerに 'wallet_migration' 記録）

-- ---- RPC（すべて SECURITY DEFINER + 権限チェック + audit）----
create function public.create_clinic_workspace(p_name text, p_phone text, p_address text) returns jsonb;
create function public.consume_workspace_tokens(p_ws uuid, p_amount int, p_reason text,
  p_patient uuid default null, p_case uuid default null) returns jsonb;   -- consume_tokens v2
create function public.refund_workspace_tokens(p_ledger_id bigint) returns jsonb;
create function public.create_ws_invite(p_ws uuid, p_role text, p_email text) returns jsonb;      -- owner/admin
create function public.accept_ws_invite(p_code text) returns jsonb;                               -- member参加
create function public.remove_ws_member(p_ws uuid, p_user uuid) returns jsonb;  -- owner（removed記録）
create function public.leave_workspace(p_ws uuid) returns jsonb;                -- 本人（left記録）
create function public.deactivate_account() returns jsonb;                      -- Personal退会（soft）
create function public.close_clinic_workspace(p_ws uuid) returns jsonb;         -- owner（soft delete）
```

## 3. RLS設計（フロント表示制御に依存しない）

| テーブル | select | insert | update | delete |
|---|---|---|---|---|
| workspaces | `is_ws_member(id)`。**ただし member には stripe_* を見せない** → 直接selectは `is_ws_admin`、member 向けは `ws_public_view`（name/type/plan/tokens/clinic_phone のみの view か、列を返さない RPC） | RPCのみ | `is_ws_owner`（clinic情報編集）| なし（soft delete via RPC） |
| workspace_members | `is_ws_member(workspace_id)`（＝メンバー一覧は互いに見える。表示は display_name/role のみ） | RPCのみ | RPCのみ | なし |
| patients / cases | `is_ws_member(workspace_id) and deleted_at is null` | `is_ws_member` + `created_by=(select auth.uid())` | `is_ws_member`（削除=deleted_at更新は `is_ws_admin` or created_by） | なし |
| library_items | 同上 | 同上 | 同上 | なし |
| workspace_invites | `is_ws_admin(workspace_id)` | RPCのみ | RPCのみ | なし |
| token_ledger | 既存own-row＋admin。**Clinic owner/admin には `is_ws_admin(workspace_id)` の select を追加**（誰が消費したかを確認可能。患者画像そのものは ledger に無いので詳細は露出しない） | service_role/RPC | なし | なし |
| Storage buckets | private。`storage.objects` ポリシーで path の先頭 `workspace_id/` を `is_ws_member` で判定 | 同左 | 同左 | `is_ws_admin` |

**代表者個人情報の保護（§6）**: member が到達できるのは `workspaces` の公開view（clinic_name / clinic_phone / plan / tokens）と `workspace_members` の (display_name, role) のみ。owner の email・個人プロフィール・stripe_customer_id・支払い情報は RLS レベルで不可視（profiles は own-row select のままなので他人の profiles はそもそも読めない。billing_* の select は `is_ws_owner` に限定変更）。

## 4. 登録フロー

**Personal（デフォルト）**: 現行サインアップ（email+pass+職種+同意）→ 招待コード → `handle_new_user` が personal workspace を自動作成 → そのまま利用開始。追加画面なし。Personal plan 購読時は checkout metadata に workspace_id を載せる。

**Clinic**: ①代表者が通常サインアップ（Personalとして入場）→ ② Account Sheet「Clinicを作成」→ clinic_name（必須）/ clinic_phone（必須・医院代表番号）/ 住所（任意）→ `create_clinic_workspace` → ③ Clinic plan checkout（workspace_id を metadata に）→ ④ メンバー招待リンク発行。**アクティブ workspace の切替**は Account Sheet 上部のセレクタ（Personal ⇄ 所属Clinic）。`state.activeWorkspaceId` を localStorage に保持。

## 5. Account Sheet 画面分岐（§10 準拠）

- 共通ヘッダに **workspace 切替**（所属が2つ以上のとき表示）
- **Personal**: 現在のプラン / トークン / プラン変更 / 追加購入 / 支払い管理 / プロフィール編集 / 患者管理・Library / **アカウント退会**（danger・最下部）
- **Clinic Owner**: Clinic名 / 共有トークン / **メンバー管理** / 招待 / 支払い管理 / Clinic情報編集 / 個人プロフィール編集 / Clinic解約 / **Clinic閉鎖**（danger）
- **Clinic Member**: 所属Clinic名 / Role: member / 共有トークン残高 / プロフィール編集 / **このClinicから退出**。支払い管理・メンバー管理・代表者情報は**非表示**（かつRLSで不可視）
- Clinic未所属で切替しようとした場合: 「Clinicに所属していません。」

## 6. Library 保存フロー

1. 生成完了（Visual Simulation / Morphing）→ 保存シートに **患者/症例ピッカー**を表示: 「最近の患者」「新規患者を作成（patient_code 自動採番 P-0001…）」「あとで整理（未整理として保存）」
2. `library_items` insert（workspace_id 必須・patient_id/case_id は選択時のみ）＋ 画像/動画は private bucket へアップロード（path=`{workspace_id}/{item_id}.jpg|webm`）、metadata に before/after 参照・生成パラメータ・消費 ledger_id
3. Library UI: 患者別 / 症例別 / 作成日順 / 作成者 / item_type のフィルタ。**未整理 item には「患者・症例が未設定です。後から紐付けできます。」バッジ＋紐付けボタン**
4. item 詳細 → 患者ページ → 症例一覧 に相互リンク

**移行戦略（重要）**: 現行 Library は localStorage(`caseflow_project_library_v55`)+IndexedDB の端末ローカル。Phase 2.1 では**二重書き**（ローカル即時表示＋DB/Storage 永続）から始め、DB 読み出しを正とし、ローカルは オフラインキャッシュに格下げ。既存ローカル item は初回ログイン時に「クラウドへ移行しますか？」で一括アップロード。

## 7. 患者情報⇄生成物 紐付け仕様

- 紐付けキー: `library_items.workspace_id`（必須・NOT NULL）> `patient_id` > `case_id`（nullable、後付け可能）
- 生成時のトークン消費 ledger にも同じ `workspace_id/patient_id/case_id` を記録（§8）→ 課金・患者・生成物が1本の線で追跡可能
- 患者soft delete 時: library_items は残す（patient_id は残す・患者一覧から消えるだけ）。復元可能
- 患者識別ポリシー継続: patient_code/display_label は匿名。本名・生年月日・カルテ番号は入力欄を設けない

## 8. token_ledger 拡張とトークン消費

- 既存列 workspace_id / case_id（migration 1）＋ **patient_id 追加**のみ
- 新RPC `consume_workspace_tokens(ws, amount, reason, patient, case)`: `is_ws_member` 検証 → workspaces.tokens_remaining を原子的に減算 → ledger 記録（user_id=消費者）。Personal も Clinic も同一経路
- 返却は `refund_workspace_tokens`（既存 refund と同じガード: 本人 or ws-admin・15分・idempotency）
- Webhook 変更: 付与先を profiles → **workspaces**（billing_customers.workspace_id で解決）。Add-on/月次付与とも
- 消費コスト: Visual Simulation 2 / Morphing 2（現行どおり）
- owner/admin 向け「メンバー別消費」表示は ledger の (user_id, sum) 集計のみ（生成内容そのものは出さない）

## 9. 退会 / 退出 / 削除 / 解約（§9・§11 文言準拠）

| 操作 | 実行者 | 処理 | データ |
|---|---|---|---|
| **Personal退会** | 本人 | `deactivate_account`: 確認ダイアログ →（サブスク中なら「先に解約が必要です」でPortalへ誘導しブロック）→ profiles.account_status='deleted'（soft）＋ personal workspace soft delete ＋ auth ban（service_role で `banned_until` 設定 or Edge Functionで admin API）→ audit | 生成物は soft delete。30日後に物理削除をバッチ検討（Phase 2.2） |
| **Clinic退出** | member本人 | `leave_workspace`: status='left' → audit。「このClinicから退出します。あなたのアカウントは削除されません。」 | Clinic 内の患者/Library は**削除しない** |
| **メンバー削除** | owner | `remove_ws_member`: status='removed', removed_by/at → audit。「このユーザーをClinicから削除します。ユーザー本人のアカウントは削除されません。」 | 同上 |
| **Clinic解約** | owner | Stripe portal で cancel（既存フロー）→ webhook が status 反映。期間終了後は member の生成をブロック（canUseApp が workspace plan を見る）。既存トークン没収なし | 閲覧は当面許可（生成のみ制限） |
| **Clinic閉鎖** | owner | `close_clinic_workspace`: active member がいれば警告 → workspaces.deleted_at → 全 member アクセス不可 → audit | soft delete・復元可能 |

すべて `admin_audit_logs` に記録（action: account_deactivated / member_left / member_removed / workspace_closed）。

## 10. 既存コードへの影響範囲

| 領域 | 影響 | 大きさ |
|---|---|---|
| `cfConsumeToken` / `consume_tokens` | workspace 版 RPC へ切替（フォールバック連鎖: v2→v1） | 中 |
| Stripe webhook / checkout | 付与先とmetadataに workspace_id | 中 |
| `canUseApp` | active workspace の plan/tokens も判定に追加 | 小 |
| Account Sheet | 3分岐＋workspace切替＋退会導線 | 中 |
| Library（最大） | localStorage→DB/Storage 二重書き・患者ピッカー・フィルタUI | **大** |
| /admin | Billing/Users の workspace 列（優先度C） | 小 |
| 保存系（cfAutoSaveTempSim / setExportBlob / autoAddVideoToLibrary） | DB書き込み追加 | 中 |
| SMS UI | **撤去済み（本コミット）** | 済 |

## 11. 実装順序（案）

1. **2.1a 基盤**: migration 7（tables/RLS/helpers/personal自動作成/バックフィル）→ **適用・検証済み（2026-07-02、本番DB）**
2. **2.1b 財布切替**: consume/refund/webhook を workspace 経路へ。Account Sheet に残高=workspace 表示
3. **2.1c Clinic**: Clinic作成フロー・メンバー招待/削除/退出・Sheet 3分岐・個人情報遮蔽の検証
4. **2.1d Library**: patients/cases UI・保存時ピッカー・DB/Storage 二重書き・フィルタ・未整理紐付け
5. **2.1e 退会系**: Personal退会・Clinic解約/閉鎖・audit
6. 各段階で Preview 検証 → Production

## 12. 実装前に確認したいリスク・決定事項

1. **財布の一本化タイミング**: profiles.tokens_remaining → workspaces への移行中、旧クライアントキャッシュと新経路が混在する時間帯がある。移行 migration は「コピー＋以後 workspaces を正」とし、旧RPC consume_tokens は personal workspace に委譲する互換実装に差し替える方針でよいか
2. **Storage コスト/上限**: 生成物を Supabase Storage に永続すると容量課金が発生（画像~0.5MB・動画数MB/件）。48h 自動削除を維持するか、プラン別保存期間（Personal 30日 / Clinic 90日等）にするか
3. **既存 Stripe 契約の帰属**: 現在の billing_customers/subscriptions は user 紐付け。バックフィルで「その user の personal workspace」に帰属させる。Clinic 契約への付け替えは「新規 Clinic checkout」のみとし、既存 Personal 契約の移管はサポートしない（可否確認）
4. **メンバーの二重所属**: 1ユーザーが Personal + 複数 Clinic に所属可能とする設計。UI は当面「Personal＋1 Clinic」を想定し、複数 Clinic は表示だけ対応でよいか
5. **患者データの越境**: removed/left になった member が作成した患者・生成物は Clinic に残る（作成者名表示あり）。この扱いの規約明記が必要
6. **Auth の退会処理**: Supabase の user ban/delete は service_role が必要 → serverless 関数 `/api/account/deactivate` を新設する（フロントから直接は不可）
7. **library_items と実患者写真**: DB 保存開始＝クラウドに患者写真を置くことになる。利用規約・プライバシーポリシーの更新（保存場所・期間・削除権）を本実装前に整備すべき

---

**次のアクション**: migration 7 適用済み。次は §12 の 7 点確定を経て 2.1b（財布切替: consume/refund/webhook の workspace 経路化）に着手します。
