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
    { label: "总推文数", value: totalTweets, color: "bg-blue-500", href: "/tweets" },
    { label: "待分析", value: pendingTweets, color: "bg-yellow-500", href: "/tweets?status=pending" },
    { label: "已分析", value: analyzedTweets, color: "bg-green-500", href: "/tweets?status=analyzed" },
    { label: "分析结果", value: totalAnalyses, color: "bg-purple-500", href: "/results" },
    { label: "关注博主", value: totalBloggers, color: "bg-pink-500", href: "/bloggers" },
    {
      label: "待标注预测",
      value: pendingPredictions,
      color: "bg-orange-500",
      href: "/bloggers?sort=pending_count",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
      {stats.map((stat) => {
        const clickable = stat.href !== null;
        return (
          <div
            key={stat.label}
            onClick={clickable ? () => router.push(stat.href!) : undefined}
            className={`bg-white rounded-lg shadow p-4 ${
              clickable ? "cursor-pointer hover:shadow-md transition" : ""
            }`}
          >
            <div className={`w-2 h-2 rounded-full ${stat.color} mb-2`} />
            <p className="text-2xl font-bold">{stat.value}</p>
            <p className="text-sm text-gray-500">{stat.label}</p>
          </div>
        );
      })}
    </div>
  );
}
