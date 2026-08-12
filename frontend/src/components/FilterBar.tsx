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
    <div className="filter-panel">
      <div className="filter-field">
        <span>信息源</span>
        <input
          type="text"
          value={localBlogger}
          onChange={(e) => setLocalBlogger(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onBloggerChange(localBlogger)}
          placeholder="输入 handle..."
          className=""
        />
      </div>
      <div className="filter-field">
        <span>内容检索</span>
        <input
          type="text"
          value={localSearch}
          onChange={(e) => setLocalSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearchChange(localSearch)}
          placeholder="关键词..."
          className=""
        />
      </div>
      <div className="filter-actions">
        <button
          onClick={() => {
            onBloggerChange(localBlogger);
            onSearchChange(localSearch);
            onApply();
          }}
          className="button-primary"
        >
          筛选
        </button>
        <button
          onClick={() => {
            setLocalBlogger("");
            setLocalSearch("");
            onClear();
          }}
          className="button-secondary"
        >
          清空
        </button>
      </div>
    </div>
  );
}
