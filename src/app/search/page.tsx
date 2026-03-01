import { prisma } from "@/lib/db";
import Link from "next/link";

interface PageProps {
  searchParams: Promise<{ q?: string; page?: string; ministry?: string; type?: string }>;
}

const PAGE_SIZE = 30;

export default async function SearchPage({ searchParams }: PageProps) {
  const { q, page: pageStr, ministry, type } = await searchParams;
  const query = q?.trim() || "";
  const currentPage = Math.max(1, parseInt(pageStr || "1", 10));

  if (!query) {
    return (
      <div>
        <h1 className="text-xl font-bold text-slate-800 mb-4">検索</h1>
        <p className="text-slate-500">検索キーワードを入力してください。</p>
      </div>
    );
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

  const [results, total, ministries] = await Promise.all([
    prisma.document.findMany({
      where: whereClause,
      include: {
        committee: {
          include: { ministry: true },
        },
      },
      orderBy: { meetingDate: "desc" },
      skip: (currentPage - 1) * PAGE_SIZE,
      take: PAGE_SIZE,
    }),
    prisma.document.count({ where: whereClause }),
    prisma.ministry.findMany({
      where: {
        committees: {
          some: {
            documents: {
              some: { title: { contains: query } },
            },
          },
        },
      },
      orderBy: { sortOrder: "asc" },
    }),
  ]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const docTypes = [
    { value: "minutes", label: "議事録" },
    { value: "summary", label: "議事要旨" },
    { value: "material", label: "資料" },
  ];

  return (
    <div>
      <h1 className="text-xl font-bold text-slate-800 mb-2">
        &ldquo;{query}&rdquo; の検索結果
      </h1>
      <p className="text-sm text-slate-500 mb-6">
        {total.toLocaleString()} 件見つかりました
      </p>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Ministry filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">省庁:</span>
          <div className="flex flex-wrap gap-1">
            <Link
              href={buildSearchUrl(query, undefined, type)}
              className={`text-xs px-2 py-1 rounded ${
                !ministry
                  ? "bg-blue-100 text-blue-700"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              全て
            </Link>
            {ministries.map((m) => (
              <Link
                key={m.slug}
                href={buildSearchUrl(query, m.slug, type)}
                className={`text-xs px-2 py-1 rounded ${
                  ministry === m.slug
                    ? "bg-blue-100 text-blue-700"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {m.name}
              </Link>
            ))}
          </div>
        </div>

        {/* Type filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">種別:</span>
          <div className="flex flex-wrap gap-1">
            <Link
              href={buildSearchUrl(query, ministry, undefined)}
              className={`text-xs px-2 py-1 rounded ${
                !type
                  ? "bg-blue-100 text-blue-700"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              全て
            </Link>
            {docTypes.map((dt) => (
              <Link
                key={dt.value}
                href={buildSearchUrl(query, ministry, dt.value)}
                className={`text-xs px-2 py-1 rounded ${
                  type === dt.value
                    ? "bg-blue-100 text-blue-700"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {dt.label}
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
        {results.length === 0 ? (
          <div className="px-4 py-8 text-center text-slate-500">
            該当する文書がありません
          </div>
        ) : (
          results.map((doc) => (
            <div key={doc.id} className="px-4 py-3">
              <div className="flex items-center gap-3 mb-1">
                <Link
                  href={`/ministries/${doc.committee.ministry.slug}`}
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{
                    backgroundColor: doc.committee.ministry.color + "15",
                    color: doc.committee.ministry.color,
                  }}
                >
                  {doc.committee.ministry.name}
                </Link>
                <span className="text-xs text-slate-400">
                  {doc.committee.name}
                </span>
              </div>
              <a
                href={doc.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 hover:underline"
              >
                {doc.title}
              </a>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-xs text-slate-400">
                  {doc.meetingDate
                    ? new Date(doc.meetingDate).toLocaleDateString("ja-JP")
                    : "日付不明"}
                </span>
                <span className="text-xs px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded">
                  {doc.docType === "minutes"
                    ? "議事録"
                    : doc.docType === "summary"
                      ? "議事要旨"
                      : doc.docType === "material"
                        ? "資料"
                        : doc.docType}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-6">
          {currentPage > 1 && (
            <SearchPaginationLink
              query={query}
              ministry={ministry}
              type={type}
              page={currentPage - 1}
              label="前へ"
            />
          )}
          {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => {
            const pageNum =
              totalPages <= 10
                ? i + 1
                : Math.max(1, Math.min(currentPage - 4, totalPages - 9)) + i;
            return (
              <SearchPaginationLink
                key={pageNum}
                query={query}
                ministry={ministry}
                type={type}
                page={pageNum}
                label={String(pageNum)}
                active={pageNum === currentPage}
              />
            );
          })}
          {currentPage < totalPages && (
            <SearchPaginationLink
              query={query}
              ministry={ministry}
              type={type}
              page={currentPage + 1}
              label="次へ"
            />
          )}
        </div>
      )}
    </div>
  );
}

function buildSearchUrl(q: string, ministry?: string, type?: string): string {
  const params = new URLSearchParams();
  params.set("q", q);
  if (ministry) params.set("ministry", ministry);
  if (type) params.set("type", type);
  return `/search?${params.toString()}`;
}

function SearchPaginationLink({
  query,
  ministry,
  type,
  page,
  label,
  active,
}: {
  query: string;
  ministry?: string;
  type?: string;
  page: number;
  label: string;
  active?: boolean;
}) {
  const params = new URLSearchParams();
  params.set("q", query);
  if (ministry) params.set("ministry", ministry);
  if (type) params.set("type", type);
  params.set("page", String(page));

  return (
    <Link
      href={`/search?${params.toString()}`}
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
