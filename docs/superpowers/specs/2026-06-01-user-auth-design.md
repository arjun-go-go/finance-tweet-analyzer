# User Authentication System — Design Spec

> Sub-spec of `finance-tweet-analyzer`. Adds JWT-based user authentication to replace the current "trust the client" user_id model.

## Goals

- 用户注册/登录（邮箱 + 密码）
- JWT 双 token 机制（短期 access_token + 长期 refresh_token）
- FastAPI 中间件统一提取 user_id，去掉 API 请求 body 中的 user_id 字段
- 前端登录/注册页 + token 存储 + 请求拦截器
- 平滑迁移：现有数据中 user_id="default" 的记录自动关联到首个注册用户

## Non-Goals

- OAuth2 第三方登录（Google/GitHub）— 预留但不实现
- 邮箱验证 / 密码重置 — 后续迭代
- RBAC 角色权限 — 当前单角色
- 多租户 — 保持单租户

## Decisions

| Topic | Decision |
|---|---|
| 密码存储 | bcrypt hash (已有依赖) |
| Token 库 | PyJWT (已有依赖) |
| Access Token 有效期 | 30 分钟 |
| Refresh Token 有效期 | 7 天 |
| Token 存储 (前端) | localStorage (access) + httpOnly cookie (refresh) |
| 前端 Token 刷新 | 401 响应时自动调用 refresh 端点 |
| 用户标识 | users.id (UUID) 作为全局 user_id |
| 密码策略 | 最少 6 字符 |

---

## §1 Data Model

### New table: `users`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | 作为全局 user_id |
| email | VARCHAR(256) UNIQUE | 登录标识 |
| username | VARCHAR(64) UNIQUE | 显示名 |
| password_hash | VARCHAR(256) | bcrypt |
| status | VARCHAR(16) DEFAULT 'active' | active / disabled |
| created_at | TIMESTAMP WITH TZ | |
| last_login_at | TIMESTAMP WITH TZ NULL | |

---

## §2 API Endpoints

### `POST /api/auth/register`
```json
{"email": "x@y.com", "username": "test", "password": "123456"}
→ 201 {"id": "uuid", "email": "...", "username": "...", "access_token": "...", "refresh_token": "..."}
```

### `POST /api/auth/login`
```json
{"email": "x@y.com", "password": "123456"}
→ 200 {"access_token": "...", "refresh_token": "...", "user": {...}}
```

### `POST /api/auth/refresh`
```json
{"refresh_token": "..."}
→ 200 {"access_token": "...", "refresh_token": "..."}
```

### `GET /api/auth/me`
Header: `Authorization: Bearer <access_token>`
→ 200 `{"id": "uuid", "email": "...", "username": "..."}`

---

## §3 Auth Middleware

```python
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    user = db.get(User, payload["sub"])
    if not user or user.status != "active":
        raise HTTPException(401)
    return user
```

所有需要认证的 API 加 `current_user: User = Depends(get_current_user)`。

---

## §4 迁移策略

现有 API 中的 `user_id` 参数全部移除，改从 JWT 解析：
- `POST /api/chat` — 去掉 body 中 user_id
- `GET /api/chat/conversations` — 去掉 query param user_id
- 其他 chat 端点同理

---

## §5 前端

- 新增 `/login` 和 `/register` 页面
- `lib/auth.ts` — token 存储 + 刷新逻辑
- 修改 `lib/api.ts` — 所有请求加 Authorization header
- 未登录跳转 `/login`
- Chat 页面去掉 hardcoded USER_ID
