/**
 * Sync local dev.db (SQLite) to Turso remote database.
 *
 * - Committees: matched by (ministry_id, slug), upserts name/document_count
 * - Documents: matched by url (INSERT OR IGNORE to skip duplicates)
 *
 * Usage: npx tsx scripts/sync_to_turso.ts
 */
import "dotenv/config";
import { createClient, type Client, type Row } from "@libsql/client";
import { join } from "path";

const LOCAL_DB_PATH = join(__dirname, "..", "dev.db");

async function main() {
  const tursoUrl = process.env.TURSO_DATABASE_URL;
  const tursoToken = process.env.TURSO_AUTH_TOKEN;

  if (!tursoUrl) {
    console.error("TURSO_DATABASE_URL is not set");
    process.exit(1);
  }

  // Connect to local SQLite via file: URL
  const local = createClient({ url: `file:${LOCAL_DB_PATH}` });

  // Connect to Turso
  const turso = createClient({
    url: tursoUrl,
    authToken: tursoToken,
  });

  console.log("Connected to local DB and Turso.");

  // --- Step 1: Build ministry slug->id mapping from Turso ---
  const tursoMinistries = await turso.execute("SELECT id, slug FROM ministries");
  const tursoMinistryMap = new Map<string, number>();
  for (const row of tursoMinistries.rows) {
    tursoMinistryMap.set(row.slug as string, row.id as number);
  }
  console.log(`Turso has ${tursoMinistryMap.size} ministries.`);

  // Local ministry id->slug mapping
  const localMinistries = await local.execute("SELECT id, slug FROM ministries");
  const localMinistryIdToSlug = new Map<number, string>();
  for (const row of localMinistries.rows) {
    localMinistryIdToSlug.set(row.id as number, row.slug as string);
  }

  // --- Step 2: Sync committees ---
  console.log("\nSyncing committees...");
  const localCommittees = await local.execute("SELECT * FROM committees");

  // Build mapping: local committee id -> turso committee id
  const committeeIdMap = new Map<number, number>();
  let committeeInserted = 0;
  let committeeUpdated = 0;

  for (const c of localCommittees.rows) {
    const ministrySlug = localMinistryIdToSlug.get(c.ministry_id as number);
    if (!ministrySlug) continue;

    const tursoMinistryId = tursoMinistryMap.get(ministrySlug);
    if (!tursoMinistryId) {
      console.warn(`  Ministry slug "${ministrySlug}" not found in Turso, skipping committee "${c.name}"`);
      continue;
    }

    // Check if committee exists in Turso by (ministry_id, slug)
    const existing = await turso.execute({
      sql: "SELECT id FROM committees WHERE ministry_id = ? AND slug = ?",
      args: [tursoMinistryId, c.slug],
    });

    if (existing.rows.length > 0) {
      // Update
      const tursoCommitteeId = existing.rows[0].id as number;
      committeeIdMap.set(c.id as number, tursoCommitteeId);
      await turso.execute({
        sql: "UPDATE committees SET name = ?, document_count = ?, updated_at = ? WHERE id = ?",
        args: [c.name, c.document_count, c.updated_at, tursoCommitteeId],
      });
      committeeUpdated++;
    } else {
      // Insert
      const result = await turso.execute({
        sql: `INSERT INTO committees (ministry_id, name, slug, category, url, is_active, document_count, created_at, updated_at)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        args: [
          tursoMinistryId,
          c.name,
          c.slug,
          c.category,
          c.url,
          c.is_active,
          c.document_count,
          c.created_at,
          c.updated_at,
        ],
      });
      committeeIdMap.set(c.id as number, Number(result.lastInsertRowid));
      committeeInserted++;
    }
  }

  console.log(`  Committees: ${committeeInserted} inserted, ${committeeUpdated} updated`);

  // --- Step 3: Sync documents ---
  console.log("\nSyncing documents...");

  // Get existing URLs from Turso for dedup
  const tursoUrls = await turso.execute("SELECT url FROM documents");
  const existingUrls = new Set<string>();
  for (const row of tursoUrls.rows) {
    existingUrls.add(row.url as string);
  }
  console.log(`  Turso already has ${existingUrls.size} documents.`);

  const localDocuments = await local.execute("SELECT * FROM documents");

  let docInserted = 0;
  let docSkipped = 0;
  const BATCH_SIZE = 100;
  let batch: Row[] = [];

  for (const d of localDocuments.rows) {
    if (existingUrls.has(d.url as string)) {
      docSkipped++;
      continue;
    }

    const tursoCommitteeId = committeeIdMap.get(d.committee_id as number);
    if (!tursoCommitteeId) {
      docSkipped++;
      continue;
    }

    batch.push(d);

    if (batch.length >= BATCH_SIZE) {
      await insertDocumentBatch(turso, batch, committeeIdMap);
      docInserted += batch.length;
      batch = [];
      if (docInserted % 1000 === 0) {
        console.log(`  ... ${docInserted} documents inserted`);
      }
    }
  }

  // Flush remaining
  if (batch.length > 0) {
    await insertDocumentBatch(turso, batch, committeeIdMap);
    docInserted += batch.length;
  }

  console.log(`  Documents: ${docInserted} inserted, ${docSkipped} skipped (duplicates or unmapped)`);

  // --- Step 4: Sync attachments ---
  console.log("\nSyncing attachments...");

  // Check if attachments table exists in Turso
  const tursoTables = await turso.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='attachments'"
  );
  if (tursoTables.rows.length === 0) {
    console.log("  Creating attachments table in Turso...");
    await turso.execute(`
      CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        file_type TEXT NOT NULL DEFAULT 'pdf',
        file_size INTEGER,
        page_count INTEGER,
        is_downloaded INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES documents(id)
      )
    `);
    await turso.execute("CREATE INDEX IF NOT EXISTS idx_attachments_document_id ON attachments(document_id)");
    await turso.execute("CREATE INDEX IF NOT EXISTS idx_attachments_url ON attachments(url)");
  }

  // Ensure text_content column exists in Turso attachments table
  const colCheck = await turso.execute("PRAGMA table_info(attachments)");
  const hasTextContent = colCheck.rows.some((r) => r.name === "text_content");
  if (!hasTextContent) {
    console.log("  Adding text_content column to attachments table...");
    await turso.execute("ALTER TABLE attachments ADD COLUMN text_content TEXT");
  }

  // Build document id mapping: local url -> turso document id
  const tursoDocRows = await turso.execute("SELECT id, url FROM documents");
  const tursoDocUrlToId = new Map<string, number>();
  for (const row of tursoDocRows.rows) {
    tursoDocUrlToId.set(row.url as string, row.id as number);
  }

  const localDocRows = await local.execute("SELECT id, url FROM documents");
  const localDocIdToUrl = new Map<number, string>();
  for (const row of localDocRows.rows) {
    localDocIdToUrl.set(row.id as number, row.url as string);
  }

  // Get existing attachment URLs from Turso for dedup
  const tursoAttachmentUrls = await turso.execute("SELECT url FROM attachments");
  const existingAttachmentUrls = new Set<string>();
  for (const row of tursoAttachmentUrls.rows) {
    existingAttachmentUrls.add(row.url as string);
  }
  console.log(`  Turso already has ${existingAttachmentUrls.size} attachments.`);

  // Sync attachments (exclude local_path - local only; include text_content for FTS)
  const localAttachments = await local.execute(
    "SELECT id, document_id, title, url, file_type, file_size, page_count, text_content, is_downloaded, created_at, updated_at FROM attachments"
  );

  let attachmentInserted = 0;
  let attachmentUpdated = 0;
  let attachmentSkipped = 0;
  let attachmentBatch: Row[] = [];
  let updateBatch: Row[] = [];

  for (const a of localAttachments.rows) {
    const localDocUrl = localDocIdToUrl.get(a.document_id as number);
    if (!localDocUrl) {
      attachmentSkipped++;
      continue;
    }
    const tursoDocId = tursoDocUrlToId.get(localDocUrl);
    if (!tursoDocId) {
      attachmentSkipped++;
      continue;
    }

    if (existingAttachmentUrls.has(a.url as string)) {
      // Update existing attachment with download status
      if (a.is_downloaded) {
        updateBatch.push(a);
        if (updateBatch.length >= BATCH_SIZE) {
          await updateAttachmentBatch(turso, updateBatch);
          attachmentUpdated += updateBatch.length;
          updateBatch = [];
        }
      } else {
        attachmentSkipped++;
      }
      continue;
    }

    attachmentBatch.push({ ...a, _tursoDocId: tursoDocId } as unknown as Row);

    if (attachmentBatch.length >= BATCH_SIZE) {
      await insertAttachmentBatch(turso, attachmentBatch);
      attachmentInserted += attachmentBatch.length;
      attachmentBatch = [];
    }
  }

  if (attachmentBatch.length > 0) {
    await insertAttachmentBatch(turso, attachmentBatch);
    attachmentInserted += attachmentBatch.length;
  }
  if (updateBatch.length > 0) {
    await updateAttachmentBatch(turso, updateBatch);
    attachmentUpdated += updateBatch.length;
  }

  console.log(`  Attachments: ${attachmentInserted} inserted, ${attachmentUpdated} updated, ${attachmentSkipped} skipped`);

  // --- Step 5: Update document counts in Turso ---
  console.log("\nUpdating document counts...");
  await turso.execute(`
    UPDATE committees SET document_count = (
      SELECT COUNT(*) FROM documents WHERE documents.committee_id = committees.id
    )
  `);

  console.log("Done!");
  local.close();
  turso.close();
}

async function insertDocumentBatch(
  turso: Client,
  batch: Row[],
  committeeIdMap: Map<number, number>
) {
  const statements = batch.map((d) => ({
    sql: `INSERT OR IGNORE INTO documents (committee_id, title, url, meeting_date, doc_type, source, source_id, last_confirmed_at, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [
      committeeIdMap.get(d.committee_id as number)!,
      d.title,
      d.url,
      d.meeting_date,
      d.doc_type,
      d.source,
      d.source_id,
      d.last_confirmed_at,
      d.created_at,
      d.updated_at,
    ],
  }));

  await turso.batch(statements, "write");
}

async function insertAttachmentBatch(turso: Client, batch: Row[]) {
  const statements = batch.map((a) => ({
    sql: `INSERT OR IGNORE INTO attachments (document_id, title, url, file_type, file_size, page_count, text_content, is_downloaded, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [
      (a as unknown as Record<string, unknown>)._tursoDocId as number,
      a.title,
      a.url,
      a.file_type,
      a.file_size,
      a.page_count,
      a.text_content ?? null,
      a.is_downloaded,
      a.created_at,
      a.updated_at,
    ],
  }));

  await turso.batch(statements, "write");
}

async function updateAttachmentBatch(turso: Client, batch: Row[]) {
  const statements = batch.map((a) => ({
    sql: `UPDATE attachments SET file_size = ?, page_count = ?, text_content = ?, is_downloaded = ?, updated_at = ? WHERE url = ?`,
    args: [a.file_size, a.page_count, a.text_content ?? null, a.is_downloaded, a.updated_at, a.url],
  }));

  await turso.batch(statements, "write");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
