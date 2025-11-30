# Technical Specification: Channel Management

- **Functional Specification:** [001-channel-management/functional-spec.md](./functional-spec.md)
- **Status:** Draft
- **Author(s):** Claude

---

## 1. High-Level Technical Approach

This feature adds three new MCP tools for channel management following the existing codebase patterns:

1. **`channels_create`** - Create public/private channels with idempotent ownership detection
2. **`channels_invite_users`** - Invite one or more users to a channel
3. **`channels_remove_user`** - Remove a user from a channel

All tools will:
- Follow the existing `@mcp.tool` decorator pattern with `Annotated` parameters
- Return CSV-formatted strings consistent with other tools
- Use the existing `SlackProvider` for API calls
- Be gated behind an environment variable `SLACK_MCP_CHANNEL_MANAGEMENT`

**Files to modify:**
- `src/slack_mcp_server/server.py` - Add new tools and helper functions
- `src/slack_mcp_server/provider.py` - Add user resolution helper
- `README.md` - Document new tools and required OAuth scopes

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 New Tools in `server.py`

#### Tool 1: `channels_create`

```python
@mcp.tool
def channels_create(
    name: Annotated[str, Field(description="Channel name (lowercase, numbers, hyphens, underscores; max 80 chars)")],
    is_private: Annotated[bool, Field(description="Create as private channel")] = False,
    description: Annotated[str | None, Field(description="Channel description/purpose")] = None,
) -> str:
    """Create a new Slack channel or return existing MCP-managed channel. Returns channel info as CSV."""
```

**Logic:**
1. Validate feature is enabled via `SLACK_MCP_CHANNEL_MANAGEMENT` env var
2. Validate channel name format (lowercase, alphanumeric, hyphens, underscores, max 80 chars)
3. Check if channel exists using `provider.client.conversations_list()` with `name` parameter
4. **If channel exists:**
   - Call `conversations_info` to get `creator` and `purpose` fields
   - Get current user ID from `provider.user_id` (already available from `auth_test`)
   - Check ownership: `creator == current_user_id` AND `purpose` contains `[managed by slack-mcp]`
   - If owned → return existing channel info (idempotent)
   - If not owned → raise `ValueError("Channel '#name' already exists but is not managed by this MCP")`
5. **If channel does not exist:**
   - Call `conversations_create(name=name, is_private=is_private)`
   - Build purpose string: `"{description} [managed by slack-mcp]"` or `"[managed by slack-mcp]"`
   - Call `conversations_setPurpose(channel=id, purpose=purpose_string)`
   - Refresh channel cache: `provider.refresh_channels()`
   - Return new channel info

**Return CSV format:**
```csv
channelID,name,is_private,creator,purpose,is_new
C123ABC,project-alpha,false,U456DEF,Project discussion [managed by slack-mcp],true
```

#### Tool 2: `channels_invite_users`

```python
@mcp.tool
def channels_invite_users(
    channel_id: Annotated[str, Field(description="Channel ID or name (e.g., C1234567890 or #project-alpha)")],
    user_ids: Annotated[str, Field(description="Comma-separated user IDs or @mentions (e.g., 'U123,U456' or '@alice,@bob')")],
) -> str:
    """Invite users to a Slack channel. Returns result as CSV."""
```

**Logic:**
1. Validate feature is enabled
2. Resolve channel reference to ID using `provider.resolve_channel()`
3. Parse and resolve user references using new helper `resolve_user_list()`
4. Call `conversations_invite(channel=channel_id, users=user_id_list)`
5. Handle `already_in_channel` error gracefully (idempotent - not an error)
6. Return success CSV

**Return CSV format:**
```csv
channelID,invited_users,already_members
C123ABC,"U123,U456",U789
```

#### Tool 3: `channels_remove_user`

```python
@mcp.tool
def channels_remove_user(
    channel_id: Annotated[str, Field(description="Channel ID or name")],
    user_id: Annotated[str, Field(description="User ID or @mention to remove")],
) -> str:
    """Remove a user from a Slack channel. Returns result as CSV."""
```

**Logic:**
1. Validate feature is enabled
2. Resolve channel and user references
3. Call `conversations_kick(channel=channel_id, user=user_id)`
4. Handle `not_in_channel` error gracefully
5. Return success CSV

**Return CSV format:**
```csv
channelID,removed_user,status
C123ABC,U456,removed
```

### 2.2 Helper Functions in `server.py`

#### `is_channel_management_enabled()`

```python
def is_channel_management_enabled() -> bool:
    """Check if channel management tools are enabled."""
    value = os.environ.get("SLACK_MCP_CHANNEL_MANAGEMENT", "").lower()
    return value in ("true", "1", "yes")
```

#### `check_channel_ownership()`

