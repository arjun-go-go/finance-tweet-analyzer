"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { isAuthenticated, fetchMe } from "@/lib/auth";
import Navbar from "@/components/Navbar";
import Breadcrumb from "@/components/Breadcrumb";

const PUBLIC_PATHS = ["/login", "/register"];

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (PUBLIC_PATHS.includes(pathname)) {
      setChecked(true);
      return;
    }

    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }

    fetchMe().then((user) => {
      if (!user) {
        router.replace("/login");
      } else {
        setChecked(true);
      }
    });
  }, [pathname, router]);

  if (PUBLIC_PATHS.includes(pathname)) {
    return <>{children}</>;
  }

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400">验证登录状态...</p>
      </div>
    );
  }

  return (
    <>
      <Navbar />
      <Breadcrumb />
      <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
    </>
  );
}
