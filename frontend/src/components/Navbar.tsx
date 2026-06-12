import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="bg-gray-900 text-white px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link href="/" className="text-xl font-bold">
          Finance Tweet Analyzer
        </Link>
        <div className="flex gap-6">
          <Link href="/" className="hover:text-blue-400">
            Dashboard
          </Link>
          <Link href="/tweets" className="hover:text-blue-400">
            推文列表
          </Link>
          <Link href="/results" className="hover:text-blue-400">
            分析结果
          </Link>
          <Link href="/analyses" className="hover:text-blue-400">
            推文分析
          </Link>
          <Link href="/tickers" className="hover:text-blue-400">
            标的推荐
          </Link>
          <Link href="/bloggers" className="hover:text-blue-400">
            博主排行
          </Link>
          <Link href="/documents" className="hover:text-blue-400">
            文档
          </Link>
          <Link href="/reports" className="hover:text-blue-400">
            报告
          </Link>
          <Link href="/tracking" className="hover:text-blue-400">
            追踪
          </Link>
          <Link href="/retrieval-test" className="hover:text-blue-400">
            检索测试
          </Link>
          <Link href="/chat" className="hover:text-blue-400">
            智能助手
          </Link>
        </div>
      </div>
    </nav>
  );
}