```python
MCP_MARKER = "[managed by slack-mcp]"

def check_channel_ownership(provider: SlackProvider, channel_id: str) -> tuple[bool, dict]:
    """
    Check if a channel is owned by this MCP instance.

    Returns:
        (is_owned, channel_info) - is_owned is True if creator matches and MCP marker present
    """
    response = provider.client.conversations_info(channel=channel_id)
    channel = response["channel"]

    creator = channel.get("creator", "")
    purpose = channel.get("purpose", {}).get("value", "")

    is_owned = (creator == provider.user_id) and (MCP_MARKER in purpose)
    return is_owned, channel
```

#### `resolve_user_list()`

```python
def resolve_user_list(provider: SlackProvider, user_refs: str) -> list[str]:
    """
    Resolve comma-separated user references to user IDs.

    Args:
        user_refs: Comma-separated user IDs or @mentions (e.g., "U123,@alice,U456")

    Returns:
        List of resolved user IDs

    Raises:
        ValueError: If any user reference cannot be resolved
    """
    user_ids = []
    for ref in user_refs.split(","):
        ref = ref.strip()
        if not ref:
            continue
        resolved = provider.resolve_user(ref)
        if not resolved:
            raise ValueError(f"User '{ref}' not found")
        user_ids.append(resolved)
    return user_ids
```

#### `channel_info_to_csv()`

```python
def channel_info_to_csv(channel: dict, is_new: bool) -> str:
    """Convert channel info dict to CSV format."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["channelID", "name", "is_private", "creator", "purpose", "is_new"])
    writer.writerow([
        channel["id"],
        channel["name"],
        channel.get("is_private", False),
        channel.get("creator", ""),
        channel.get("purpose", {}).get("value", ""),
        is_new,
    ])
    return output.getvalue()
```

### 2.3 Provider Enhancement (`provider.py`)

Add `user_id` property to `SlackProvider` class (already captured from `auth_test`):

```python
@property
def user_id(self) -> str:
    """Return the authenticated user's ID."""
    return self._user_id  # Already set in __init__ from auth_test response
```

Verify `resolve_user()` method handles all formats (already exists at lines 193-203).

### 2.4 Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_MCP_CHANNEL_MANAGEMENT` | Enable channel management tools: `true`, `1`, or `yes` |

### 2.5 Required OAuth Scopes

Add to existing scope requirements:

| Scope | Purpose |
|-------|---------|
| `channels:manage` | Create and archive public channels |
| `groups:write` | Create and manage private channels, invite/remove users |
| `channels:read` | Read public channel info (for ownership check) |
| `groups:read` | Read private channel info (for ownership check) |

### 2.6 README Updates

Add new section documenting:
1. New tools and their parameters
2. Environment variable to enable
3. Additional OAuth scopes required
4. Examples of usage

---

## 3. Impact and Risk Analysis

### System Dependencies

| Dependency | Impact |
|------------|--------|
| Slack API | New endpoints: `conversations.create`, `conversations.info`, `conversations.invite`, `conversations.kick`, `conversations.setPurpose` |
| Provider cache | Must refresh after channel creation to include new channel |
| OAuth scopes | Users need additional scopes for channel management |

### Potential Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| User lacks required OAuth scopes | Medium | Tool fails with permission error | Clear error message indicating missing scope; document scopes in README |
| Race condition: channel created between check and create | Low | Slack returns `name_taken` error | Catch this error and re-check ownership (treat as existing channel) |
| MCP marker accidentally removed from purpose | Low | Channel appears unmanaged, cannot be reused | Document that marker should not be removed; could add secondary check via creator only with warning |
| Rate limiting on Slack API | Low | Tools fail temporarily | Existing error handling surfaces Slack errors; no special handling needed |
| Channel name validation mismatch with Slack | Low | Confusing error messages | Validate name format locally before API call with clear error message |

---

## 4. Testing Strategy

### Unit Tests

1. **`is_channel_management_enabled()`**
   - Test with `true`, `1`, `yes` (enabled)
   - Test with `false`, `0`, empty, unset (disabled)

2. **`check_channel_ownership()`**
   - Test channel owned by current user with marker → `True`
   - Test channel owned by current user without marker → `False`
   - Test channel owned by different user with marker → `False`
   - Test channel owned by different user without marker → `False`

3. **`resolve_user_list()`**
   - Test single user ID
   - Test multiple user IDs
   - Test @mention format
   - Test mixed formats
   - Test invalid user reference → raises `ValueError`

4. **Channel name validation**
   - Valid: `project-alpha`, `team_updates`, `channel123`
   - Invalid: `Project-Alpha` (uppercase), `my channel` (space), `ch@nnel` (special char), 81+ chars

### Integration Tests (Manual or Mocked)

1. **Create channel (new)**
   - Creates channel with correct name
   - Sets purpose with MCP marker
   - Returns correct CSV

2. **Create channel (idempotent)**
   - Second call returns same channel ID
   - Does not create duplicate

3. **Create channel (conflict)**
   - Channel exists but not MCP-managed → error

4. **Invite users**
   - Single user invited successfully
   - Multiple users invited successfully
   - Already-member handled gracefully

5. **Remove user**
   - User removed successfully
   - Non-member handled gracefully

### Acceptance Criteria Verification

Map each acceptance criterion from functional spec to specific test cases.