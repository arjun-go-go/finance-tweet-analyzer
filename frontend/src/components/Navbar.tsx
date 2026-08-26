"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "今日" },
  { href: "/sources", label: "信息源" },
  { href: "/watch", label: "关注" },
  { href: "/assistant", label: "助手" },
];

export default function Navbar() {
  const pathname = usePathname();
  return (
    <nav aria-label="主导航">
      {links.map((link) => (
        <Link key={link.href} href={link.href} aria-current={pathname === link.href ? "page" : undefined}>
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
