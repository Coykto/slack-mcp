# Slack MCP Server Testing Guide

**Purpose:** Instructions for testing this MCP server via actual MCP tool calls using a subagent.

## Environment Setup

**For Main Agent - Before Running Tests:**
```bash
# Read the token from user's shell:
echo "SLACK_API_TOKEN=$SLACK_API_TOKEN"
```

Then pass the value explicitly to the subagent prompt (never store tokens in memory files).

## Subagent Testing Approach

1. Run tools via MCP client SDK using `uv run python -c "..."` with inline code
2. Do NOT create test files - just run commands and observe output
3. Call actual MCP tools (not Python classes) to test full integration
4. Compile report from outputs at the end

## MCP Client Test Pattern

```bash
uv run python -c "
import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test():
    server_params = StdioServerParameters(
        command='uv',
        args=['run', '--directory', '/Users/eb/PycharmProjects/slack-mcp', 'slack-mcp-server',
              '--xoxp-token', '<SLACK_API_TOKEN>']
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            print(f'Available tools: {[t.name for t in tools.tools]}')

            # Call MCP tool
            result = await session.call_tool('channels_list', {'channel_types': 'public_channel', 'limit': 5})
            print(f'channels_list result: {result.content[0].text[:500]}...')

asyncio.run(test())
"
```

## Available Tools

### 1. channels_list
Lists channels by type.
```python
result = await session.call_tool('channels_list', {
    'channel_types': 'public_channel',  # or 'private_channel', 'im', 'mpim'
    'sort': 'popularity',  # optional
    'limit': 10
})
```

### 2. conversations_history
Gets messages from a channel or DM.
```python
result = await session.call_tool('conversations_history', {
    'channel_id': '#general',  # or 'Cxxxxxxxxxx' or '@username'
    'limit': '1d'  # or '1w', '30d', or numeric like '50'
})
```

### 3. conversations_replies
Gets thread replies.
```python
result = await session.call_tool('conversations_replies', {
    'channel_id': '#general',
    'thread_ts': '1234567890.123456',  # from a message with replies
    'limit': '1d'
})
```

### 4. conversations_search_messages
Searches messages with filters.
```python
result = await session.call_tool('conversations_search_messages', {
    'search_query': 'project update',
    'filter_in_channel': '#general',  # optional
    'filter_date_after': '2024-01-01',  # optional
    'limit': 10
})
```

### 5. conversations_add_message
Posts a message (disabled by default).
```python
# Only works if SLACK_MCP_ADD_MESSAGE_TOOL env is set
result = await session.call_tool('conversations_add_message', {
    'channel_id': '#test-channel',
    'payload': 'Hello from MCP test!',
    'thread_ts': '1234567890.123456'  # optional, for replies
})
```

## Available Resources

```python
# List resources
resources = await session.list_resources()
print([r.uri for r in resources.resources])

# Read channels directory
result = await session.read_resource('slack://workspace/channels')

# Read users directory  
result = await session.read_resource('slack://workspace/users')
```

## Quick Verification Script

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_all():
    server_params = StdioServerParameters(
        command='uv',
        args=['run', '--directory', '/Users/eb/PycharmProjects/slack-mcp', 'slack-mcp-server',
              '--xoxp-token', '<SLACK_API_TOKEN>']
    )

    results = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List tools
            tools = await session.list_tools()
            results.append(f"Tools: {[t.name for t in tools.tools]}")

            # 2. channels_list
            try:
                result = await session.call_tool('channels_list', {
                    'channel_types': 'public_channel',
                    'limit': 5
                })
                results.append(f"channels_list: PASS ({len(result.content[0].text)} chars)")
            except Exception as e:
                results.append(f"channels_list: FAIL - {e}")

            # 3. conversations_history (adjust channel name)
            try:
                result = await session.call_tool('conversations_history', {
                    'channel_id': '#general',
                    'limit': '5'
                })
                results.append(f"conversations_history: PASS ({len(result.content[0].text)} chars)")
            except Exception as e:
                results.append(f"conversations_history: FAIL - {e}")

            # 4. conversations_search_messages
            try:
                result = await session.call_tool('conversations_search_messages', {
                    'search_query': 'test',
                    'limit': 5
                })
                results.append(f"conversations_search_messages: PASS ({len(result.content[0].text)} chars)")
            except Exception as e:
                results.append(f"conversations_search_messages: FAIL - {e}")

            # 5. List resources
            try:
                resources = await session.list_resources()
                results.append(f"Resources: {[str(r.uri) for r in resources.resources]}")
            except Exception as e:
                results.append(f"list_resources: FAIL - {e}")

    print("\\n".join(results))

asyncio.run(test_all())
```

## Error Handling

When a test fails, capture and report:
1. The exact error message or exception
2. The raw output/response from the tool call
3. The command that was run (for reproduction)

```python
try:
    result = await session.call_tool('tool_name', params)
    data = result.content[0].text
    print(f'tool_name: PASS - {len(data)} chars')
except Exception as e:
    print(f'tool_name: FAIL - {type(e).__name__}: {e}')
```

## Subagent Prompt Template

When delegating testing to a subagent, use this template:

```
You are testing the Slack MCP server. 

**Environment:**
- Project directory: /Users/eb/PycharmProjects/slack-mcp
- Slack token: <VALUE_FROM_ECHO_COMMAND>

**Task:**
Run the MCP client test pattern to verify all tools work correctly.
Use `uv run python -c "..."` with inline code - do NOT create test files.

**Required Tests:**
1. List available tools
2. Test channels_list with public_channel type
3. Test conversations_history on a channel
4. Test conversations_search_messages with a query
5. List and read resources

**Report Format:**
For each test, report:
- Tool name
- PASS/FAIL
- Output size or error message
- Any unexpected behavior
```

## When to Update This File

- **Adding new tools**: Add test cases for the new tool
- **Modifying tool parameters**: Update test cases to reflect changes
- **Finding good test data**: Update example channel names/IDs
- **Fixing bugs**: Add test case that covers the bug scenario
