"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { isAuthenticated, fetchMe } from "@/lib/auth";
import AppShell from "@/components/AppShell";

const PUBLIC_PATHS = ["/login", "/register"];

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    // Recover from an absolute app URL accidentally appended to the current origin,
    // e.g. /http:/192.168.31.156:3000/ after Next.js path normalization.
    if (/^\/https?:\//i.test(pathname)) {
      router.replace("/");
      return;
    }

    if (PUBLIC_PATHS.includes(pathname)) {
      setChecked(true);
      return;
    }

    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }

    fetchMe()
      .then((user) => {
        if (!user) {
          router.replace("/login");
        } else {
          setChecked(true);
        }
      })
      .catch(() => router.replace("/login"));
  }, [pathname, router]);

  if (PUBLIC_PATHS.includes(pathname)) {
    return <>{children}</>;
  }

  if (!checked) {
    return (
      <div className="auth-loading">
        <span className="workspace-brand-mark"><span /></span>
        <p>正在进入投资情报工作台</p>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
