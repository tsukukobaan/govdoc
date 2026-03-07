/**
 * Create FTS5 virtual table for full-text search on attachments.
 *
 * - Creates `search_index` FTS5 table (title + text_content)
 * - Populates with existing downloaded attachments
 *
 * Usage: npx tsx scripts/migrate_fts.ts
 */
import "dotenv/config";
import { createClient } from "@libsql/client";

async function main() {
  const tursoUrl = process.env.TURSO_DATABASE_URL;
  const tursoToken = process.env.TURSO_AUTH_TOKEN;

  if (!tursoUrl) {
    console.error("TURSO_DATABASE_URL is not set");
    process.exit(1);
  }

  const turso = createClient({
    url: tursoUrl,
    authToken: tursoToken,
  });

  console.log("Connected to Turso.");

  // Drop existing FTS table if needed (for re-runs)
  const existing = await turso.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='search_index'"
  );
  if (existing.rows.length > 0) {
    console.log("Dropping existing search_index table...");
    await turso.execute("DROP TABLE search_index");
  }

  // Create FTS5 virtual table
  console.log("Creating FTS5 virtual table search_index...");
  await turso.execute(`
    CREATE VIRTUAL TABLE search_index USING fts5(
      title,
      text_content,
      content='attachments',
      content_rowid='id',
      tokenize='unicode61'
    )
  `);

  // Populate with existing data
  console.log("Populating search_index with existing attachment data...");
  const result = await turso.execute(`
    INSERT INTO search_index(rowid, title, text_content)
    SELECT id, title, COALESCE(text_content, '') FROM attachments WHERE is_downloaded = 1
  `);

  console.log(`Inserted ${result.rowsAffected} rows into search_index.`);

  // Verify
  const count = await turso.execute("SELECT COUNT(*) as cnt FROM search_index");
  console.log(`search_index now has ${count.rows[0].cnt} rows.`);

  console.log("Done!");
  turso.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
