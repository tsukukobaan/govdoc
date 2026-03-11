# GovDoc — 政府審議会ドキュメント検索

日本政府の省庁・審議会・委員会の議事録・資料を横断検索できるWebアプリケーション。
92,000件超のドキュメントと58,000件超のPDF全文検索に対応。

## Tech Stack

| レイヤー | 技術 |
|----------|------|
| Frontend | Next.js 16 (App Router) + React 19 + Tailwind CSS 4 |
| Database | Turso (libSQL) — クラウドSQLite |
| ORM | Prisma 7 + @prisma/adapter-libsql |
| Storage | Cloudflare R2 (PDF保存 + 公開CDN) |
| Deploy | Vercel (ISR 24h) |
| CI/CD | GitHub Actions (日次データ更新) |
| Scripts | Python (スクレイパー・データパイプライン) |

## Getting Started

```bash
cd web
npm install
npm run dev
```

http://localhost:3000 で開発サーバーが起動します。

### 環境変数

`.env.local` に以下を設定:

```env
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=govdoc-pdfs
R2_PUBLIC_URL=https://...
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  GitHub Actions (daily 03:00 JST)                   │
│                                                     │
│  scrape → kokkai → crawl → download → fts           │
│    │        │        │        │         │            │
│    └────────┴────────┴────────┴─────────┘            │
│              ↓ libsql-experimental                  │
│           ┌──────┐     ┌────┐                       │
│           │ Turso│     │ R2 │ (PDFs)                │
│           └──┬───┘     └──┬─┘                       │
└──────────────┼────────────┼─────────────────────────┘
               │            │
        ┌──────┴──────┐     │
        │  Vercel     │     │
        │  Next.js    ├─────┘
        │  (Frontend) │
        └─────────────┘
```

### Data Pipeline

`scripts/update_pipeline.py` が全ステップを統合管理:

1. **scrape** — 13省庁のWebサイトからドキュメントメタデータを収集
2. **kokkai** — 国会会議録APIから国会審議データをインポート
3. **crawl** — ドキュメントページから添付ファイル（PDF等）のURLを抽出
4. **download** — PDFをダウンロード → テキスト抽出 → R2にアップロード
5. **fts** — FTS5全文検索インデックスの差分更新

DB接続は `scripts/db.py` が自動切替:
- `TURSO_DATABASE_URL` 設定時 → Turso直接書き込み（CI用）
- 未設定時 → ローカル `dev.db` に書き込み（開発用）

```bash
# Full pipeline
python scripts/update_pipeline.py

# Specific steps
python scripts/update_pipeline.py --steps scrape,kokkai

# Local only (no Turso sync)
python scripts/update_pipeline.py --skip-sync

# Preview
python scripts/update_pipeline.py --dry-run
```

## Project Structure

```
web/
├── src/
│   ├── app/                     # Next.js App Router
│   │   ├── page.tsx             # トップ（省庁一覧・統計）
│   │   ├── search/page.tsx      # 検索（FTS全文検索対応）
│   │   ├── ministries/[slug]/   # 省庁別ページ
│   │   └── api/
│   │       ├── search/          # 検索API
│   │       └── stats/           # 統計API
│   ├── lib/
│   │   ├── db.ts                # Prisma client (Turso adapter)
│   │   └── turso.ts             # Raw libSQL client (FTS queries)
│   └── components/              # UI components
├── prisma/schema.prisma         # DB schema
├── scripts/
│   ├── db.py                    # 共有DB接続モジュール
│   ├── update_pipeline.py       # 統合パイプライン
│   ├── scrape_all.py            # 全省庁スクレイプ
│   ├── scrapers/                # 省庁別スクレイパー (13省庁)
│   ├── import_kokkai.py         # 国会API取り込み
│   ├── crawl_attachments.py     # 添付ファイルURL収集
│   ├── download_pdfs.py         # PDF DL & テキスト抽出
│   ├── sync_to_turso.ts         # ローカルDB → Turso同期
│   ├── update_fts.ts            # FTS差分更新
│   └── migrate_fts.ts           # FTS全再構築
├── mcp-server/                  # MCP Server (Claude連携)
└── .github/workflows/           # GitHub Actions
```

## Data Coverage

| 省庁 | ドキュメント数 |
|------|---------------|
| 国会 | 27,760 |
| 厚生労働省 | 11,694 |
| 国土交通省 | 9,850 |
| 文部科学省 | 8,260 |
| 経済産業省 | 8,167 |
| 環境省 | 6,390 |
| 内閣府 | 5,530 |
| 農林水産省 | 4,227 |
| 総務省 | 2,822 |
| 首相官邸 | 2,613 |
| 金融庁 | 1,802 |
| 内閣官房 | 1,290 |
| 財務省 | 1,194 |
| 防衛省 | 494 |

## License

Private project.
