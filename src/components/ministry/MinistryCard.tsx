import Link from "next/link";

interface MinistryCardProps {
  slug: string;
  name: string;
  nameEn: string;
  color: string;
  documentCount: number;
  committeeCount: number;
}

export function MinistryCard({
  slug,
  name,
  nameEn,
  color,
  documentCount,
  committeeCount,
}: MinistryCardProps) {
  return (
    <Link
      href={`/ministries/${slug}`}
      className="block bg-white rounded-lg border border-slate-200 p-5 hover:shadow-md hover:border-slate-300 transition-all"
    >
      <div className="flex items-start gap-3">
        <div
          className="w-3 h-3 rounded-full mt-1.5 shrink-0"
          style={{ backgroundColor: color }}
        />
        <div className="min-w-0">
          <h3 className="font-semibold text-slate-800 text-lg">{name}</h3>
          <p className="text-xs text-slate-400 mt-0.5">{nameEn}</p>
          <div className="flex gap-4 mt-3 text-sm text-slate-600">
            <span>
              <span className="font-semibold text-slate-800">
                {documentCount.toLocaleString()}
              </span>{" "}
              件
            </span>
            <span>
              <span className="font-semibold text-slate-800">
                {committeeCount}
              </span>{" "}
              審議会
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
