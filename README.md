# Slack MCP Server (Python)

A powerful MCP server for Slack workspaces - supports DMs, Group DMs, smart history fetch, and works via OAuth or browser tokens.

This is a Python/FastMCP rewrite of the original Go-based [slack-mcp-server](https://github.com/korotovsky/slack-mcp-server).

## Features

- **8 Tools**: conversations_history, conversations_replies, conversations_add_message, conversations_search_messages, channels_list, channels_create, channels_invite_users, channels_remove_user
- **2 Resources**: slack://{workspace}/channels, slack://{workspace}/users
- **Authentication**: Bot OAuth tokens (xoxb) for most operations, User OAuth tokens (xoxp) for search
- **Smart Caching**: Users and channels cached locally for fast lookups
- **CSV Output**: All responses in CSV format for easy parsing

## Installation

### Using uvx (recommended for Claude Code)

```bash
uvx --from git+https://github.com/korotovsky/slack-mcp-server/python_version slack-mcp-server \
    --bot-token xoxb-your-bot-token
```

### Using pip

```bash
pip install git+https://github.com/korotovsky/slack-mcp-server.git#subdirectory=python_version
```

### Development

```bash
cd python_version
pip install -e ".[dev]"
pre-commit install
```

## Claude Code Configuration

Add to your Claude Code MCP settings:

**With Bot Token (recommended for most operations):**

```json
{
  "slack-mcp": {
    "type": "stdio",
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/korotovsky/slack-mcp-server/python_version",
      "slack-mcp-server",
      "--bot-token",
      "xoxb-your-bot-token-here"
    ]
  }
}
```

**With Both Bot and User Tokens (for search functionality):**

```json
{
  "slack-mcp": {
    "type": "stdio",
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/korotovsky/slack-mcp-server/python_version",
      "slack-mcp-server",
      "--bot-token",
      "xoxb-your-bot-token-here",
      "--user-token",
      "xoxp-your-user-token-here"
    ]
  }
}
```

**Or with browser tokens:**

```json
{
  "slack-mcp": {
    "type": "stdio",
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/korotovsky/slack-mcp-server/python_version",
      "slack-mcp-server",
      "--xoxc-token",
      "xoxc-your-token",
      "--xoxd-token",
      "xoxd-your-cookie"
    ]
  }
}
```

## Authentication

The server supports two types of OAuth tokens, each with distinct purposes:

### Bot Token (xoxb) - Required
Bot OAuth tokens are used for most operations and are required for the server to function.

**Token Format:** `xoxb-...`

**Required Scopes:**
- `channels:manage` - Create public channels
- `groups:write` - Create private channels, invite/remove users
- `channels:read` - Read public channel info
- `groups:read` - Read private channel info
- `channels:history` - Read public channel message history
- `groups:history` - Read private channel message history
- `im:history` - Read DM history
- `mpim:history` - Read group DM history
- `users:read` - Read user information
- `chat:write` - Post messages

**How to get a Bot Token:**
1. Create a Slack app at https://api.slack.com/apps
2. Navigate to "OAuth & Permissions"
3. Add the required bot token scopes listed above
4. Install the app to your workspace
5. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

### User Token (xoxp) - Optional
User OAuth tokens are only required for search operations. Bot tokens cannot be used with the `search.messages` API.

**Token Format:** `xoxp-...`

**Required Scopes:**
- `search:read` - Search messages (required for `conversations_search_messages`)

**How to get a User Token:**
1. In your Slack app settings, navigate to "OAuth & Permissions"
2. Add the `search:read` user token scope
3. Reinstall the app to your workspace
4. Copy the "User OAuth Token" (starts with `xoxp-`)

**Note:** If you don't need search functionality, you can omit the user token.

### Browser Tokens (xoxc/xoxd) - Alternative
Extract from browser for "stealth mode":
1. Open Slack in browser, open DevTools
2. Find `xoxc-` token in localStorage or network requests
3. Find `d=xoxd-...` in cookies

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_MCP_BOT_TOKEN` | Bot OAuth token (xoxb-...) - required for most operations |
| `SLACK_MCP_USER_TOKEN` | User OAuth token (xoxp-...) - optional, for search operations |
| `SLACK_MCP_XOXC_TOKEN` | Browser token (alternative authentication) |
| `SLACK_MCP_XOXD_TOKEN` | Browser cookie (alternative authentication) |
| `SLACK_MCP_ADD_MESSAGE_TOOL` | Enable posting: `true`, `1`, or channel list |
| `SLACK_MCP_ADD_MESSAGE_MARK` | Mark as read after posting |
| `SLACK_MCP_ADD_MESSAGE_UNFURLING` | Link unfurling: `yes` or domain list |
| `SLACK_MCP_CHANNEL_MANAGEMENT` | Enable channel management tools: `true`, `1`, or `yes` |
| `SLACK_MCP_USERS_CACHE` | Custom users cache path |
| `SLACK_MCP_CHANNELS_CACHE` | Custom channels cache path |
| `SLACK_MCP_LOG_LEVEL` | Log level (debug/info/warning/error) |

## Tools

### conversations_history
Get messages from a channel or DM.

```
channel_id: Channel ID (Cxxxxxxxxxx) or name (#general, @username)
include_activity_messages: Include join/leave messages (default: false)
cursor: Pagination cursor
limit: '1d', '1w', '30d', '90d' or number like '50'
```

### conversations_replies
Get thread replies.

```
channel_id: Channel ID or name
thread_ts: Thread timestamp (1234567890.123456)
include_activity_messages: Include activity messages
cursor: Pagination cursor
limit: Time range or number
```

### conversations_add_message
Post a message (disabled by default, set SLACK_MCP_ADD_MESSAGE_TOOL to enable).

```
channel_id: Channel ID or name
payload: Message text
thread_ts: Optional thread to reply to
content_type: 'text/markdown' or 'text/plain'
```

### conversations_search_messages
Search messages with filters.

```
search_query: Search text or Slack message URL
filter_in_channel: Filter by channel
filter_in_im_or_mpim: Filter by DM
filter_users_with: Filter threads with user
filter_users_from: Filter messages from user
filter_date_before/after/on/during: Date filters
filter_threads_only: Only thread messages
cursor: Pagination cursor
limit: Max results (1-100)
```

### channels_list
Get list of channels.

```
channel_types: Comma-separated: 'mpim', 'im', 'public_channel', 'private_channel'
sort: 'popularity' to sort by member count
limit: Max results (1-999)
cursor: Pagination cursor
```

### channels_create
Create a new Slack channel (requires `SLACK_MCP_CHANNEL_MANAGEMENT=true`).

**Parameters:**
```
name: Channel name (lowercase, numbers, hyphens, underscores; max 80 chars)
is_private: Create as private channel (default: false)
description: Channel description/purpose
```

**Usage Examples:**
```python
# Create a public channel
channels_create(name="project-alpha", description="Main project discussion")

# Create a private channel for team leads
channels_create(name="team-leads", is_private=true, description="Leadership discussions")
```

**Important Behaviors:**

**Idempotent Creation:** All channels created by this tool are marked with `[managed by slack-mcp]` in their purpose field. If you call `channels_create` with a name that already exists:
- If the channel was created by this MCP instance (has the marker), it returns the existing channel
- If the channel exists but was NOT created by this MCP, an error is returned

This ensures safe, idempotent channel creation while preventing accidental modification of existing channels not managed by this tool.

**Required Scopes:**
- Public channels: `channels:manage` bot token scope
- Private channels: `groups:write` bot token scope

### channels_invite_users
Invite users to a Slack channel (requires `SLACK_MCP_CHANNEL_MANAGEMENT=true`).

**Parameters:**
```
channel_id: Channel ID or name (e.g., C1234567890 or #project-alpha)
user_ids: Comma-separated user IDs or @mentions (e.g., 'U123,U456' or '@alice,@bob')
```

**Usage Examples:**
```python
# Invite users by @mention
channels_invite_users(channel_id="#project-alpha", user_ids="@alice,@bob")

# Invite users by ID
channels_invite_users(channel_id="C1234567890", user_ids="U123456,U789012")

# Mix of @mentions and IDs
channels_invite_users(channel_id="#project-alpha", user_ids="@alice,U789012")
```

**Important Behaviors:**
- Users already in the channel are silently skipped (idempotent behavior)
- Supports both user IDs (U...) and @mentions for convenience
- Requires `groups:write` bot token scope

### channels_remove_user
Remove a user from a Slack channel (requires `SLACK_MCP_CHANNEL_MANAGEMENT=true`).

**Parameters:**
```
channel_id: Channel ID or name (e.g., C1234567890 or #project-alpha)
user_id: User ID or @mention to remove (e.g., 'U123' or '@alice')
```

**Usage Examples:**
```python
# Remove user by @mention
channels_remove_user(channel_id="#project-alpha", user_id="@alice")

# Remove user by ID
channels_remove_user(channel_id="C1234567890", user_id="U123456")
```

**Important Behaviors:**
- Removing a user who is not in the channel returns a `not_in_channel` status (not an error)
- Supports both user IDs (U...) and @mentions for convenience
- Requires `groups:write` bot token scope

## Resources

- `slack://{workspace}/channels` - CSV directory of all channels
- `slack://{workspace}/users` - CSV directory of all users

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run linting
ruff check .
ruff format .
```

## License

MIT
