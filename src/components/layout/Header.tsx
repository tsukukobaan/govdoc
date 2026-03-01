import Link from "next/link";
import { SearchBar } from "@/components/search/SearchBar";

export function Header() {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-xl font-bold text-slate-800">
              GovDoc Index
            </span>
            <span className="text-xs text-slate-500 hidden sm:inline">
              政府審議会議事録インデックス
            </span>
          </Link>
          <div className="flex items-center gap-4">
            <SearchBar />
          </div>
        </div>
      </div>
    </header>
  );
}
