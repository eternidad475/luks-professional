# トークン有効期限設計（Phase 2.2 提案 — 未適用・レビュー用）

> ステータス: **設計案のみ。本番DBには一切適用していない。**
> 適用は 2.1b（wallet の workspace 移行）と同時または直後に行うのが最小コスト。

## 1. ポリシー（確定したい仕様）

| source | 期限 | 備考 |
|---|---|---|
| `trial` | **付与から30日** | Trial 10 tokens |
| `invite`（invitee grant） | **付与から30日** | 10 tokens。trial と重複付与なし（実装済み） |
| `invite_bonus`（inviter） | **付与から30日** | 5 tokens |
| `subscription` | **次回更新日まで**（`current_period_end`） | webhook の invoice 期間をそのまま `expires_at` に |
| `addon` | **無期限（推奨）** | 購入トークンの短期失効はクレームリスク。期限を設ける場合は購入前・購入後・Wallet で明示必須 |
| `admin` | 無期限（付与時に指定可能） | 運用裁量 |
| `legacy` | 無期限 | 移行時の既存残高（下記 §4） |

消費順序: **期限が近い batch から先に消費**（expires_at NULLS LAST → created_at ASC）。
ユーザーに最も不利にならない順序であり、subscription 分を月内に使い切ってから addon に手を付ける自然な挙動になる。

## 2. スキーマ（additive のみ）

```sql
create table public.token_batches (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references public.workspaces(id) on delete cascade,
  user_id          uuid references auth.users(id),   -- 付与対象（監査用。財布は workspace）
  source           text not null check (source in
                     ('trial','invite','invite_bonus','subscription','addon','admin','legacy')),
  granted_tokens   integer not null check (granted_tokens >= 0),
  remaining_tokens integer not null check (remaining_tokens >= 0),
  expires_at       timestamptz,                      -- null = 無期限
  expired_at       timestamptz,                      -- 失効処理実行済みマーカー
  reason           text,
  ledger_id        bigint references public.token_ledger(id),  -- 付与元 ledger 行
  created_at       timestamptz not null default now(),
  check (remaining_tokens <= granted_tokens)
);
create index on public.token_batches (workspace_id, expires_at asc nulls last, created_at asc)
  where remaining_tokens > 0 and expired_at is null;
-- RLS: workspace member read（is_ws_member）。insert/update は RPC / service_role のみ
```

`token_ledger` への追加はなし（reason に `expired_tokens` を追加使用するのみ）。
**tokens_remaining（profiles / workspaces）は「= 有効 batch の remaining 合計」という導出値**に位置づけを変え、
互換のため列は残す（読み取り経路を壊さない）。

## 3. RPC 変更（2.2 で同一トランザクション切替）

- `consume_tokens` v3: 有効 batch を期限昇順にロック(`for update skip locked`は不要・単一ws)→ 順に減算 →
  ledger 1行（metadata に `{batch_breakdown:[{batch_id,used}]}`）→ profiles/workspaces 合計を同Txで更新
- `refund_generation_tokens` v2: 消費 ledger の batch_breakdown を逆順に戻す（失効済み batch へは戻さず
  新規 `source='admin', reason='refund'` batch を作成）
- 付与系（invite / trial / webhook grant / admin_grant）: ledger 挿入と同時に batch を1行作成
- 失効ジョブ: `pg_cron`（Supabase 拡張・有効化必要）で日次:
  ```
  期限切れ・remaining>0 の batch → remaining を 0 に・expired_at=now()
  → token_ledger に delta = -remaining, reason='expired_tokens'（workspace_id/batch参照付き）
  → profiles / workspaces の合計を同Txで減算
  ```
- 失効の**事前通知**: Wallet UI バッジ（§5）+ 将来的にメール（14日前/3日前）

## 4. 移行方針（破壊的変更なし・3段階）

1. **2.2a（additive）**: `token_batches` 作成 + 既存残高を
   `source='legacy', expires_at=null` の1 batch として workspace ごとにバックフィル。
   この時点では何も読まれない（既存RPCは従来どおり）→ **リスクゼロ・いつでもrollback可（drop table のみ）**
2. **2.2b（切替）**: 上記RPC群を batch 読み書きに差し替え（1 migration・同一Tx）。
   切替直後から `tokens_remaining == sum(batches.remaining)` を invariant として整合性クエリで監視
3. **2.2c（失効有効化）**: pg_cron ジョブ登録。初回は dry-run（対象0件のはず — 期限付き batch は
   2.2b 以降の新規付与のみ。**既存ユーザーの既得トークンには遡及適用しない**）

ロールバック: 2.2b で問題が出た場合、RPC を旧版（totals 直接減算）に戻すだけで復旧
（totals は常に同Txで更新しているため drift しない）。ledger は追記のみで一切書き換えない。

## 5. Wallet UI（将来表示）

- 保有トークン合計（現行表示）
- 内訳: 「期限あり N tokens（最短 M/D まで）」「期限なし N tokens」
- 14日以内に失効する batch がある場合: 「⚠ N tokens が M/D に失効します」
- 追加購入モーダルの addon 説明に「購入トークンに有効期限はありません」を明記

## 6. 既存データとの整合性

- token_ledger: 追記のみ。過去行の編集なし。`expired_tokens` は負 delta の通常行として合計と自然に整合
- 既存の `invite_grant_policy_adjustment` 等の補正行もそのまま（legacy batch に織込み済みの残高が起点）
- 監視クエリ（2.2b 以降 daily で確認）:
  ```sql
  select w.id from workspaces w
  join (select workspace_id, coalesce(sum(remaining_tokens),0) s
          from token_batches where expired_at is null group by 1) b on b.workspace_id=w.id
  where w.tokens_remaining <> b.s;   -- 0行が正常
  ```
