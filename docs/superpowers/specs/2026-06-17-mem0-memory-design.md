# mem0 记忆组件集成设计

**日期：** 2026-06-17  
**状态：** 已批准  
**作者：** Arjun

---

## 背景

当前聊天 Agent 通过 `PostgresSaver` 保存单次会话内的消息历史（thread_id = conversation_id），并通过 `extract_preferences_node` + `user_prefs`/`user_profile` 持久化用户偏好。但两次不同会话之间没有跨会话情节记忆——用户在 A 会话中提到"我看好 BTC 短线"，在 B 会话中 Agent 不知道。

**目标：** 引入 mem0 作为跨会话长期记忆层，让 Agent 能在每轮回复前召回用户历史偏好、关注标的、投资风格等记忆片段，实现个性化增强。

---

## 设计决策

### 异步策略：召回同步 + 存储异步

- **召回（recall）同步**：Agent 回复前必须拿到记忆，否则记忆无意义
- **存储（store）异步**：用户不感知存储时机，后台线程写入，不阻塞 SSE 响应
- 与现有 `extract_preferences_node` 后台线程模式一致

---

## 架构

### Graph 拓扑

```
START
  ↓
init_context_node       （现有）加载 user_profile + user_prefs
  ↓
mem0_recall_node        （新增）同步检索 mem0，注入 memories 到状态
  ↓
agent_node              （改造）system prompt 追加 <memories> 段落
  ↓ (tool_calls?)
tools_node ←────────────（现有）工具调用循环
  ↓ (no tool_calls)
extract_preferences_node（现有）规则+LLM 偏好提取，后台写 user_prefs
  ↓
mem0_store_node         （新增）后台线程异步存储本轮对话记忆
  ↓
END
```

### 状态扩展

```python
class AgentState(MessagesState):
    user_profile: dict
    user_prefs: dict
    consecutive_tool_failures: int = 0
    memories: list[str]          # 新增：本轮召回的记忆列表
```

---

## 各节点详细设计

### `mem0_recall_node`（新增，同步）

- 从 `config["metadata"]["user_id"]` 获取用户 ID
- 取 `state["messages"]` 中最后一条 `HumanMessage` 作为检索 query
- 调用 `mem0_client.search(query, user_id=user_id, limit=settings.mem0_top_k)`
- 返回 `{"memories": [r["memory"] for r in results["results"]]}`
- 若 mem0 不可用（超时/异常）：静默降级，返回 `{"memories": []}`，不阻断主链路
- 性能目标：p95 < 300ms（mem0 cloud SLA）

### `agent_node`（改造）

`_build_prompt_from_state` 函数追加 `<memories>` 段落：

```python
if memories := state.get("memories"):
    prompt += (
        "\n\n<memories>\n以下是用户的历史偏好和记忆，请结合这些信息回答：\n"
        + "\n".join(f"- {m}" for m in memories)
        + "\n</memories>"
    )
```

无记忆时不追加，不影响现有 prompt 结构。

### `mem0_store_node`（新增，异步）

- 提取本轮最后一条 `HumanMessage` + 最后一条 `AIMessage`（非 tool call）
- 格式化为 mem0 messages 格式：`[{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]`
- 启动 daemon 线程调用 `mem0_client.add(messages, user_id=user_id)`
- 节点本身立即返回 `{}`，不等待线程完成
- 失败静默忽略（loguru warning），不影响对话

### Graph 边改动

```python
# 旧
graph.add_edge("init", "agent")
graph.add_edge("extract_preferences", END)

# 新
graph.add_edge("init", "mem0_recall")
graph.add_edge("mem0_recall", "agent")
graph.add_edge("extract_preferences", "mem0_store")
graph.add_edge("mem0_store", END)
```

---

## 配置项

在 `app/core/config.py` 的 `Settings` 类中新增：

```python
mem0_enabled: bool = True
mem0_api_key: str = ""         # mem0 cloud API key；为空时自动降级为 disabled
mem0_base_url: str = ""        # 自托管 mem0 server URL（可选，优先于 cloud）
mem0_top_k: int = 5            # 每轮召回记忆条数上限
```

`.env` 对应：
```
MEM0_ENABLED=true
MEM0_API_KEY=your_key_here
MEM0_BASE_URL=              # 留空表示使用 cloud
MEM0_TOP_K=5
```

---

## mem0 客户端初始化

新建 `app/memory/mem0_client.py`：

- 单例模式，线程安全
- 根据 `settings.mem0_enabled` 和 `settings.mem0_api_key` 决定是否启用
- `mem0_base_url` 非空时使用自托管配置
- 导出 `get_mem0_client() -> MemoryClient | None`（disabled 时返回 None，调用方需判断）

---

## 依赖

`pyproject.toml` 新增：

```
mem0ai>=0.1.0
```

---

## 错误处理 & 降级

| 场景 | 处理方式 |
|------|---------|
| mem0_api_key 未配置 | 跳过 recall/store，nodes 直接返回 `{}` |
| mem0 cloud 超时（>500ms） | 捕获异常，返回 `{"memories": []}`，warning 日志 |
| mem0 store 失败 | 后台线程捕获异常，warning 日志，不影响对话 |
| mem0 返回空结果 | 正常处理，不追加 `<memories>` 段落 |

---

## 与现有记忆系统的关系

| 组件 | 作用 | 是否保留 |
|------|------|---------|
| `PostgresSaver` | 单次会话内消息历史 | 保留 |
| `user_prefs` / `user_profile` | 结构化偏好（DB 表） | 保留 |
| `extract_preferences_node` | 从对话提取偏好写 DB | 保留 |
| **mem0**（新增）| 跨会话情节记忆（语义检索） | 新增 |

mem0 不替代现有系统，而是补充跨会话的长期情节记忆层。

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `app/core/config.py` | 修改 | 新增 4 个 mem0 配置项 |
| `app/memory/mem0_client.py` | 新建 | mem0 客户端单例 |
| `app/agents/chat_agent.py` | 修改 | 新增 2 个节点，改造 graph 拓扑和 agent_node prompt |
| `pyproject.toml` | 修改 | 新增 `mem0ai` 依赖 |
