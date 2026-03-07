import { prisma } from "@/lib/db";
import { MinistryCard } from "@/components/ministry/MinistryCard";
import Link from "next/link";
import { unstable_cache } from "next/cache";

export const dynamic = "force-dynamic";

const getCachedData = unstable_cache(
  async () => {
    const [ministries, totalDocs, totalCommittees, recentDocs] = await Promise.all([
      prisma.ministry.findMany({
        where: {
          committees: {
            some: {
              documentCount: { gt: 0 },
            },
          },
        },
        include: {
          _count: {
            select: { committees: true },
          },
        },
        orderBy: { sortOrder: "asc" },
      }),
      prisma.document.count(),
      prisma.committee.count({
        where: { documentCount: { gt: 0 } },
      }),
      prisma.document.findMany({
        take: 10,
        orderBy: { meetingDate: "desc" },
        where: { meetingDate: { not: null } },
        include: {
          committee: {
            include: { ministry: true },
          },
        },
      }),
    ]);

    const ministriesWithCounts = await Promise.all(
      ministries.map(async (m) => {
        const docCount = await prisma.document.count({
          where: { committee: { ministryId: m.id } },
        });
        return { ...m, documentCount: docCount };
      })
    );

    return { ministriesWithCounts, totalDocs, totalCommittees, recentDocs };
  },
  ["home-page-data"],
  { revalidate: 86400 }
);

export default async function Home() {
  const { ministriesWithCounts, totalDocs, totalCommittees, recentDocs } =
    await getCachedData();

  const latestDate = recentDocs[0]?.meetingDate
    ? new Date(recentDocs[0].meetingDate).toLocaleDateString("ja-JP")
    : "-";

  return (
    <div>
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <StatCard label="総文書数" value={totalDocs.toLocaleString()} />
        <StatCard
          label="省庁・機関"
          value={ministriesWithCounts.length.toString()}
        />
        <StatCard
          label="審議会・委員会"
          value={totalCommittees.toLocaleString()}
        />
        <StatCard label="最終更新" value={latestDate} />
      </div>

      {/* Ministry grid */}
      <h2 className="text-xl font-bold text-slate-800 mb-4">
        省庁・機関別インデックス
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-10">
        {ministriesWithCounts.map((m) => (
          <MinistryCard
            key={m.id}
            slug={m.slug}
            name={m.name}
            nameEn={m.nameEn}
            color={m.color}
            documentCount={m.documentCount}
            committeeCount={m._count.committees}
          />
        ))}
      </div>

      {/* Recent documents */}
      <h2 className="text-xl font-bold text-slate-800 mb-4">
        最近の議事録・資料
      </h2>
      <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
        {recentDocs.map((doc) => (
          <div key={doc.id} className="px-4 py-3 flex items-center gap-4">
            <span className="text-sm text-slate-400 shrink-0 w-24">
              {doc.meetingDate
                ? new Date(doc.meetingDate).toLocaleDateString("ja-JP")
                : ""}
            </span>
            <Link
              href={`/ministries/${doc.committee.ministry.slug}`}
              className="text-xs px-2 py-0.5 rounded-full shrink-0"
              style={{
                backgroundColor: doc.committee.ministry.color + "15",
                color: doc.committee.ministry.color,
              }}
            >
              {doc.committee.ministry.name}
            </Link>
            <Link
              href={`/ministries/${doc.committee.ministry.slug}/committees/${doc.committee.slug}`}
              className="text-sm text-slate-500 hover:text-blue-600 shrink-0 hidden md:inline"
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
        ))}
      </div>

      {/* External Links */}
      <h2 className="text-xl font-bold text-slate-800 mt-10 mb-4">
        関連リンク
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <ExternalLink
          title="国会会議録検索システム"
          description="国立国会図書館が提供する国会議事録の全文検索"
          url="https://kokkai.ndl.go.jp/"
        />
        <ExternalLink
          title="e-Gov 法令検索"
          description="日本の法令の検索・閲覧"
          url="https://laws.e-gov.go.jp/"
        />
        <ExternalLink
          title="e-Gov パブリックコメント"
          description="意見募集中の案件一覧"
          url="https://public-comment.e-gov.go.jp/pcm/list"
        />
        <ExternalLink
          title="白書等一覧"
          description="各省庁が発行する白書・年次報告書"
          url="https://www.e-gov.go.jp/about-government/white-papers.html"
        />
        <ExternalLink
          title="e-Gov データポータル"
          description="政府のオープンデータカタログ"
          url="https://data.e-gov.go.jp/"
        />
        <ExternalLink
          title="NISTEP 議事録メタデータ"
          description="本サイトのデータソース（GitHub）"
          url="https://github.com/NISTEP/minutes"
        />
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 text-center">
      <div className="text-2xl font-bold text-slate-800">{value}</div>
      <div className="text-sm text-slate-500 mt-1">{label}</div>
    </div>
  );
}

function ExternalLink({
  title,
  description,
  url,
}: {
  title: string;
  description: string;
  url: string;
}) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-white rounded-lg border border-slate-200 p-4 hover:shadow-md hover:border-slate-300 transition-all"
    >
      <h3 className="font-semibold text-blue-600 text-sm">{title}</h3>
      <p className="text-xs text-slate-500 mt-1">{description}</p>
    </a>
  );
}
