"use client";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

const STATUS_CONFIG: Record<string, { color: string; label: string; pulse?: boolean }> = {
  indexed: { color: "bg-green-100 text-green-800", label: "已入库" },
  ready: { color: "bg-green-100 text-green-800", label: "已就绪" },
  processing: { color: "bg-yellow-100 text-yellow-800", label: "处理中", pulse: true },
  pending: { color: "bg-gray-100 text-gray-800", label: "等待中" },
  error: { color: "bg-red-100 text-red-800", label: "失败" },
  generating: { color: "bg-blue-100 text-blue-800", label: "生成中", pulse: true },
  done: { color: "bg-green-100 text-green-800", label: "已完成" },
  failed: { color: "bg-red-100 text-red-800", label: "失败" },
  active: { color: "bg-green-100 text-green-800", label: "活跃" },
  paused: { color: "bg-yellow-100 text-yellow-800", label: "已暂停" },
};

export default function StatusBadge({ status, size = "sm" }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const colorClass = config?.color ?? "bg-gray-100 text-gray-800";
  const label = config?.label ?? status;
  const pulse = config?.pulse ?? false;

  const sizeClass = size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${colorClass} ${sizeClass} ${
        pulse ? "animate-pulse" : ""
      }`}
    >
      {label}
    </span>
  );
}
