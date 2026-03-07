/**
 * Apply Phase 2 schema migration to Turso remote database.
 * Adds is_index_page, index_crawled_at to documents, and creates attachments table.
 *
 * Usage: npx tsx scripts/migrate_turso.ts
 */
import { config } from "dotenv";
config({ path: ".env.local" });

import { createClient } from "@libsql/client";

async function main() {
  const url = process.env.TURSO_DATABASE_URL;
  const authToken = process.env.TURSO_AUTH_TOKEN;
  console.log("Turso URL:", url);

  if (!url) {
    console.error("TURSO_DATABASE_URL not set");
    process.exit(1);
  }

  const turso = createClient({ url, authToken });

  // 1. Add new columns to documents
  for (const [col, def] of [
    ["is_index_page", "INTEGER NOT NULL DEFAULT 0"],
    ["index_crawled_at", "TEXT"],
  ] as const) {
    try {
      await turso.execute(`ALTER TABLE documents ADD COLUMN ${col} ${def}`);
      console.log(`Added column documents.${col}`);
    } catch (e: unknown) {
      const msg = (e as Error).message || "";
      if (msg.includes("duplicate column")) {
        console.log(`Column documents.${col} already exists, skipping`);
      } else {
        console.error(`Error adding ${col}:`, msg);
      }
    }
  }

  // 2. Create attachments table
  await turso.execute(`
    CREATE TABLE IF NOT EXISTS attachments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      document_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      url TEXT NOT NULL,
      file_type TEXT NOT NULL DEFAULT 'pdf',
      file_size INTEGER,
      page_count INTEGER,
      local_path TEXT,
      text_content TEXT,
      is_downloaded INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now')),
      FOREIGN KEY (document_id) REFERENCES documents(id)
    )
  `);
  console.log("Created attachments table (if not exists)");

  await turso.execute(
    "CREATE INDEX IF NOT EXISTS attachments_document_id_idx ON attachments(document_id)"
  );
  await turso.execute(
    "CREATE INDEX IF NOT EXISTS attachments_url_idx ON attachments(url)"
  );
  console.log("Created indexes");

  // Verify
  const cols = await turso.execute("PRAGMA table_info(documents)");
  console.log("\ndocuments columns:", cols.rows.map((r) => r.name).join(", "));

  const attCols = await turso.execute("PRAGMA table_info(attachments)");
  console.log("attachments columns:", attCols.rows.map((r) => r.name).join(", "));

  console.log("\nDone!");
  turso.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
