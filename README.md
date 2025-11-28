# Slack MCP Server (Python)

A powerful MCP server for Slack workspaces - supports DMs, Group DMs, smart history fetch, and works via OAuth or browser tokens.

This is a Python/FastMCP rewrite of the original Go-based [slack-mcp-server](https://github.com/korotovsky/slack-mcp-server).

## Features

- **5 Tools**: conversations_history, conversations_replies, conversations_add_message, conversations_search_messages, channels_list
- **2 Resources**: slack://{workspace}/channels, slack://{workspace}/users
- **Authentication**: OAuth tokens (xoxp) or browser tokens (xoxc/xoxd)
- **Smart Caching**: Users and channels cached locally for fast lookups
- **CSV Output**: All responses in CSV format for easy parsing

## Installation

### Using uvx (recommended for Claude Code)

```bash
uvx --from git+https://github.com/korotovsky/slack-mcp-server/python_version slack-mcp-server \
    --xoxp-token xoxp-your-token
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

```json
{
  "slack-mcp": {
    "type": "stdio",
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/korotovsky/slack-mcp-server/python_version",
      "slack-mcp-server",
      "--xoxp-token",
      "xoxp-your-token-here"
    ]
  }
}
```

Or with browser tokens:

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

### OAuth Token (xoxp)
Get a User OAuth token from your Slack app settings. Required scopes:
- `channels:history`, `channels:read`
- `groups:history`, `groups:read`
- `im:history`, `im:read`
- `mpim:history`, `mpim:read`
- `users:read`
- `search:read`
- `chat:write` (for add_message)

### Browser Tokens (xoxc/xoxd)
Extract from browser for "stealth mode":
1. Open Slack in browser, open DevTools
2. Find `xoxc-` token in localStorage or network requests
3. Find `d=xoxd-...` in cookies

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_MCP_XOXP_TOKEN` | User OAuth token |
| `SLACK_MCP_XOXC_TOKEN` | Browser token |
| `SLACK_MCP_XOXD_TOKEN` | Browser cookie |
| `SLACK_MCP_ADD_MESSAGE_TOOL` | Enable posting: `true`, `1`, or channel list |
| `SLACK_MCP_ADD_MESSAGE_MARK` | Mark as read after posting |
| `SLACK_MCP_ADD_MESSAGE_UNFURLING` | Link unfurling: `yes` or domain list |
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
