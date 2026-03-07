import { prisma } from "@/lib/db";
import { turso } from "@/lib/turso";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const query = searchParams.get("q")?.trim();
  const ministry = searchParams.get("ministry");
  const type = searchParams.get("type");
  const scope = searchParams.get("scope") || "all"; // title | content | all
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const limit = 30;

  if (!query) {
    return NextResponse.json({ results: [], total: 0 });
  }

  // For "content" or "all" scope, use FTS5
  if (scope === "content" || scope === "all") {
    return handleFtsSearch(query, ministry, type, scope, page, limit);
  }

  // For "title" scope, use existing Prisma LIKE search
  return handleTitleSearch(query, ministry, type, page, limit);
}

async function handleTitleSearch(
  query: string,
  ministry: string | null,
  type: string | null,
  page: number,
  limit: number
) {
  const whereClause: Record<string, unknown> = {
    title: { contains: query },
  };

  if (ministry) {
    whereClause.committee = { ministry: { slug: ministry } };
  }
  if (type) {
    whereClause.docType = type;
  }

  const [results, total] = await Promise.all([
    prisma.document.findMany({
      where: whereClause,
      include: {
        committee: {
          include: { ministry: true },
        },
      },
      orderBy: { meetingDate: "desc" },
      skip: (page - 1) * limit,
      take: limit,
    }),
    prisma.document.count({ where: whereClause }),
  ]);

  return NextResponse.json({
    results: results.map((d) => ({
      id: d.id,
      title: d.title,
      url: d.url,
      meetingDate: d.meetingDate,
      docType: d.docType,
      committeeName: d.committee.name,
      ministryName: d.committee.ministry.name,
      ministrySlug: d.committee.ministry.slug,
      ministryColor: d.committee.ministry.color,
      source: "title" as const,
    })),
    total,
    page,
    totalPages: Math.ceil(total / limit),
  });
}

async function handleFtsSearch(
  query: string,
  ministry: string | null,
  type: string | null,
  scope: string,
  page: number,
  limit: number
) {
  // Build FTS match expression - escape double quotes in query
  const ftsQuery = query.replace(/"/g, '""');

  // Build WHERE conditions for filtering
  const conditions: string[] = [];
  const args: (string | number)[] = [];

  // FTS MATCH condition
  conditions.push("search_index MATCH ?");
  args.push(ftsQuery);

  if (ministry) {
    conditions.push("m.slug = ?");
    args.push(ministry);
  }
  if (type) {
    conditions.push("d.doc_type = ?");
    args.push(type);
  }

  const whereSQL = conditions.join(" AND ");

  // Count query
  const countResult = await turso.execute({
    sql: `
      SELECT COUNT(*) as cnt
      FROM search_index si
      JOIN attachments a ON a.id = si.rowid
      JOIN documents d ON a.document_id = d.id
      JOIN committees c ON d.committee_id = c.id
      JOIN ministries m ON c.ministry_id = m.id
      WHERE ${whereSQL}
    `,
    args,
  });
  const total = countResult.rows[0].cnt as number;

  // Search query with snippet
  const offset = (page - 1) * limit;
  const searchResult = await turso.execute({
    sql: `
      SELECT a.id, a.title, a.document_id, a.page_count, a.file_size, a.url as attachment_url,
             snippet(search_index, 1, '<mark>', '</mark>', '...', 32) as snippet,
             d.title as doc_title, d.meeting_date, d.url as doc_url, d.doc_type,
             c.name as committee_name,
             m.name as ministry_name, m.slug as ministry_slug, m.color as ministry_color
      FROM search_index si
      JOIN attachments a ON a.id = si.rowid
      JOIN documents d ON a.document_id = d.id
      JOIN committees c ON d.committee_id = c.id
      JOIN ministries m ON c.ministry_id = m.id
      WHERE ${whereSQL}
      ORDER BY rank
      LIMIT ? OFFSET ?
    `,
    args: [...args, limit, offset],
  });

  const ftsResults = searchResult.rows.map((row) => ({
    id: row.id as number,
    attachmentTitle: row.title as string,
    attachmentUrl: row.attachment_url as string,
    pageCount: row.page_count as number | null,
    fileSize: row.file_size as number | null,
    snippet: row.snippet as string,
    title: row.doc_title as string,
    url: row.doc_url as string,
    meetingDate: row.meeting_date as string | null,
    docType: row.doc_type as string,
    committeeName: row.committee_name as string,
    ministryName: row.ministry_name as string,
    ministrySlug: row.ministry_slug as string,
    ministryColor: row.ministry_color as string,
    source: "content" as const,
  }));

  // For "all" scope, also search titles via Prisma and merge
  if (scope === "all") {
    const titleWhere: Record<string, unknown> = {
      title: { contains: query },
    };
    if (ministry) {
      titleWhere.committee = { ministry: { slug: ministry } };
    }
    if (type) {
      titleWhere.docType = type;
    }

    const [titleResults, titleTotal] = await Promise.all([
      prisma.document.findMany({
        where: titleWhere,
        include: {
          committee: { include: { ministry: true } },
        },
        orderBy: { meetingDate: "desc" },
        take: 5, // Show top 5 title matches in "all" mode
      }),
      prisma.document.count({ where: titleWhere }),
    ]);

    return NextResponse.json({
      results: ftsResults,
      titleResults: titleResults.map((d) => ({
        id: d.id,
        title: d.title,
        url: d.url,
        meetingDate: d.meetingDate,
        docType: d.docType,
        committeeName: d.committee.name,
        ministryName: d.committee.ministry.name,
        ministrySlug: d.committee.ministry.slug,
        ministryColor: d.committee.ministry.color,
        source: "title" as const,
      })),
      titleTotal,
      total,
      page,
      totalPages: Math.ceil(total / limit),
    });
  }

  return NextResponse.json({
    results: ftsResults,
    total,
    page,
    totalPages: Math.ceil(total / limit),
  });
}
