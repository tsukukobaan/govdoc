import { prisma } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const query = searchParams.get("q")?.trim();
  const ministry = searchParams.get("ministry");
  const type = searchParams.get("type");
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const limit = 30;

  if (!query) {
    return NextResponse.json({ results: [], total: 0 });
  }

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
    })),
    total,
    page,
    totalPages: Math.ceil(total / limit),
  });
}
