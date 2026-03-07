-- CreateTable
CREATE TABLE "attachments" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "document_id" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "file_type" TEXT NOT NULL DEFAULT 'pdf',
    "file_size" INTEGER,
    "page_count" INTEGER,
    "local_path" TEXT,
    "text_content" TEXT,
    "is_downloaded" BOOLEAN NOT NULL DEFAULT false,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL,
    CONSTRAINT "attachments_document_id_fkey" FOREIGN KEY ("document_id") REFERENCES "documents" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_documents" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "committee_id" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "meeting_date" DATETIME,
    "doc_type" TEXT NOT NULL DEFAULT 'minutes',
    "source" TEXT NOT NULL DEFAULT 'nistep',
    "source_id" TEXT,
    "last_confirmed_at" DATETIME,
    "is_index_page" BOOLEAN NOT NULL DEFAULT false,
    "index_crawled_at" DATETIME,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL,
    CONSTRAINT "documents_committee_id_fkey" FOREIGN KEY ("committee_id") REFERENCES "committees" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);
INSERT INTO "new_documents" ("committee_id", "created_at", "doc_type", "id", "last_confirmed_at", "meeting_date", "source", "source_id", "title", "updated_at", "url") SELECT "committee_id", "created_at", "doc_type", "id", "last_confirmed_at", "meeting_date", "source", "source_id", "title", "updated_at", "url" FROM "documents";
DROP TABLE "documents";
ALTER TABLE "new_documents" RENAME TO "documents";
CREATE INDEX "documents_committee_id_idx" ON "documents"("committee_id");
CREATE INDEX "documents_meeting_date_idx" ON "documents"("meeting_date");
CREATE INDEX "documents_source_idx" ON "documents"("source");
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;

-- CreateIndex
CREATE INDEX "attachments_document_id_idx" ON "attachments"("document_id");

-- CreateIndex
CREATE INDEX "attachments_url_idx" ON "attachments"("url");
