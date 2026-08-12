"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AuthFrame from "@/components/AuthFrame";
import { register } from "@/lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(email, username, password);
      router.push("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthFrame mode="register">
      {error && <div className="auth-error">{error}</div>}
      <form onSubmit={handleSubmit} className="auth-form">
        <label>邮箱<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required placeholder="your@email.com" /></label>
        <label>用户名<input type="text" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={2} placeholder="至少 2 个字符" /></label>
        <label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={6} placeholder="至少 6 位" /></label>
        <button type="submit" disabled={loading}>{loading ? "正在创建…" : "创建工作台"}</button>
      </form>
    </AuthFrame>
  );
}
