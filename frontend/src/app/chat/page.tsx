"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AppIcon from "@/components/AppIcon";
import {
  createConversation,
  listConversations,
  listMessages,
  deleteConversation,
  getAccessToken,
  type ConversationListItem,
} from "@/lib/api";
import { isAuthenticated, fetchMe, refreshAccessToken, type AuthUser } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

function createClientId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  return `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function ChatPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [sidebarLoading, setSidebarLoading] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    fetchMe().then((u) => {
      if (!u) {
        router.push("/login");
        return;
      }
      setUser(u);
      loadConversations();
    });
  }, [router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, toolStatus]);

  const loadConversations = async () => {
    setSidebarLoading(true);
    try {
      const data = await listConversations({ limit: 50 });
      setConversations(data.items);
    } catch {
      // silently fail
    } finally {
      setSidebarLoading(false);
    }
  };

  const loadMessages = useCallback(async (convId: string) => {
    try {
      const data = await listMessages(convId, {
        limit: 100,
        direction: "forward",
      });
      const display: DisplayMessage[] = data.items
        .filter((m) => m.role === "human" || m.role === "ai")
        .map((m) => ({
          id: m.id,
          role: m.role === "human" ? "user" : "assistant",
          content: m.content,
        }));
      setMessages(display);
    } catch {
      setMessages([]);
    }
  }, []);

  const selectConversation = async (convId: string) => {
    setActiveConvId(convId);
    setToolStatus(null);
    await loadMessages(convId);
  };

  const handleNewConversation = async () => {
    try {
      const conv = await createConversation();
      setConversations((prev) => [
        {
          id: conv.id,
          title: null,
          status: "active",
          message_count: 0,
          last_message_at: null,
          last_message_preview: null,
          created_at: conv.created_at,
        },
        ...prev,
      ]);
      setActiveConvId(conv.id);
      setMessages([]);
    } catch {
      alert("创建会话失败");
    }
  };

  const handleDeleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定删除此会话？")) return;
    try {
      await deleteConversation(convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConvId === convId) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch {
      alert("删除失败");
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");

    let convId = activeConvId;
    if (!convId) {
      try {
        const conv = await createConversation();
        convId = conv.id;
        setActiveConvId(convId);
        setConversations((prev) => [
          {
            id: conv.id,
            title: null,
            status: "active",
            message_count: 0,
            last_message_at: null,
            last_message_preview: null,
            created_at: conv.created_at,
          },
          ...prev,
        ]);
      } catch {
        alert("创建会话失败");
        return;
      }
    }

    const messageId = createClientId();
    const userDisplay: DisplayMessage = {
      id: messageId,
      role: "user",
      content: userMsg,
    };
    setMessages((prev) => [...prev, userDisplay]);
    setLoading(true);
    setToolStatus(null);

    const assistantId = createClientId();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "" },
    ]);

    try {
      let token = getAccessToken();
      let res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          conversation_id: convId,
          message_id: messageId,
          message: userMsg,
        }),
      });

      if (res.status === 401) {
        const newToken = await refreshAccessToken();
        if (!newToken) {
          router.push("/login");
          return;
        }
        token = newToken;
        res = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            conversation_id: convId,
            message_id: messageId,
            message: userMsg,
          }),
        });
        if (res.status === 401) {
          router.push("/login");
          return;
        }
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "请求失败" }));
        throw new Error(err.detail || "请求失败");
      }

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const dataStr = line.slice(5).trim();
            if (!dataStr) continue;

            try {
              const data = JSON.parse(dataStr);

              if (currentEvent === "token" && data.content) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content + data.content,
                  };
                  return updated;
                });
                setToolStatus(null);
              } else if (currentEvent === "tool_call" && data.tools) {
                setToolStatus(data.label || data.tools[0]);
              } else if (currentEvent === "done") {
                setToolStatus(null);
              } else if (currentEvent === "error") {
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    content: `出错了: ${data.error || "未知错误"}`,
                  };
                  return updated;
                });
              }
            } catch {
              // ignore malformed JSON
            }
            currentEvent = "";
          }
        }
      }

      loadConversations();
      setTimeout(() => loadConversations(), 3000);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "请求失败";
      setMessages((prev) => {
        const updated = [...prev];
        if (updated[updated.length - 1]?.role === "assistant") {
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: errorMsg,
          };
        }
        return updated;
      });
    } finally {
      setLoading(false);
      setToolStatus(null);
    }
  };

  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant" && message.content);
  const evidenceTools = latestAssistant
    ? Array.from(new Set(Array.from(latestAssistant.content.matchAll(/【tool:([^】]+)】/g), (match) => match[1])))
    : [];
  const evidenceLabels: Record<string, string> = {
    query_database: "结构化数据库",
    search_public_signals: "公共信号库",
    search_my_documents: "私人文档",
    list_my_tracked_tickers: "个人 Watchlist",
    list_my_followed_bloggers: "正式关注关系",
    fetch_and_save_tweets: "实时推文采集",
    fetch_and_save_profile: "博主公开资料",
  };

  return (
    <div className="chat-workspace">
      <aside className="chat-conversations">
        <div className="chat-side-header"><span>研究会话</span><button onClick={handleNewConversation}>新建</button></div>
        <div className="chat-conversation-list">
          {sidebarLoading ? <p className="chat-muted">正在加载会话</p> : conversations.length === 0 ? <p className="chat-muted">还没有研究会话</p> : conversations.map((conv) => (
            <button key={conv.id} onClick={() => selectConversation(conv.id)} className={`chat-conversation ${activeConvId === conv.id ? "is-active" : ""}`}>
              <span><strong>{conv.title || "未命名研究"}</strong><small>{conv.last_message_preview || "暂无消息"}</small></span>
              <span onClick={(event) => handleDeleteConversation(conv.id, event)} className="chat-delete" title="删除会话">×</span>
            </button>
          ))}
        </div>
        <div className="chat-user"><span>{user?.username || "研究账户"}</span><small>私人工作空间</small></div>
      </aside>

      <section className="chat-stage">
        <header className="chat-stage-header">
          <div><p>Research copilot</p><h1>{activeConvId ? conversations.find((item) => item.id === activeConvId)?.title || "新研究" : "研究助手"}</h1></div>
          <select className="chat-mobile-select" value={activeConvId || ""} onChange={(event) => event.target.value ? selectConversation(event.target.value) : handleNewConversation()} aria-label="选择会话">
            <option value="">新建研究</option>{conversations.map((conv) => <option key={conv.id} value={conv.id}>{conv.title || "未命名研究"}</option>)}
          </select>
          <span className="chat-grounded"><span />证据约束已开启</span>
        </header>

        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="research-empty">
              <span className="empty-radar"><span /></span>
              <h2>从一个研究问题开始</h2>
              <p>助手会检索你的关注关系、私人文档和公共市场信号，并在具体事实后标明来源。</p>
              <div className="research-starters">
                {["我关注的博主最近有哪些重要观点？", "总结 BTC 最近的市场情绪", "我的私人文档如何评价 NVDA？", "哪些标的出现了新的风险信号？"].map((prompt) => <button key={prompt} onClick={() => setInput(prompt)}>{prompt}<AppIcon name="arrow" /></button>)}
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <article key={msg.id} className={`research-message is-${msg.role} ${msg.role === "assistant" && /出错|失败|无法连接/.test(msg.content) ? "is-error" : ""}`}>
              <div className="research-message-label">{msg.role === "user" ? "你" : "Signal Desk"}</div>
              {msg.role === "user" ? <p>{msg.content}</p> : (
                <div className="research-markdown">
                  {msg.content ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown> : <span className="thinking-line"><span />正在核对来源</span>}
                </div>
              )}
            </article>
          ))}
          {toolStatus && <div className="tool-progress"><span className="signal-loader" /><div><strong>{toolStatus}</strong><small>正在检索并验证证据</small></div></div>}
          <div ref={bottomRef} />
        </div>

        <footer className="chat-composer">
          <div className="chat-scope-row"><span>研究范围</span><b>我的关注</b><b>公共信号</b><b>私人文档</b></div>
          <div className="chat-input-wrap">
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); handleSend(); } }} placeholder="询问一个标的、博主或研究资料…" disabled={loading} rows={2} />
            <button onClick={handleSend} disabled={loading || !input.trim()} aria-label="发送研究问题"><AppIcon name="arrow" /></button>
          </div>
          <small>Enter 发送 · Shift + Enter 换行 · 金融结论仅供研究参考</small>
        </footer>
      </section>

      <aside className="chat-evidence-rail">
        <div className="chat-rail-heading"><AppIcon name="evidence" /><div><strong>本轮证据</strong><small>回答使用的数据范围</small></div></div>
        {evidenceTools.length > 0 ? <div className="chat-evidence-list">{evidenceTools.map((tool) => <div key={tool}><span /><strong>{evidenceLabels[tool] || tool}</strong><small>已用于最近回答</small></div>)}</div> : <div className="chat-evidence-empty"><p>提出问题后，这里会显示最近回答使用的数据源。</p></div>}
        <div className="chat-rail-note"><span>证据规则</span><p>账户数据、博主观点和市场事实必须来自工具结果；证据不足时助手会停止推断。</p></div>
      </aside>
    </div>
  );
}
