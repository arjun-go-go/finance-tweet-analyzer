"use client";

import { useState } from "react";

interface FilterBarProps {
  blogger: string;
  search: string;
  onBloggerChange: (v: string) => void;
  onSearchChange: (v: string) => void;
  onApply: () => void;
  onClear: () => void;
}

export default function FilterBar({
  blogger,
  search,
  onBloggerChange,
  onSearchChange,
  onApply,
  onClear,
}: FilterBarProps) {
  const [localBlogger, setLocalBlogger] = useState(blogger);
  const [localSearch, setLocalSearch] = useState(search);

  return (
    <div className="flex flex-wrap items-center gap-3 bg-white rounded-lg shadow p-3">
      <div className="flex items-center gap-2 flex-1 min-w-[200px]">
        <span className="text-sm text-gray-500 shrink-0">博主</span>
        <input
          type="text"
          value={localBlogger}
          onChange={(e) => setLocalBlogger(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onBloggerChange(localBlogger)}
          placeholder="输入 handle..."
          className="flex-1 border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div className="flex items-center gap-2 flex-1 min-w-[200px]">
        <span className="text-sm text-gray-500 shrink-0">搜索</span>
        <input
          type="text"
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearchChange(localSearch)}
          placeholder="关键词..."
          className="flex-1 border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => {
            onBloggerChange(localBlogger);
            onSearchChange(localSearch);
            onApply();
          }}
          className="px-4 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 transition-colors"
        >
          筛选
        </button>
        <button
          onClick={() => {
            setLocalBlogger("");
            setLocalSearch("");
            onClear();
          }}
          className="px-4 py-1.5 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200 transition-colors"
        >
          清空
        </button>
      </div>
    </div>
  );
}
