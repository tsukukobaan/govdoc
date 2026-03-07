import { prisma } from "@/lib/db";
import { notFound } from "next/navigation";
import Link from "next/link";

export const revalidate = 86400;

const PAGE_SIZE = 50;

interface PageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ page?: string; year?: string; type?: string }>;
}

export default async function MinistryPage({ params, searchParams }: PageProps) {
  const { slug } = await params;
  const { page: pageStr, year, type } = await searchParams;

  const ministry = await prisma.ministry.findUnique({
    where: { slug },
  });

  if (!ministry) notFound();

  const currentPage = Math.max(1, parseInt(pageStr || "1", 10));

  // Build filter conditions
  const whereClause: Record<string, unknown> = {
    committee: { ministryId: ministry.id },
  };
  if (year) {
    const yearNum = parseInt(year, 10);
    whereClause.meetingDate = {
      gte: new Date(`${yearNum}-01-01`),
      lt: new Date(`${yearNum + 1}-01-01`),
    };
  }
  if (type) {
    whereClause.docType = type;
  }

  // Run independent queries in parallel
  const [committees, totalDocs, documents, years] = await Promise.all([
    prisma.committee.findMany({
      where: {
        ministryId: ministry.id,
        documentCount: { gt: 0 },
      },
      orderBy: { documentCount: "desc" },
    }),
    prisma.document.count({ where: whereClause }),
    prisma.document.findMany({
      where: whereClause,
      include: {
        committee: true,
      },
      orderBy: { meetingDate: "desc" },
      skip: (currentPage - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.$queryRawUnsafe<{ year: number }[]>(
      `SELECT DISTINCT CAST(strftime('%Y', meeting_date) AS INTEGER) as year
       FROM documents d
       JOIN committees c ON d.committee_id = c.id
       WHERE c.ministry_id = ? AND d.meeting_date IS NOT NULL
       ORDER BY year DESC`,
      ministry.id
    ),
  ]);

  const totalPages = Math.ceil(totalDocs / PAGE_SIZE);

  const docTypes = [
    { value: "minutes", label: "議事録" },
    { value: "summary", label: "議事要旨" },
    { value: "material", label: "資料" },
  ];

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="text-sm text-slate-500 mb-4">
        <Link href="/" className="hover:text-blue-600">
          トップ
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">{ministry.name}</span>
      </nav>

      {/* Ministry header */}
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-4 h-4 rounded-full"
          style={{ backgroundColor: ministry.color }}
        />
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{ministry.name}</h1>
          <p className="text-sm text-slate-500">{ministry.nameEn}</p>
        </div>
        {ministry.councilUrl && (
          <a
            href={ministry.councilUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-sm text-blue-600 hover:underline"
          >
            公式サイト
          </a>
        )}
      </div>

      {/* Stats */}
      <div className="flex gap-6 text-sm text-slate-600 mb-6">
        <span>
          <span className="font-semibold text-slate-800">
            {totalDocs.toLocaleString()}
          </span>{" "}
          件の文書
        </span>
        <span>
          <span className="font-semibold text-slate-800">
            {committees.length}
          </span>{" "}
          審議会・委員会
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <FilterSelect
          label="年度"
          paramName="year"
          currentValue={year}
          options={years.map((y) => ({
            value: String(y.year),
            label: `${y.year}年`,
          }))}
          slug={slug}
          type={type}
        />
        <FilterSelect
          label="種別"
          paramName="type"
          currentValue={type}
          options={docTypes}
          slug={slug}
          year={year}
        />
      </div>

      {/* Document list */}
      <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
        {documents.length === 0 ? (
          <div className="px-4 py-8 text-center text-slate-500">
            該当する文書がありません
          </div>
        ) : (
          documents.map((doc) => (
            <div key={doc.id} className="px-4 py-3 flex items-center gap-4">
              <span className="text-sm text-slate-400 shrink-0 w-24">
                {doc.meetingDate
                  ? new Date(doc.meetingDate).toLocaleDateString("ja-JP")
                  : "日付不明"}
              </span>
              <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded shrink-0">
                {doc.docType === "minutes"
                  ? "議事録"
                  : doc.docType === "summary"
                    ? "議事要旨"
                    : doc.docType === "material"
                      ? "資料"
                      : doc.docType}
              </span>
              <Link
                href={`/ministries/${slug}/committees/${doc.committee.slug}`}
                className="text-sm text-slate-500 hover:text-blue-600 shrink-0 hidden lg:inline max-w-48 truncate"
              >
                {doc.committee.name}
              </Link>
              <a
                href={doc.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 hover:underline truncate"
              >
                {doc.title}
              </a>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-6">
          {currentPage > 1 && (
            <PaginationLink
              page={currentPage - 1}
              slug={slug}
              year={year}
              type={type}
              label="前へ"
            />
          )}
          {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => {
            const pageNum = getPageNumber(i, currentPage, totalPages);
            return (
              <PaginationLink
                key={pageNum}
                page={pageNum}
                slug={slug}
                year={year}
                type={type}
                label={String(pageNum)}
                active={pageNum === currentPage}
              />
            );
          })}
          {currentPage < totalPages && (
            <PaginationLink
              page={currentPage + 1}
              slug={slug}
              year={year}
              type={type}
              label="次へ"
            />
          )}
        </div>
      )}

      {/* Committee list */}
      <h2 className="text-lg font-bold text-slate-800 mt-10 mb-4">
        審議会・委員会一覧
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {committees.map((c) => (
          <Link
            key={c.id}
            href={`/ministries/${slug}/committees/${c.slug}`}
            className="bg-white rounded border border-slate-200 px-4 py-2 flex items-center justify-between text-sm hover:bg-slate-50 hover:border-slate-300 transition-colors"
          >
            <span className="text-slate-700 truncate">{c.name}</span>
            <span className="text-slate-400 shrink-0 ml-2">
              {c.documentCount}件
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function getPageNumber(index: number, current: number, total: number): number {
  if (total <= 10) return index + 1;
  const start = Math.max(1, Math.min(current - 4, total - 9));
  return start + index;
}

function FilterSelect({
  label,
  paramName,
  currentValue,
  options,
  slug,
  year,
  type,
}: {
  label: string;
  paramName: string;
  currentValue?: string;
  options: { value: string; label: string }[];
  slug: string;
  year?: string;
  type?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-slate-500">{label}:</span>
      <div className="flex flex-wrap gap-1">
        <Link
          href={buildUrl(slug, paramName === "year" ? undefined : year, paramName === "type" ? undefined : type)}
          className={`text-xs px-2 py-1 rounded ${
            !currentValue
              ? "bg-blue-100 text-blue-700"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          全て
        </Link>
        {options.slice(0, 20).map((opt) => (
          <Link
            key={opt.value}
            href={buildUrl(
              slug,
              paramName === "year" ? opt.value : year,
              paramName === "type" ? opt.value : type
            )}
            className={`text-xs px-2 py-1 rounded ${
              currentValue === opt.value
                ? "bg-blue-100 text-blue-700"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {opt.label}
          </Link>
        ))}
      </div>
    </div>
  );
}

function buildUrl(slug: string, year?: string, type?: string): string {
  const params = new URLSearchParams();
  if (year) params.set("year", year);
  if (type) params.set("type", type);
  const qs = params.toString();
  return `/ministries/${slug}${qs ? `?${qs}` : ""}`;
}

function PaginationLink({
  page,
  slug,
  year,
  type,
  label,
  active,
}: {
  page: number;
  slug: string;
  year?: string;
  type?: string;
  label: string;
  active?: boolean;
}) {
  const params = new URLSearchParams();
  params.set("page", String(page));
  if (year) params.set("year", year);
  if (type) params.set("type", type);

  return (
    <Link
      href={`/ministries/${slug}?${params.toString()}`}
      className={`px-3 py-1 text-sm rounded ${
        active
          ? "bg-blue-600 text-white"
          : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
      }`}
    >
      {label}
    </Link>
  );
}
