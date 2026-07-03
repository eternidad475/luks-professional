# Account Types, Plans, Wallets & Clinic Model

> ステータス: 設計・監査記録（2026-07-13）。Account UI は ACCOUNT / ACCOUNT TYPE /
> PLAN / WALLET の4セクションに分離済み。Clinic のメンバー/共有トークン運用は
> 一部が将来実装（本ドキュメントに安全要件を明記）。

## 1. アカウントタイプ と 料金プランは別概念

**アカウントタイプ**（誰が・どの単位で使うか。`workspaces.type` に対応）:

| key | 表示 | 説明 |
|---|---|---|
| `personal` | パーソナル | 個人利用のアカウント |
| `clinic` | クリニック | 医院・チーム利用（owner 視点） |
| `clinic_member` | クリニックメンバー | clinic workspace に member として所属（owner 以外） |
| `clinic_shared_seat` | 共有端末用アカウント | クリニック内の共有端末で使う制限付きアカウント（§5） |

- 現在の本番 `workspaces.type` は `personal` / `clinic` のみ。全3ユーザーが `personal`。
- UI（`cfAccountType()`）は上記4種を表示できるよう拡張済み。member/shared_seat は
  clinic membership が実装され次第、判定を接続する。

**料金プラン**（課金。`billing_subscriptions.plan` / Stripe に対応）:

| key | 表示 | 内容 | ウォレット |
|---|---|---|---|
| `trial` | Trial | 初回のみ無料10トークン | 個人 |
| `invite_beta` | Invite Beta | 招待ベータ / 月額契約なし | 個人 |
| `free` | Free | 無料プラン | 個人 |
| `sketch`(=personal) | Sketch | 月額1,500円 / 100 tokens | 個人 (`profiles.tokens_remaining`) |
| `studio` | Studio | 月額3,000円 / 500 tokens | 個人 |
| `clinic_studio`(=clinic) | Clinic Studio | 月額5,000円 / 500 tokens | クリニック (`workspaces.tokens_remaining`) |
| `developer` | Developer | 開発者用 / 月額契約なし | 個人 |
| `addon` | Add-on | 買い切り追加トークン | 利用中のウォレット |

**PLAN 解決順（`cfCurrentPlan()`）**: Stripe subscription(active/trialing/past_due) →
`beta_access` → `developer` role → Free。role と plan と beta_access を混同しない。
`developer` role でも beta_access があれば表示は Invite Beta（有料プラン扱いにしない）。

## 2. ウォレット（個人 / クリニック）

- **個人ウォレット** = `profiles.tokens_remaining`。個人利用時の生成で消費。Trial /
  Sketch / Add-on(個人時) はここに紐づく。
- **クリニックウォレット** = `workspaces.tokens_remaining`（type=clinic）。クリニック
  利用時の生成で消費。Clinic Studio / Add-on(クリニック時) はここ。
- 個人ウォレットとクリニックウォレットは**混ぜない**。クリニック所属メンバーに
  個人トークンを自動付与しない。active member のみクリニックウォレットを使える。

## 3. メンバー解除時のアクセス権失効（実装済み・RLSで自動）

- `ws_role(ws)` は `workspace_members.status = 'active'` のみを対象にする。
- したがって `is_ws_member` / `is_ws_owner` / `is_ws_admin` は removed/left member に
  対して false を返す → cases / patients / library_items / billing_* の RLS が
  **自動的にアクセスを失効**させる（過去URL / API直叩きでも読めない）。
- メンバー解除は `workspace_members.status = 'removed'`（+ `removed_at` / `removed_by`
  を記録する運用）で行う。auth user / profiles / personal workspace は残す。
- 失効するのは「クリニック共有トークン/データへのアクセス権」であり、本人の
  **個人トークン（profiles.tokens_remaining）は残す**。

## 4. 直接改ざん防止（実装済み）

- `profiles`: role / tokens_remaining / beta_access / account_status 等は
  authenticated から直接 UPDATE 不可（migration 12）。編集可能列は display_name /
  clinic_name / professional_type / professional_confirmed のみ。
- `workspaces`: type / plan / tokens_remaining / owner_user_id / deleted_at は
  authenticated から直接 UPDATE 不可（migration 15）。編集可能列は name /
  clinic_phone / clinic_address のみ。type/plan/tokens の変更は SECURITY DEFINER
  RPC または owner-gated 移行 RPC / 管理者処理経由のみ。
- `personal → clinic` 移行はフロントから `workspaces.type` を直接書き換えず、将来の
  専用 owner-gated RPC（医院名等の入力 + Clinic Studio checkout）で行う。UI は
  Personal ユーザーが Clinic Studio を選ぶと**移行確認**を表示（即課金/即type変更しない）。
- `clinic → personal` は安易に戻せない。clinic 契約・メンバー・共有データ・請求が
  絡むため、UI は「個人プランに戻すにはサポートへ」と表示し、将来は管理者承認制 /
  厳格な条件付きにする。

## 5. 共有端末アカウント（Clinic Shared Seat）方針

原則は**個別メンバー登録を推奨**（誰が生成/患者画像を扱ったかの監査性、退職者の
資格情報リスク回避のため）。共有端末運用を許容する場合は Clinic Shared Seat として
制限付きで扱う:

- 管理者権限なし / 支払い管理不可 / メンバー管理不可 / role 変更不可
- developer/admin 操作不可 / invite 発行不可（または管理者のみ）
- 生成・閲覧など限定機能のみ / 操作ログに shared seat と記録
- クリニック管理者がいつでも無効化できる

（現時点で shared seat は未実装。実装時は上記制限を RLS/RPC/UI の全層で担保すること。）

## 6. 生成時のトークン消費（現状と将来要件）

- **現状**: 生成時の消費は `profiles.tokens_remaining`（個人ウォレット）に対して
  `consume_token(s)` SECURITY DEFINER RPC 経由で行われる。クリニックウォレット
  （workspaces.tokens_remaining）からの消費は**未実装**。
- **将来 clinic wallet 消費を実装する際の安全要件**:
  - `selected_workspace_id` をフロントから受け取っても信用しない。サーバー/RPC 側で
    `is_ws_member(ws)`（= active member）を必ず検証してから消費する。
  - removed/left member はクリニックウォレットを消費できない（ws_role の active 判定で
    自動遮断されるが、消費 RPC 内でも明示チェック）。
  - 一般メンバーはクリニックウォレットを**増やせない**（tokens_remaining は
    SECURITY DEFINER RPC / owner-gated のみ）。
  - 消費は `workspaces.tokens_remaining` と `token_ledger`（workspace_id 付き）の
    整合を崩さないよう単一 RPC でアトミックに行う。
  - Add-on購入・プラン変更は clinic owner / admin / billing_manager のみ。shared seat
    と一般メンバーは不可。

## 7. 課金 / Stripe（実装済みの安全性）

- checkout / billing portal は Authorization Bearer トークンをサーバー側 `getUser` で
  検証し、認証ユーザー本人の billing_customers から Stripe customer を導出
  （user_id をフロントから信用しない・顧客ID取り違えなし）。
- service_role / Stripe secret はサーバー env のみ。webhook は署名検証。
- 一般メンバー / shared seat は clinic billing を閲覧・操作できない（RLS: billing_* は
  own / ws_owner / admin のみ SELECT、書き込みポリシーなし）。
