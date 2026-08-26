import Link from "next/link";

export default function AuthFrame({ mode, children }: { mode: "login" | "register"; children: React.ReactNode }) {
  const login = mode === "login";
  return (
    <main className="auth-page">
      <section className="auth-thesis">
        <div className="auth-brand"><span className="workspace-brand-mark"><span /></span><strong>Signal</strong></div>
        <div className="auth-thesis-copy">
          <p>Twitter investment intelligence</p>
          <h1>关注观点变化，<br />而不是信息噪音。</h1>
          <span>从博主推文、图片和历史结果中提取可追溯、可验证的投资情报。</span>
        </div>
        <div className="auth-proof">
          <div><b>01</b><span>证据可回溯</span></div>
          <div><b>02</b><span>标的已核验</span></div>
          <div><b>03</b><span>预测可验证</span></div>
        </div>
      </section>
      <section className="auth-form-side">
        <div className="auth-form-card">
          <p className="page-eyebrow">{login ? "Welcome back" : "Create workspace"}</p>
          <h2>{login ? "欢迎回来" : "创建个人情报工作台"}</h2>
          <p>{login ? "继续查看你关注的博主和标的。" : "从关注一个 Twitter 信息源开始。"}</p>
          {children}
          <div className="auth-switch">{login ? "还没有账号？" : "已经有账号？"}<Link href={login ? "/register" : "/login"}>{login ? "创建账户" : "直接登录"}</Link></div>
        </div>
      </section>
    </main>
  );
}
