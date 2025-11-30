# Technical Specification: Token Selection for MCP Tools

- **Functional Specification:** `context/spec/002-token-selection/functional-spec.md`
- **Status:** Draft
- **Author(s):** Claude

---

## 1. High-Level Technical Approach

This feature enables users to select which Slack token (bot or user) to use for each MCP tool call. The implementation involves:

1. **Breaking change:** Require both tokens at startup (no opt-out)
2. **Internal refactoring:** Rename `client` to `bot_client` for consistency
3. **New parameter:** Add `token_type` parameter to all 8 MCP tools
4. **Helper function:** Add `get_client()` to return the correct WebClient based on token type
5. **Documentation:** Update all tool descriptions to explain token selection

**Affected files:**
- `src/slack_mcp_server/provider.py` - Token validation and client renaming
- `src/slack_mcp_server/server.py` - All tool definitions and helper function

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Provider Changes (`src/slack_mcp_server/provider.py`)

#### 2.1.1 Rename `client` to `bot_client`

**Current:**
```python
self.client = WebClient(token=bot_token, ssl=ssl_context)
```

**New:**
```python
self.bot_client = WebClient(token=bot_token, ssl=ssl_context)
```

**Internal references to update:**
- `SlackProvider.auth_test()` - uses `self.client.auth_test()`
- `SlackProvider.refresh_users()` - uses `self.client.users_list()`
- `SlackProvider._fetch_channels_by_type()` - uses `self.client.conversations_list()`

#### 2.1.2 Require Both Tokens

**Current validation:**
```python
if not bot_token:
    raise ValueError("Authentication required: bot_token must be provided")
```

**New validation:**
```python
missing = []
if not bot_token:
    missing.append("SLACK_MCP_BOT_TOKEN")
if not user_token:
    missing.append("SLACK_MCP_USER_TOKEN")
if missing:
    raise ValueError(
        f"Both bot and user tokens are required. Missing: {', '.join(missing)}"
    )
```

#### 2.1.3 Make `user_client` Non-Optional

**Current:**
```python
self.user_client: WebClient | None = None
if user_token:
    self.user_client = WebClient(token=user_token, ssl=ssl_context)
```

**New:**
```python
self.user_client = WebClient(token=user_token, ssl=ssl_context)
```

The type annotation changes from `WebClient | None` to `WebClient`.

---

### 2.2 Server Changes (`src/slack_mcp_server/server.py`)

#### 2.2.1 Add Type Alias

Add at module level (near other imports/constants):

```python
from typing import Literal

TokenType = Literal["bot", "user"]
```

#### 2.2.2 Add Helper Function

Add after existing helper functions (around line 288):

```python
def get_client(provider: SlackProvider, token_type: TokenType) -> WebClient:
    """Get the appropriate Slack WebClient based on token type.

    Args:
        provider: The SlackProvider instance
        token_type: Either "bot" or "user"

    Returns:
        WebClient instance for the requested token type

    Raises:
        ValueError: If token_type is invalid
    """
    if token_type == "bot":
        return provider.bot_client
    elif token_type == "user":
        return provider.user_client
    else:
        raise ValueError(f"Invalid token_type: {token_type}. Must be 'bot' or 'user'.")
```

#### 2.2.3 Add `token_type` Parameter to All Tools

**Parameter definition (consistent across all tools):**

```python
token_type: Annotated[
    TokenType,
    Field(description="Token to use: 'bot' or 'user'. Different tokens have different permissions and identity.")
] = "bot",  # Default varies by tool
```

**Default values per tool:**

| Tool | Default | Position |
|------|---------|----------|
| `conversations_history` | `"bot"` | Last parameter |
| `conversations_replies` | `"bot"` | Last parameter |
| `conversations_add_message` | `"bot"` | Last parameter |
| `conversations_search_messages` | `"user"` | Last parameter |
| `channels_list` | `"bot"` | Last parameter |
| `channels_create` | `"bot"` | Last parameter |
| `channels_invite_users` | `"bot"` | Last parameter |
| `channels_remove_user` | `"bot"` | Last parameter |

#### 2.2.4 Update Tool Implementations

**Pattern for each tool:**

Replace direct client access:
```python
# Before
response = provider.client.conversations_history(...)

# After
client = get_client(provider, token_type)
response = client.conversations_history(...)
```

