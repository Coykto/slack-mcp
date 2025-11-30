# Functional Specification: Token Selection for MCP Tools

- **Roadmap Item:** Allow users to select which token (bot or user) to use for each tool call
- **Status:** Draft
- **Author:** Claude

---

## 1. Overview and Rationale (The "Why")

### Context
The Slack MCP server currently supports two types of OAuth tokens:
- **Bot token** (`xoxb-...`): Used for most operations (channel management, posting messages, fetching history)
- **User token** (`xoxp-...`): Used only for search operations (required by Slack's search API)

The choice of which token to use is currently hardcoded per operation. Users have no control over this behavior.

### Problem
Users need flexibility in token selection for several reasons:
1. **Visibility differences:** Bot and user tokens may have access to different channels and DMs. A user might need to access a private channel the bot isn't a member of, or vice versa.
2. **Identity:** Actions performed with the bot token appear as coming from the bot, while actions with the user token appear as coming from the user. Users may need to control how their actions appear in Slack.
3. **Permission levels:** Bot and user tokens often have different OAuth scopes and permissions. Some operations may only be possible with one token type.

### Desired Outcome
Users can explicitly specify which token (bot or user) to use when calling any MCP tool, while sensible defaults are maintained for convenience.

### Success Criteria
- All tools accept an optional parameter to select the token type
- Default behavior matches the current implementation (bot token for most operations, user token for search)
- Both tokens are required at startup - the MCP server refuses to start if either is missing
- Tool descriptions clearly communicate the token selection capability

---

## 2. Functional Requirements (The "What")

### 2.1 Required Token Configuration

**As a** user starting the MCP server, **I need to** provide both bot and user tokens, **so that** all tools can use either token as needed.

**Behavior:**

1. At startup, the MCP server checks for both `SLACK_MCP_BOT_TOKEN` and `SLACK_MCP_USER_TOKEN` environment variables
2. If either token is missing, the server refuses to start and displays a clear error message indicating which token(s) are missing
3. Both tokens are validated (authenticated) at startup

**Acceptance Criteria:**

- [ ] Given both tokens are configured, when the MCP server starts, then it initializes successfully
- [ ] Given only the bot token is configured, when the MCP server attempts to start, then it fails with error: "Both bot and user tokens are required. Missing: SLACK_MCP_USER_TOKEN"
- [ ] Given only the user token is configured, when the MCP server attempts to start, then it fails with error: "Both bot and user tokens are required. Missing: SLACK_MCP_BOT_TOKEN"
- [ ] Given neither token is configured, when the MCP server attempts to start, then it fails with error: "Both bot and user tokens are required. Missing: SLACK_MCP_BOT_TOKEN, SLACK_MCP_USER_TOKEN"

---

### 2.2 Token Selection Parameter

**As a** user calling an MCP tool, **I want to** optionally specify which token to use, **so that** I can control the identity and access level of the operation.

**Parameter Definition:**

| Parameter | Required | Type | Values | Default |
|-----------|----------|------|--------|---------|
| `token_type` | No | string | `"bot"` or `"user"` | Tool-specific (see 2.3) |

**Behavior:**

1. Each tool accepts an optional `token_type` parameter
2. When `token_type` is provided, the tool uses the corresponding client (bot or user)
3. When `token_type` is omitted, the tool uses its default token (defined in 2.3)
4. Invalid values for `token_type` result in a validation error

**Acceptance Criteria:**

- [ ] Given `token_type="bot"`, when I call any tool, then the operation is performed using the bot token
- [ ] Given `token_type="user"`, when I call any tool, then the operation is performed using the user token
- [ ] Given `token_type` is omitted, when I call a tool, then the operation uses the tool's default token
- [ ] Given an invalid `token_type` value (e.g., `"admin"`), when I call a tool, then a validation error is returned: "Invalid token_type: must be 'bot' or 'user'"

---

### 2.3 Default Token Behavior

**As a** user, **I want** sensible defaults for token selection, **so that** I don't need to specify the token for common use cases.

**Default Token per Tool:**

| Tool | Default Token | Rationale |
|------|---------------|-----------|
| `conversations_history` | `bot` | Standard bot operation |
| `conversations_replies` | `bot` | Standard bot operation |
| `conversations_add_message` | `bot` | Messages appear from bot by default |
| `conversations_search_messages` | `user` | Slack search API requires user token |
| `channels_list` | `bot` | Standard bot operation |
| `channels_create` | `bot` | Channel creation typically done as bot |
| `channels_invite_users` | `bot` | Standard bot operation |
| `channels_remove_user` | `bot` | Standard bot operation |

**Acceptance Criteria:**

- [ ] Given I call `conversations_search_messages` without `token_type`, then the user token is used (matching current behavior)
- [ ] Given I call `conversations_history` without `token_type`, then the bot token is used (matching current behavior)
- [ ] Given I call any channel management tool without `token_type`, then the bot token is used

---

### 2.4 Tool Description Updates

**As a** user discovering MCP tools, **I want** tool descriptions to clearly indicate token selection capability, **so that** I understand how to use this feature.

**Behavior:**

Each tool's description must include:
1. A note about the `token_type` parameter
2. The default token for that tool
3. When using a different token might be useful

**Example Description Format:**

```
Get messages from a channel or DM. Returns CSV with cursor in last row for pagination.

Token selection: Use `token_type` parameter to choose 'bot' (default) or 'user' token.
Use 'user' to access channels/DMs the bot cannot see.
```

**Acceptance Criteria:**

- [ ] Each tool's description mentions the `token_type` parameter
- [ ] Each tool's description states its default token
- [ ] Each tool's description provides guidance on when to use the non-default token

---

### 2.5 Internal Refactoring: Rename `client` to `bot_client`

**As a** developer maintaining the codebase, **I want** consistent naming for the Slack clients, **so that** the code is clear and self-documenting.

**Change:**

- Rename the internal `client` attribute to `bot_client` in the `SlackProvider` class
- This matches the existing `user_client` naming convention

**Acceptance Criteria:**

- [ ] The `SlackProvider.client` attribute is renamed to `SlackProvider.bot_client`
- [ ] All internal references to `client` are updated to `bot_client`
- [ ] No external/public API changes (this is an internal refactoring)

---

## 3. Scope and Boundaries

### In-Scope

- Adding `token_type` parameter to all existing tools
- Requiring both tokens at startup (no opt-out)
- Updating tool descriptions to document token selection
- Renaming internal `client` to `bot_client` for consistency
- Maintaining backward-compatible default behavior

### Out-of-Scope

- Adding new tools
- Changing OAuth scope requirements
- Per-tool token configuration via environment variables
- Token refresh or rotation logic
- Support for additional token types (e.g., app-level tokens)