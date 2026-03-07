import { prisma } from "@/lib/db";
import { turso } from "@/lib/turso";
import Link from "next/link";

export const revalidate = 86400;

interface PageProps {
  searchParams: Promise<{ q?: string; page?: string; ministry?: string; type?: string; scope?: string }>;
}

const PAGE_SIZE = 30;

type FtsResult = {
  id: number;
  attachmentTitle: string;
  attachmentUrl: string;
  pageCount: number | null;
  fileSize: number | null;
  snippet: string;
  title: string;
  url: string;
  meetingDate: string | null;
  docType: string;
  committeeName: string;
  ministryName: string;
  ministrySlug: string;
  ministryColor: string;
};

export default async function SearchPage({ searchParams }: PageProps) {
  const { q, page: pageStr, ministry, type, scope: scopeParam } = await searchParams;
  const query = q?.trim() || "";
  const currentPage = Math.max(1, parseInt(pageStr || "1", 10));
  const scope = scopeParam || "all";

  if (!query) {
    return (
      <div>
        <h1 className="text-xl font-bold text-slate-800 mb-4">検索</h1>
        <p className="text-slate-500">検索キーワードを入力してください。</p>
      </div>
    );
  }

  // Title search (for "title" and "all" scopes)
  let titleResults: Awaited<ReturnType<typeof prisma.document.findMany<{
    include: { committee: { include: { ministry: true } } };
  }>>> = [];
  let titleTotal = 0;
  let titleTotalPages = 0;

  if (scope === "title" || scope === "all") {
    const titleWhere: Record<string, unknown> = {
      title: { contains: query },
    };
    if (ministry) {
      titleWhere.committee = { ministry: { slug: ministry } };
    }
    if (type) {
      titleWhere.docType = type;
    }

    const titleSkip = scope === "title" ? (currentPage - 1) * PAGE_SIZE : 0;
    const titleTake = scope === "title" ? PAGE_SIZE : 5;

    [titleResults, titleTotal] = await Promise.all([
      prisma.document.findMany({
        where: titleWhere,
        include: {
          committee: {
            include: { ministry: true },
          },
        },
        orderBy: { meetingDate: "desc" },
        skip: titleSkip,
        take: titleTake,
      }),
      prisma.document.count({ where: titleWhere }),
    ]);
    titleTotalPages = Math.ceil(titleTotal / PAGE_SIZE);
  }

  // FTS search (for "content" and "all" scopes)
  let ftsResults: FtsResult[] = [];
  let ftsTotal = 0;
  let ftsTotalPages = 0;

  if (scope === "content" || scope === "all") {
    const ftsQuery = query.replace(/"/g, '""');
    const conditions: string[] = ["search_index MATCH ?"];
    const args: (string | number)[] = [ftsQuery];

    if (ministry) {
      conditions.push("m.slug = ?");
      args.push(ministry);
    }
    if (type) {
      conditions.push("d.doc_type = ?");
      args.push(type);
    }

    const whereSQL = conditions.join(" AND ");

    const [countResult, searchResult] = await Promise.all([
      turso.execute({
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
      }),
      turso.execute({
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
        args: [...args, PAGE_SIZE, (currentPage - 1) * PAGE_SIZE],
      }),
    ]);

    ftsTotal = countResult.rows[0].cnt as number;
    ftsTotalPages = Math.ceil(ftsTotal / PAGE_SIZE);

    ftsResults = searchResult.rows.map((row) => ({
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
    }));
  }

  // Ministries for filter (use Prisma)
  const ministries = await prisma.ministry.findMany({
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
  });

  // Determine totals for display based on scope
  const displayTotal = scope === "title" ? titleTotal : ftsTotal;
  const displayTotalPages = scope === "title" ? titleTotalPages : ftsTotalPages;

  const docTypes = [
    { value: "minutes", label: "議事録" },
    { value: "summary", label: "議事要旨" },
    { value: "material", label: "資料" },
  ];

  const scopes = [
    { value: "all", label: "すべて" },
    { value: "title", label: "タイトル" },
    { value: "content", label: "PDF全文" },
  ];

  return (
    <div>
      <h1 className="text-xl font-bold text-slate-800 mb-2">
        &ldquo;{query}&rdquo; の検索結果
      </h1>
      <p className="text-sm text-slate-500 mb-6">
        {scope === "all"
          ? `タイトル ${titleTotal.toLocaleString()} 件 / PDF全文 ${ftsTotal.toLocaleString()} 件`
          : `${displayTotal.toLocaleString()} 件見つかりました`}
      </p>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Scope filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">検索対象:</span>
          <div className="flex flex-wrap gap-1">
            {scopes.map((s) => (
              <Link
                key={s.value}
                href={buildSearchUrl(query, ministry, type, s.value)}
                className={`text-xs px-2 py-1 rounded ${
                  scope === s.value
                    ? "bg-blue-100 text-blue-700"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {s.label}
              </Link>
            ))}
          </div>
        </div>

        {/* Ministry filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">省庁:</span>
          <div className="flex flex-wrap gap-1">
            <Link
              href={buildSearchUrl(query, undefined, type, scope)}
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
                href={buildSearchUrl(query, m.slug, type, scope)}
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
              href={buildSearchUrl(query, ministry, undefined, scope)}
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
                href={buildSearchUrl(query, ministry, dt.value, scope)}
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

      {/* Title match results (shown in "all" scope as a separate section) */}
      {scope === "all" && titleResults.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-700">
              タイトルに一致（{titleTotal.toLocaleString()} 件）
            </h2>
            {titleTotal > 5 && (
              <Link
                href={buildSearchUrl(query, ministry, type, "title")}
                className="text-xs text-blue-600 hover:underline"
              >
                すべて表示
              </Link>
            )}
          </div>
          <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
            {titleResults.map((doc) => (
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
                  <DocTypeBadge docType={doc.docType} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Title-only results (shown in "title" scope) */}
      {scope === "title" && (
        <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
          {titleResults.length === 0 ? (
            <div className="px-4 py-8 text-center text-slate-500">
              該当する文書がありません
            </div>
          ) : (
            titleResults.map((doc) => (
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
                  <DocTypeBadge docType={doc.docType} />
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* FTS results (shown in "content" and "all" scopes) */}
      {(scope === "content" || scope === "all") && (
        <div>
          {scope === "all" && (
            <h2 className="text-sm font-semibold text-slate-700 mb-3">
              PDF全文に一致（{ftsTotal.toLocaleString()} 件）
            </h2>
          )}
          <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
            {ftsResults.length === 0 ? (
              <div className="px-4 py-8 text-center text-slate-500">
                該当する文書がありません
              </div>
            ) : (
              ftsResults.map((result) => (
                <div key={`fts-${result.id}`} className="px-4 py-3">
                  <div className="flex items-center gap-3 mb-1">
                    <Link
                      href={`/ministries/${result.ministrySlug}`}
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: result.ministryColor + "15",
                        color: result.ministryColor,
                      }}
                    >
                      {result.ministryName}
                    </Link>
                    <span className="text-xs text-slate-400">
                      {result.committeeName}
                    </span>
                  </div>
                  <a
                    href={result.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:underline"
                  >
                    {result.title}
                  </a>
                  {/* Attachment info */}
                  <div className="flex items-center gap-2 mt-1">
                    <svg className="w-3.5 h-3.5 text-red-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M4 18h12a2 2 0 002-2V8l-6-6H4a2 2 0 00-2 2v12a2 2 0 002 2zm8-14l4 4h-4V4zM6 12h8v1H6v-1zm0 2h8v1H6v-1zm0-4h3v1H6V10z" />
                    </svg>
                    <a
                      href={result.attachmentUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-slate-600 hover:text-blue-600 hover:underline truncate"
                    >
                      {result.attachmentTitle}
                    </a>
                    {result.pageCount && (
                      <span className="text-xs text-slate-400 shrink-0">{result.pageCount}ページ</span>
                    )}
                    {result.fileSize && (
                      <span className="text-xs text-slate-400 shrink-0">{formatFileSize(result.fileSize)}</span>
                    )}
                  </div>
                  {/* Snippet */}
                  {result.snippet && (
                    <div
                      className="mt-2 text-xs text-slate-600 bg-slate-50 rounded px-3 py-2 leading-relaxed [&_mark]:bg-yellow-200 [&_mark]:text-slate-900 [&_mark]:px-0.5 [&_mark]:rounded-sm"
                      dangerouslySetInnerHTML={{ __html: result.snippet }}
                    />
                  )}
                  <div className="flex items-center gap-3 mt-1.5">
                    <span className="text-xs text-slate-400">
                      {result.meetingDate
                        ? new Date(result.meetingDate).toLocaleDateString("ja-JP")
                        : "日付不明"}
                    </span>
                    <DocTypeBadge docType={result.docType} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Pagination (for title and content scopes; all scope paginates FTS results) */}
      {displayTotalPages > 1 && scope !== "all" && (
        <div className="flex justify-center gap-2 mt-6">
          {currentPage > 1 && (
            <SearchPaginationLink
              query={query}
              ministry={ministry}
              type={type}
              scope={scope}
              page={currentPage - 1}
              label="前へ"
            />
          )}
          {Array.from({ length: Math.min(displayTotalPages, 10) }, (_, i) => {
            const pageNum =
              displayTotalPages <= 10
                ? i + 1
                : Math.max(1, Math.min(currentPage - 4, displayTotalPages - 9)) + i;
            return (
              <SearchPaginationLink
                key={pageNum}
                query={query}
                ministry={ministry}
                type={type}
                scope={scope}
                page={pageNum}
                label={String(pageNum)}
                active={pageNum === currentPage}
              />
            );
          })}
          {currentPage < displayTotalPages && (
            <SearchPaginationLink
              query={query}
              ministry={ministry}
              type={type}
              scope={scope}
              page={currentPage + 1}
              label="次へ"
            />
          )}
        </div>
      )}
      {ftsTotalPages > 1 && scope === "all" && (
        <div className="flex justify-center gap-2 mt-6">
          {currentPage > 1 && (
            <SearchPaginationLink
              query={query}
              ministry={ministry}
              type={type}
              scope={scope}
              page={currentPage - 1}
              label="前へ"
            />
          )}
          {Array.from({ length: Math.min(ftsTotalPages, 10) }, (_, i) => {
            const pageNum =
              ftsTotalPages <= 10
                ? i + 1
                : Math.max(1, Math.min(currentPage - 4, ftsTotalPages - 9)) + i;
            return (
              <SearchPaginationLink
                key={pageNum}
                query={query}
                ministry={ministry}
                type={type}
                scope={scope}
                page={pageNum}
                label={String(pageNum)}
                active={pageNum === currentPage}
              />
            );
          })}
          {currentPage < ftsTotalPages && (
            <SearchPaginationLink
              query={query}
              ministry={ministry}
              type={type}
              scope={scope}
              page={currentPage + 1}
              label="次へ"
            />
          )}
        </div>
      )}
    </div>
  );
}

function buildSearchUrl(q: string, ministry?: string, type?: string, scope?: string): string {
  const params = new URLSearchParams();
  params.set("q", q);
  if (ministry) params.set("ministry", ministry);
  if (type) params.set("type", type);
  if (scope && scope !== "all") params.set("scope", scope);
  return `/search?${params.toString()}`;
}

function DocTypeBadge({ docType }: { docType: string }) {
  const label =
    docType === "minutes"
      ? "議事録"
      : docType === "summary"
        ? "議事要旨"
        : docType === "material"
          ? "資料"
          : docType;
  return (
    <span className="text-xs px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded">
      {label}
    </span>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function SearchPaginationLink({
  query,
  ministry,
  type,
  scope,
  page,
  label,
  active,
}: {
  query: string;
  ministry?: string;
  type?: string;
  scope?: string;
  page: number;
  label: string;
  active?: boolean;
}) {
  const params = new URLSearchParams();
  params.set("q", query);
  if (ministry) params.set("ministry", ministry);
  if (type) params.set("type", type);
  if (scope && scope !== "all") params.set("scope", scope);
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
