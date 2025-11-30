# Tasks: Channel Management

## Slice 1: Enable feature toggle and create minimal `channels_create` (happy path only)

The smallest end-to-end value: create a public channel when it doesn't exist.

- [x] **Slice 1: Create a new public channel (happy path)**
  - [x] Add `is_channel_management_enabled()` helper function in `server.py`
  - [x] Add `MCP_MARKER = "[managed by slack-mcp]"` constant
  - [x] Add `channel_info_to_csv()` helper function for CSV output
  - [x] Implement `channels_create` tool with basic logic:
    - Validate feature enabled
    - Validate channel name format
    - Call `conversations_create`
    - Call `conversations_setPurpose` with MCP marker
    - Refresh channel cache
    - Return CSV
  - [x] Add `SLACK_MCP_CHANNEL_MANAGEMENT` to README environment variables table

**After this slice:** Users can create new public channels via MCP.

---

## Slice 2: Add idempotent channel creation (ownership detection)

Build on Slice 1: if channel exists and is MCP-managed, return it instead of erroring.

- [x] **Slice 2: Idempotent channel creation with ownership check**
  - [x] Add `user_id` property to `SlackProvider` (if not already exposed)
  - [x] Add `check_channel_ownership()` helper function
  - [x] Update `channels_create` to:
    - Check if channel exists (via channel cache or API)
    - If exists: call `check_channel_ownership()`
    - If owned → return existing channel (idempotent)
    - If not owned → raise descriptive error
  - [x] Handle `name_taken` error from Slack API (race condition)

**After this slice:** Repeated calls to create the same channel work idempotently.

---

## Slice 3: Support private channel creation

Extend `channels_create` to support `is_private=True`.

- [x] **Slice 3: Private channel support**
  - [x] Verify `conversations_create(is_private=True)` works with existing implementation
  - [x] Document private channel behavior in README

**After this slice:** Users can create both public and private channels.

---

## Slice 4: Invite users to channel

Add the second tool for membership management.

- [x] **Slice 4: Invite users to a channel**
  - [x] Add `resolve_user_list()` helper function in `server.py`
  - [x] Implement `channels_invite_users` tool:
    - Validate feature enabled
    - Resolve channel reference
    - Resolve user references (comma-separated)
    - Call `conversations_invite`
    - Handle `already_in_channel` gracefully (idempotent)
    - Return CSV with results
  - [x] Document tool in README

**After this slice:** Users can invite members to channels via MCP.

---

## Slice 5: Remove user from channel

Add the third tool for membership management.

- [x] **Slice 5: Remove user from a channel**
  - [x] Implement `channels_remove_user` tool:
    - Validate feature enabled
    - Resolve channel and user references
    - Call `conversations_kick`
    - Handle `not_in_channel` gracefully
    - Return CSV with results
  - [x] Document tool in README

**After this slice:** Users can remove members from channels via MCP.

---

## Slice 6: Live integration testing

Use subagent to call all tools against a real Slack workspace and verify they work.

- [x] **Slice 6: Live integration testing**
  - [x] Perform end-to-end test sequence:
    1. Create a test public channel (`mcp-test-public-20251130-1`) ✅
    2. Verify channel was created with MCP marker in purpose ✅
    3. Call create again with same name → verify idempotent (returns same channel) ✅
    4. Create a test private channel (`mcp-test-private-20251130-1`) ✅
    5. Invite @ebasmov to the public channel ✅
    6. Invite @ebasmov again → verify idempotent (no error) ✅
    7. Remove @ebasmov from the channel ✅
    8. Remove @ebasmov again → verify graceful handling ✅
    9. Attempt to create `#general` (not MCP-managed) → verify error ✅
  - [x] Document any issues found and fix them:
    - Fixed: `refresh_channels()` was loading from cache instead of API after channel creation
    - Added `force=True` parameter to `refresh_channels()` in `provider.py`
    - Added `SLACK_MCP_BOT_TOKEN` env var support in `cli.py` (bot tokens have `channels:manage` scope)

**After this slice:** All tools verified working against real Slack API.

---

## Slice 7: Complete documentation

Finalize documentation.

- [x] **Slice 7: Complete documentation**
  - [x] Add new OAuth scopes to README (`channels:manage`, `groups:write`, `channels:read`, `groups:read`)
  - [x] Add usage examples for all three new tools
  - [x] Document the `[managed by slack-mcp]` marker behavior
  - [x] Document bot token vs user token authentication (SLACK_MCP_BOT_TOKEN, SLACK_MCP_USER_TOKEN)

**After this slice:** Feature is fully documented and ready for users.

---

## ✅ Feature Complete

All 7 slices have been implemented and tested. The Channel Management feature is ready for use.