**Special case - `conversations_search_messages`:**

Currently checks if `user_client` exists:
```python
if not provider.user_client:
    raise ValueError("Search requires a user token...")
```

This check can be removed since both tokens are now required at startup. Replace with:
```python
client = get_client(provider, token_type)
response = client.search_messages(...)
```

#### 2.2.5 Update Tool Descriptions

**Add to each tool's docstring:**

```python
"""Get messages from a channel or DM. Returns CSV with cursor in last row for pagination.

Use `token_type` to select 'bot' (default) or 'user' token. User token may access
different channels/DMs and actions appear as the authenticated user.
"""
```

---

### 2.3 Summary of Changes by File

#### `src/slack_mcp_server/provider.py`

| Change | Lines Affected |
|--------|----------------|
| Require both tokens in `__init__` | ~63-66 |
| Rename `self.client` → `self.bot_client` | ~70 |
| Remove conditional for `user_client` | ~73-75 |
| Update `auth_test()` to use `bot_client` | ~101-107 |
| Update `refresh_users()` to use `bot_client` | ~134-176 |
| Update `_fetch_channels_by_type()` to use `bot_client` | ~265-290 |

#### `src/slack_mcp_server/server.py`

| Change | Lines Affected |
|--------|----------------|
| Add `TokenType` type alias | Near imports |
| Add `get_client()` helper | After existing helpers (~288) |
| Update `conversations_history` | ~301-358 |
| Update `conversations_replies` | ~361-430 |
| Update `conversations_add_message` | ~433-490 |
| Update `conversations_search_messages` | ~493-626 |
| Update `channels_list` | ~629-701 |
| Update `channels_create` | ~704-842 |
| Update `channels_invite_users` | ~845-918 |
| Update `channels_remove_user` | ~921-974 |

---

## 3. Impact and Risk Analysis

### System Dependencies

- **Slack API:** No changes to Slack API usage - we're just selecting which authenticated client to use
- **FastMCP:** No changes to MCP protocol - just adding a new parameter to existing tools
- **Environment variables:** Now requires both `SLACK_MCP_BOT_TOKEN` and `SLACK_MCP_USER_TOKEN`

### Potential Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Breaking change:** Users with only bot token configured will fail to start | High | Document migration in README and changelog; error message clearly states required env vars |
| **API permission mismatch:** User tries bot token for search (which requires user token scopes) | Medium | Slack API will return appropriate error; document recommended defaults |
| **Inconsistent behavior:** Some operations may behave differently with user vs bot token | Low | Document in tool descriptions that permissions and visibility may differ |

---

## 4. Testing Strategy

Testing is performed via integration tests using MCP client calls. A subagent runs test scenarios by calling the MCP server and its tools directly (see `.serena/memories/mcp-testing-guide.md`).

### Test Scenarios

**1. Server Startup - Token Validation:**
- Attempt to start server with only bot token → expect startup failure with clear error
- Attempt to start server with only user token → expect startup failure with clear error
- Start server with both tokens → expect successful initialization

**2. Tool Parameter Availability:**
- List tools via `session.list_tools()` → verify all 8 tools are present
- Inspect tool schemas → verify each tool has `token_type` parameter with `"bot"` or `"user"` options

**3. Default Token Behavior:**
- Call `conversations_history` without `token_type` → should use bot token (default)
- Call `conversations_search_messages` without `token_type` → should use user token (default)
- Call `channels_list` without `token_type` → should use bot token (default)

**4. Explicit Token Selection:**
- Call `conversations_history` with `token_type="user"` → should succeed using user token
- Call `conversations_history` with `token_type="bot"` → should succeed using bot token
- Call `conversations_search_messages` with `token_type="bot"` → should succeed (or fail with Slack API permission error, which is expected)

**5. Invalid Token Type:**
- Call any tool with `token_type="invalid"` → expect validation error

### Test Execution Pattern

```python
# Example test call with token_type parameter
result = await session.call_tool('conversations_history', {
    'channel_id': '#test-channel',
    'limit': '5',
    'token_type': 'user'  # Explicit token selection
})
```

### Success Criteria

- All tools accept `token_type` parameter
- Default behavior matches the specified defaults (bot for most, user for search)
- Explicit token selection works for all tools
- Server refuses to start without both tokens configured
