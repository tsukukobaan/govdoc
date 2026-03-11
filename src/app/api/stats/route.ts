import { turso } from "@/lib/turso";
import { NextResponse } from "next/server";

export const revalidate = 3600; // 1 hour

export async function GET() {
  const [
    docCount,
    docsByType,
    docsBySource,
    attachmentCount,
    attachmentsDownloaded,
    attachmentsWithText,
    committeeCount,
    ministryStats,
    recentDocuments,
  ] = await Promise.all([
    turso.execute("SELECT COUNT(*) as c FROM documents"),
    turso.execute("SELECT doc_type, COUNT(*) as c FROM documents GROUP BY doc_type"),
    turso.execute("SELECT source, COUNT(*) as c FROM documents GROUP BY source"),
    turso.execute("SELECT COUNT(*) as c FROM attachments"),
    turso.execute("SELECT COUNT(*) as c FROM attachments WHERE is_downloaded = 1"),
    turso.execute(
      "SELECT COUNT(*) as c FROM attachments WHERE text_content IS NOT NULL AND length(text_content) > 0"
    ),
    turso.execute("SELECT COUNT(*) as c FROM committees"),
    turso.execute(
      `SELECT m.name, m.slug, COUNT(DISTINCT c.id) as committees, COUNT(d.id) as documents
       FROM ministries m
       LEFT JOIN committees c ON c.ministry_id = m.id
       LEFT JOIN documents d ON d.committee_id = c.id
       GROUP BY m.id ORDER BY documents DESC`
    ),
    turso.execute(
      `SELECT d.title, d.meeting_date, d.doc_type, m.name as ministry_name
       FROM documents d
       JOIN committees c ON d.committee_id = c.id
       JOIN ministries m ON c.ministry_id = m.id
       WHERE d.meeting_date IS NOT NULL
       ORDER BY d.created_at DESC LIMIT 10`
    ),
  ]);

  return NextResponse.json({
    updated_at: new Date().toISOString(),
    documents: {
      total: docCount.rows[0].c,
      by_type: Object.fromEntries(docsByType.rows.map((r) => [r.doc_type, r.c])),
      by_source: Object.fromEntries(docsBySource.rows.map((r) => [r.source, r.c])),
    },
    attachments: {
      total: attachmentCount.rows[0].c,
      downloaded: attachmentsDownloaded.rows[0].c,
      with_text: attachmentsWithText.rows[0].c,
    },
    committees: committeeCount.rows[0].c,
    ministries: ministryStats.rows.map((r) => ({
      name: r.name,
      slug: r.slug,
      committees: r.committees,
      documents: r.documents,
    })),
    recent_documents: recentDocuments.rows.map((r) => ({
      title: r.title,
      meeting_date: r.meeting_date,
      doc_type: r.doc_type,
      ministry: r.ministry_name,
    })),
  });
}
