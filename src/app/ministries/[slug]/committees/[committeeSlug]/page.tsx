import { prisma } from "@/lib/db";
import { notFound } from "next/navigation";
import Link from "next/link";

export const revalidate = 86400;

interface PageProps {
  params: Promise<{ slug: string; committeeSlug: string }>;
}

export default async function CommitteePage({ params }: PageProps) {
  const { slug, committeeSlug } = await params;

  const ministry = await prisma.ministry.findUnique({
    where: { slug },
  });

  if (!ministry) notFound();

  const committee = await prisma.committee.findFirst({
    where: { ministryId: ministry.id, slug: committeeSlug },
  });

  if (!committee) notFound();

  const documents = await prisma.document.findMany({
    where: { committeeId: committee.id },
    orderBy: { meetingDate: "desc" },
    include: { attachments: true },
  });

  // Group documents by meetingDate
  const grouped = new Map<string, typeof documents>();
  for (const doc of documents) {
    const key = doc.meetingDate
      ? new Date(doc.meetingDate).toISOString().split("T")[0]
      : "unknown";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(doc);
  }

  const docTypeLabel: Record<string, string> = {
    minutes: "議事録",
    summary: "議事要旨",
    material: "資料",
  };

  const docTypeOrder: Record<string, number> = {
    minutes: 0,
    summary: 1,
    material: 2,
  };

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="text-sm text-slate-500 mb-4">
        <Link href="/" className="hover:text-blue-600">
          トップ
        </Link>
        <span className="mx-2">/</span>
        <Link
          href={`/ministries/${slug}`}
          className="hover:text-blue-600"
        >
          {ministry.name}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-slate-800">{committee.name}</span>
      </nav>

      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-4 h-4 rounded-full"
          style={{ backgroundColor: ministry.color }}
        />
        <div>
          <h1 className="text-2xl font-bold text-slate-800">
            {committee.name}
          </h1>
          <p className="text-sm text-slate-500">{ministry.name}</p>
        </div>
        {committee.url && (
          <a
            href={committee.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-sm text-blue-600 hover:underline"
          >
            公式ページ
          </a>
        )}
      </div>

      {/* Stats */}
      <div className="flex gap-6 text-sm text-slate-600 mb-8">
        <span>
          <span className="font-semibold text-slate-800">
            {documents.length.toLocaleString()}
          </span>{" "}
          件の文書
        </span>
        <span>
          <span className="font-semibold text-slate-800">
            {grouped.size}
          </span>{" "}
          回の会議
        </span>
      </div>

      {/* Documents grouped by date */}
      <div className="space-y-6">
        {Array.from(grouped.entries()).map(([dateKey, docs]) => (
          <div
            key={dateKey}
            className="bg-white rounded-lg border border-slate-200 overflow-hidden"
          >
            <div className="px-4 py-3 bg-slate-50 border-b border-slate-200">
              <h2 className="font-semibold text-slate-800">
                {dateKey !== "unknown"
                  ? new Date(dateKey + "T00:00:00").toLocaleDateString(
                      "ja-JP",
                      {
                        year: "numeric",
                        month: "long",
                        day: "numeric",
                      }
                    )
                  : "日付不明"}
              </h2>
            </div>
            <div className="divide-y divide-slate-100">
              {docs
                .sort(
                  (a, b) =>
                    (docTypeOrder[a.docType] ?? 9) -
                    (docTypeOrder[b.docType] ?? 9)
                )
                .map((doc) => (
                  <div key={doc.id} className="px-4 py-2.5">
                    <div className="flex items-center gap-3">
                      <span className="text-xs px-2 py-0.5 bg-slate-100 text-slate-600 rounded shrink-0">
                        {docTypeLabel[doc.docType] ?? doc.docType}
                      </span>
                      <a
                        href={doc.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-600 hover:underline truncate"
                      >
                        {doc.title}
                      </a>
                    </div>
                    {doc.attachments.length > 0 && (
                      <div className="ml-16 mt-1.5 space-y-1">
                        {doc.attachments.map((att) => (
                          <a
                            key={att.id}
                            href={att.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 text-xs text-slate-500 hover:text-blue-600 group"
                          >
                            <span className="px-1.5 py-0.5 bg-red-50 text-red-600 rounded text-[10px] font-medium uppercase shrink-0">
                              {att.fileType}
                            </span>
                            <span className="truncate group-hover:underline">
                              {att.title}
                            </span>
                            {att.pageCount && (
                              <span className="text-slate-400 shrink-0">
                                {att.pageCount}p
                              </span>
                            )}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
