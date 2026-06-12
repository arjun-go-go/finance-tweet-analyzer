"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  createConversation,
  listConversations,
  listMessages,
  deleteConversation,
  getAccessToken,
  type ConversationListItem,
} from "@/lib/api";
import { isAuthenticated, logout, fetchMe, refreshAccessToken, type AuthUser } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
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

    const messageId = crypto.randomUUID();
    const userDisplay: DisplayMessage = {
      id: messageId,
      role: "user",
      content: userMsg,
    };
    setMessages((prev) => [...prev, userDisplay]);
    setLoading(true);
    setToolStatus(null);

    const assistantId = crypto.randomUUID();
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

  return (
    <div className="flex h-[calc(100vh-120px)] -mx-6 -my-8">
      {/* Sidebar */}
      <div className="w-72 bg-gray-900 text-white flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <button
            onClick={handleNewConversation}
            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors"
          >
            + 新建会话
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {sidebarLoading ? (
            <p className="text-gray-400 text-sm text-center py-4">加载中...</p>
          ) : conversations.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-4">
              暂无会话，点击上方新建
            </p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => selectConversation(conv.id)}
                className={`group flex items-center gap-2 px-4 py-3 cursor-pointer border-b border-gray-800 hover:bg-gray-800 transition-colors ${
                  activeConvId === conv.id ? "bg-gray-800" : ""
                }`}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">
                    {conv.title || "新对话"}
                  </p>
                  <p className="text-xs text-gray-400 truncate">
                    {conv.last_message_preview || "暂无消息"}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDeleteConversation(conv.id, e)}
                  className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-400 text-xs transition-opacity"
                  title="删除"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>

        {user && (
          <div className="p-3 border-t border-gray-700 flex items-center justify-between">
            <span className="text-xs text-gray-400">{user.username}</span>
            <button
              onClick={logout}
              className="px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
              title="退出登录"
            >
              退出
            </button>
          </div>
        )}
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col bg-white">
        <div className="px-6 py-3 border-b flex items-center justify-between">
          <h1 className="text-lg font-semibold">
            {activeConvId
              ? conversations.find((c) => c.id === activeConvId)?.title || "新对话"
              : "智能助手"}
          </h1>
          <p className="text-xs text-gray-400">
            输入 Twitter 用户名获取博主信息，或查询分析数据
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 py-20">
              <p className="text-lg mb-2">开始新的对话</p>
              <p className="text-sm">
                试试: "获取 qinbafrank 的推文" / "有哪些博主" / "分析 BTC 相关推文"
              </p>
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`px-4 py-2 rounded-lg max-w-[80%] whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-800"
                }`}
              >
                {msg.content || "思考中..."}
              </div>
            </div>
          ))}
          {toolStatus && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-md bg-blue-50 border border-blue-100">
              <span className="inline-block w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-sm text-blue-600">{toolStatus}</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="px-6 py-4 border-t">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder="输入消息..."
              className="flex-1 border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "处理中..." : "发送"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
