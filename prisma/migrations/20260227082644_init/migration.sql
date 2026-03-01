-- CreateTable
CREATE TABLE "ministries" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "name_en" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "council_url" TEXT,
    "color" TEXT NOT NULL DEFAULT '#1a1a2e',
    "sort_order" INTEGER NOT NULL DEFAULT 0,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "committees" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "ministry_id" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "category" TEXT NOT NULL DEFAULT 'advisory_council',
    "url" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "document_count" INTEGER NOT NULL DEFAULT 0,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL,
    CONSTRAINT "committees_ministry_id_fkey" FOREIGN KEY ("ministry_id") REFERENCES "ministries" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "documents" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "committee_id" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "meeting_date" DATETIME,
    "doc_type" TEXT NOT NULL DEFAULT 'minutes',
    "source" TEXT NOT NULL DEFAULT 'nistep',
    "source_id" TEXT,
    "last_confirmed_at" DATETIME,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" DATETIME NOT NULL,
    CONSTRAINT "documents_committee_id_fkey" FOREIGN KEY ("committee_id") REFERENCES "committees" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "ministries_slug_key" ON "ministries"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "committees_ministry_id_slug_key" ON "committees"("ministry_id", "slug");

-- CreateIndex
CREATE INDEX "documents_committee_id_idx" ON "documents"("committee_id");

-- CreateIndex
CREATE INDEX "documents_meeting_date_idx" ON "documents"("meeting_date");

-- CreateIndex
CREATE INDEX "documents_source_idx" ON "documents"("source");
