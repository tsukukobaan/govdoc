# GovDoc - 政府審議会ドキュメント検索

日本政府の審議会・委員会の議事録・資料を横断検索できるWebアプリケーション。

## Tech Stack

- **Frontend**: Next.js 16 (App Router) + React 19 + Tailwind CSS 4
- **DB**: SQLite (dev.db) → Turso (libSQL) for production
- **ORM**: Prisma 7 with @prisma/adapter-libsql
- **Storage**: Cloudflare R2 (PDF保存・公開CDN)
- **Deploy**: Vercel (ISR 24h)
- **Scripts**: Python (スクレイパー・データパイプライン)
- **MCP Server**: TypeScript + better-sqlite3 (Claude連携ツール)

## Project Structure

```
web/
├── src/app/                 # Next.js App Router pages
│   ├── page.tsx             # トップページ（省庁一覧・統計）
│   ├── search/page.tsx      # 検索ページ（FTS全文検索対応）
│   ├── ministries/[slug]/   # 省庁別ページ
│   └── api/search/          # 検索API
├── src/lib/
│   ├── db.ts                # Prisma client (Turso adapter)
│   └── turso.ts             # Raw libSQL client (FTS queries)
├── src/components/          # UI components
├── prisma/schema.prisma     # DB schema (Ministry→Committee→Document→Attachment)
├── scripts/
│   ├── scrapers/            # 省庁別Webスクレイパー (Python)
│   ├── import_nistep.py     # NISTEPデータ取り込み
│   ├── import_kokkai.py     # 国会会議録API取り込み
│   ├── crawl_attachments.py # 添付ファイルURL収集
│   ├── download_pdfs.py     # PDF DL & テキスト抽出
│   ├── sync_to_turso.ts     # ローカルDB → Turso同期
│   └── migrate_fts.ts       # FTS5テーブル作成
└── mcp-server/              # MCP Server (Claude連携)
```

## Key Commands

```bash
npm run dev              # 開発サーバー起動
npm run build            # ビルド

# Data pipeline (unified)
python scripts/update_pipeline.py                      # Full pipeline (scrape→sync)
python scripts/update_pipeline.py --steps scrape,kokkai  # Specific steps
python scripts/update_pipeline.py --skip-sync          # Local DB only
python scripts/update_pipeline.py --dry-run            # Preview

# Individual steps
python scripts/scrape_all.py                           # Scrape all ministries
python scripts/import_kokkai.py                        # Import Diet records
python scripts/crawl_attachments.py                    # Discover attachment URLs
python scripts/download_pdfs.py                        # Download PDFs + extract text
npx tsx scripts/sync_to_turso.ts                       # Sync dev.db → Turso
npx tsx scripts/update_fts.ts                          # Incremental FTS index update
npx tsx scripts/migrate_fts.ts                         # Full FTS index rebuild
```

## Database

- Prismaモデル名は PascalCase、DBテーブルは snake_case (@@map使用)
- FTS5 virtual table `search_index` で全文検索 (turso.ts経由で直接SQL)
- dev.db (2GB+) はgit管理外

## Conventions

- TypeScript strict mode
- App Router (RSC) — サーバーコンポーネント中心
- ページは `revalidate = 86400` (24h ISR)
- Python scripts は `scripts/.venv/` の仮想環境を使用

## Data Update Pipeline

`scripts/update_pipeline.py` が全ステップを統合管理。
`scripts/db.py` がDB接続を抽象化:
- `TURSO_DATABASE_URL` 設定時 → `libsql-experimental` でTurso直接書き込み（CI用）
- 未設定時 → `sqlite3` でローカル `dev.db` に書き込み（ローカル開発用）

ステップ:
1. **scrape** — 省庁Webサイトのスクレイプ
2. **kokkai** — 国会会議録APIからインポート
3. **crawl** — 添付ファイルURL収集
4. **download** — PDF DL & テキスト抽出 & R2アップロード
5. **sync** — dev.db → Turso同期（Turso直接モード時は自動スキップ）
6. **fts** — FTS5インデックスの差分更新

実行ログは `logs/update_YYYYMMDD_HHMMSS.json` に保存。
GitHub Actions (`.github/workflows/update-data.yml`) で毎日03:00 JST自動実行。

## API Endpoints

- `GET /api/search?q=...` — 全文検索
- `GET /api/stats` — データベース統計情報

## Work Plan

詳細は [docs/WORKPLAN.md](docs/WORKPLAN.md) を参照。
