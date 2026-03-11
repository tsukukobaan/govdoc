/**
 * Incrementally update FTS5 search_index with new/updated attachments.
 *
 * Unlike migrate_fts.ts (full rebuild), this only inserts attachments
 * that are not yet in the FTS index.
 *
 * Usage: npx tsx scripts/update_fts.ts
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

  // Check if search_index exists
  const existing = await turso.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='search_index'"
  );
  if (existing.rows.length === 0) {
    console.log("search_index does not exist. Run migrate_fts.ts first.");
    process.exit(1);
  }

  // Count current FTS rows
  const currentCount = await turso.execute("SELECT COUNT(*) as cnt FROM search_index");
  console.log(`Current search_index rows: ${currentCount.rows[0].cnt}`);

  // Find attachments that are downloaded but not yet in FTS
  // FTS content table rowid maps to attachments.id
  const newAttachments = await turso.execute(`
    SELECT a.id, a.title, COALESCE(a.text_content, '') as text_content
    FROM attachments a
    WHERE a.is_downloaded = 1
      AND a.id NOT IN (SELECT rowid FROM search_index)
  `);

  if (newAttachments.rows.length === 0) {
    console.log("No new attachments to index.");
    turso.close();
    return;
  }

  console.log(`Found ${newAttachments.rows.length} new attachments to index.`);

  // Insert in batches
  const BATCH_SIZE = 100;
  let inserted = 0;

  for (let i = 0; i < newAttachments.rows.length; i += BATCH_SIZE) {
    const batch = newAttachments.rows.slice(i, i + BATCH_SIZE);
    const statements = batch.map((row) => ({
      sql: "INSERT INTO search_index(rowid, title, text_content) VALUES (?, ?, ?)",
      args: [row.id, row.title, row.text_content],
    }));

    await turso.batch(statements, "write");
    inserted += batch.length;

    if (inserted % 1000 === 0) {
      console.log(`  ... ${inserted} indexed`);
    }
  }

  console.log(`Indexed ${inserted} new attachments.`);

  // Verify
  const finalCount = await turso.execute("SELECT COUNT(*) as cnt FROM search_index");
  console.log(`search_index now has ${finalCount.rows[0].cnt} rows.`);

  console.log("Done!");
  turso.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
