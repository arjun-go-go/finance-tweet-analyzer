"use client";

import { useRouter } from "next/navigation";

interface StatsProps {
  totalTweets: number;
  pendingTweets: number;
  analyzedTweets: number;
  totalAnalyses: number;
  totalBloggers: number;
  pendingPredictions?: number;
}

export default function DashboardStats({
  totalTweets,
  pendingTweets,
  analyzedTweets,
  totalAnalyses,
  totalBloggers,
  pendingPredictions = 0,
}: StatsProps) {
  const router = useRouter();
  const stats = [
    { label: "总推文", value: totalTweets, dot: "bg-blue-500", href: "/tweets" },
    { label: "待分析", value: pendingTweets, dot: "bg-yellow-500", href: "/tweets?tab=pending" },
    { label: "已分析", value: analyzedTweets, dot: "bg-green-500", href: "/tweets?tab=analyzed" },
    { label: "分析结果", value: totalAnalyses, dot: "bg-purple-500", href: "/tweets?tab=analyzed" },
    { label: "博主", value: totalBloggers, dot: "bg-pink-500", href: "/bloggers" },
    { label: "待标注", value: pendingPredictions, dot: "bg-orange-500", href: "/bloggers?sort=pending_count" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {stats.map((stat) => (
        <button
          key={stat.label}
          onClick={() => router.push(stat.href)}
          className="bg-white rounded-lg shadow p-4 text-left hover:shadow-md transition-shadow"
        >
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2.5 h-2.5 rounded-full ${stat.dot}`} />
            <span className="text-sm text-gray-500">{stat.label}</span>
          </div>
          <p className="text-2xl font-bold text-gray-800">{stat.value}</p>
        </button>
      ))}
    </div>
  );
}
