# GovDoc Work Plan

## Current Status (2026-03-11)

### Data Coverage
| 指標 | 数値 |
|------|------|
| ドキュメント総数 | 92,093件 |
| 添付ファイル | 59,289件 |
| PDF DL済 | 59,126件 (99.7%) |
| テキスト抽出済 | 58,558件 (98.8%) |
| 対応省庁 | 14/19省庁 |

### Covered Ministries (14)
国会, 厚労省, 国交省, 文科省, 経産省, 環境省, 内閣府, 農水省, 総務省, 首相官邸, 金融庁, 内閣官房, 財務省, 防衛省

### Uncovered Ministries (5)
デジタル庁, 法務省, 外務省, 警察庁, その他

---

## NEXT: 本番パイプライン稼働

以下を順に実施して日次自動更新を稼働させる:

1. **GitHub Actions Secrets を設定**
   - リポジトリの Settings → Secrets and variables → Actions に追加:
     - `TURSO_DATABASE_URL` — `libsql://govdoc-tsukukobaan.aws-ap-northeast-1.turso.io`
     - `TURSO_AUTH_TOKEN` — Turso JWT auth token
     - `R2_ACCOUNT_ID` — Cloudflare account ID
     - `R2_ACCESS_KEY_ID` — R2 API key
     - `R2_SECRET_ACCESS_KEY` — R2 secret
     - `R2_BUCKET_NAME` — `govdoc-pdfs`

2. **手動トリガーで初回テスト**
   - Actions タブ → "Update GovDoc Data" → "Run workflow"
   - `steps` に `scrape` だけ指定して小さくテスト
   - ログ artifact をダウンロードして結果確認

3. **全ステップ通しテスト**
   - 手動トリガーでステップ指定なし（全ステップ）実行
   - Turso上のデータが更新されることを確認
   - Vercel上のWebアプリで検索結果が反映されることを確認

4. **cronで日次自動実行を確認**
   - 翌日03:00 JST以降にActions履歴を確認
   - 成功していれば本番稼働完了

---

## Phase 1: データ完備 (Data Completion)

### 1.1 未対応省庁スクレイパー追加
- [ ] デジタル庁 (`digital.py`) — 審議会ページの構造調査 → スクレイパー実装
- [ ] 法務省 (`moj.py`) — 審議会ページの構造調査 → スクレイパー実装
- [ ] 外務省 (`mofa.py`) — 審議会ページの構造調査 → スクレイパー実装
- [ ] 警察庁 (`npa.py`) — 審議会ページの構造調査 → スクレイパー実装

### 1.2 残りPDF処理
- [ ] 未ダウンロード163件の処理（エラー原因調査・リトライ）
- [ ] テキスト未抽出 ~568件の再処理

### 1.3 Turso同期
- [ ] 最新データのTurso同期（`sync_to_turso.ts`）
- [ ] FTSインデックス再構築（`migrate_fts.ts`）
- [ ] 本番環境での動作確認

---

## Phase 2: 検索・UI改善

### 2.1 検索機能強化
- [ ] 検索結果のスニペットハイライト改善
- [ ] 日付範囲フィルター追加
- [ ] 委員会名での絞り込み
- [ ] 検索結果のソート（日付順/関連度順）
- [ ] 検索サジェスト・オートコンプリート

### 2.2 ページ改善
- [ ] 委員会詳細ページの充実（添付ファイル一覧・PDF閲覧リンク）
- [ ] ドキュメント詳細ページ（個別の議事録ビュー）
- [ ] レスポンシブ対応の改善
- [ ] ページネーションUI改善

### 2.3 トップページ
- [ ] 検索ボックスをトップページに統合
- [ ] 統計情報のビジュアル化
- [ ] 最近追加されたドキュメントフィード

---

## Phase 3: MCP Server拡張

### 3.1 機能追加
- [ ] FTS全文検索ツール追加（現在はタイトル検索のみ）
- [ ] 省庁一覧ツール追加
- [ ] ドキュメント統計ツール追加

### 3.2 Turso対応
- [ ] better-sqlite3 → libSQL client への移行
- [ ] リモートDB対応（ローカルdev.db依存の解消）

---

## Phase 4: 運用・インフラ

### 4.1 データ更新自動化
- [x] 統合パイプラインスクリプト (`scripts/update_pipeline.py`)
- [x] GitHub Actions定期実行 (`.github/workflows/update-data.yml`, 毎日03:00 JST)
- [x] FTS差分更新 (`scripts/update_fts.ts`)
- [x] 統計API (`/api/stats`)
- [x] 実行ログのJSON出力 (`logs/update_*.json`)
- [x] Turso直接書き込み対応 (`scripts/db.py`, dev.db転送不要)
- [ ] GitHub Actions Secrets の設定 → **NEXTセクション参照**
- [ ] 手動トリガーでの初回動作確認 → **NEXTセクション参照**
- [ ] `lastConfirmedAt` を活用したデータ鮮度管理

### 4.2 監視・品質
- [ ] スクレイプ結果のログ・エラー監視
- [ ] リンク切れ検出
- [ ] データ品質チェック（重複検出、日付異常など）

### 4.3 パフォーマンス
- [ ] Vercelデプロイの最適化（コールドスタート、Edge対応検討）
- [ ] 検索クエリのパフォーマンスチューニング
- [ ] CDNキャッシュ戦略の見直し

---

## Technical Debt

- [x] README.md をプロジェクト固有の内容に更新
- [ ] テスト追加（検索ロジック、スクレイパーの単体テスト）
- [ ] エラーハンドリングの統一（スクレイパー間で差異あり）
- [ ] Python scripts の型ヒント追加
