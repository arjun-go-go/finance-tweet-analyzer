import Link from "next/link";

export default function AuthFrame({ mode, children }: { mode: "login" | "register"; children: React.ReactNode }) {
  const login = mode === "login";
  return (
    <main className="auth-page">
      <section className="auth-thesis">
        <div className="auth-brand"><span className="workspace-brand-mark"><span /></span><strong>Signal Desk</strong></div>
        <div className="auth-thesis-copy">
          <p>AI investment intelligence</p>
          <h1>市场观点很多，<br />值得相信的很少。</h1>
          <span>持续追踪博主、标的和私人研究资料，把分散信息整理成可验证、可回溯的投资情报。</span>
        </div>
        <div className="auth-proof">
          <div><b>01</b><span>重要观点自动聚合</span></div>
          <div><b>02</b><span>每个结论回到原始证据</span></div>
          <div><b>03</b><span>私人资料与市场观点联合研究</span></div>
        </div>
      </section>
      <section className="auth-form-side">
        <div className="auth-form-card">
          <p className="page-eyebrow">{login ? "Welcome back" : "Create workspace"}</p>
          <h2>{login ? "进入研究工作台" : "建立你的情报工作台"}</h2>
          <p>{login ? "继续查看与你关注范围相关的市场变化。" : "从关注一个标的或博主开始。"}</p>
          {children}
          <div className="auth-switch">{login ? "还没有账号？" : "已经有账号？"}<Link href={login ? "/register" : "/login"}>{login ? "创建账户" : "直接登录"}</Link></div>
        </div>
      </section>
    </main>
  );
}

