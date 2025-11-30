# Functional Specification: Channel Management

- **Roadmap Item:** Create channels and manage membership via MCP
- **Status:** Draft
- **Author:** Claude

---

## 1. Overview and Rationale (The "Why")

### Context
The Slack MCP server currently provides read-only operations (fetching messages, searching, listing channels). Developers using Claude Code need to programmatically set up Slack channels as part of their workflows without switching context to the Slack UI.

### Problem
When working on projects that require Slack channel setup, developers must manually:
1. Switch to Slack to create channels
2. Invite the right team members
3. Remember which channels they've already created across sessions

This breaks workflow and creates friction, especially when the same channel setup is needed repeatedly.

### Desired Outcome
Developers can create and manage Slack channels directly through the MCP, with intelligent handling of previously-created channels to enable idempotent operations across sessions.

### Success Criteria
- Channels can be created without leaving the development environment
- Repeated requests to create the same channel don't fail or create duplicates
- Channel membership can be managed programmatically

---

## 2. Functional Requirements (The "What")

### 2.1 Create Channel

**As a** developer using Claude Code, **I want to** create a Slack channel through the MCP, **so that** I can set up project communication without leaving my development environment.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Channel name (lowercase, numbers, hyphens, underscores; max 80 chars) |
| `is_private` | No | Whether to create a private channel (default: `false` = public) |
| `description` | No | Channel description/purpose |

**Ownership Marker:**

All channels created by this MCP include `[managed by slack-mcp]` in the channel description. This marker, combined with the `creator` field, is used to identify MCP-managed channels.

**Behavior:**

1. Normalize the channel name (lowercase, validate format)
2. Check if a channel with this name already exists in the workspace
3. **If channel exists:**
   - Fetch channel info including `creator` and `purpose` fields
   - If `creator` matches the current authenticated user **AND** description contains `[managed by slack-mcp]` → silently return the existing channel ID
   - Otherwise → return error: "Channel '#name' already exists but is not managed by this MCP"
4. **If channel does not exist:**
   - Create the channel with specified parameters
   - Automatically append `[managed by slack-mcp]` to the description
   - Return the new channel ID

**Acceptance Criteria:**

- [ ] Given a valid channel name that doesn't exist, when I call create channel, then a new channel is created and its ID is returned
- [ ] Given a valid channel name that I previously created via MCP, when I call create channel again, then the existing channel ID is returned silently (idempotent)
- [ ] Given a channel name that exists but was created by someone else, when I call create channel, then an error is returned stating the channel is not managed by this MCP
- [ ] Given a channel name that exists and was created by the same user but without the MCP marker, when I call create channel, then an error is returned (user-created channel, not MCP-managed)
- [ ] Given an invalid channel name (uppercase, special chars, >80 chars), when I call create channel, then a validation error is returned
- [ ] Given `is_private=true`, when I call create channel, then a private channel is created
- [ ] When a channel is created, then the description includes `[managed by slack-mcp]`
- [ ] Given a user-provided description "Project discussion", when the channel is created, then the stored description is "Project discussion [managed by slack-mcp]"

---

### 2.2 Invite Users to Channel

**As a** developer, **I want to** add users to a channel, **so that** I can set up the right team members programmatically.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `channel_id` | Yes | Channel ID or name (e.g., `C1234567890` or `#project-alpha`) |
| `user_ids` | Yes | One or more user IDs to invite (supports 1-1000 users) |

**Behavior:**

1. Resolve channel name to ID if necessary
2. Invite the specified users to the channel
3. Return success/failure status

**Acceptance Criteria:**

- [ ] Given a valid channel and user ID, when I call invite, then the user is added to the channel
- [ ] Given multiple user IDs, when I call invite, then all users are added in a single operation
- [ ] Given an invalid channel ID, when I call invite, then an appropriate error is returned
- [ ] Given a user who is already a member, when I call invite, then the operation succeeds without error (idempotent)

---

### 2.3 Remove User from Channel

**As a** developer, **I want to** remove users from a channel, **so that** I can manage channel membership programmatically.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `channel_id` | Yes | Channel ID or name |
| `user_id` | Yes | User ID to remove |

**Behavior:**

1. Resolve channel name to ID if necessary
2. Remove the specified user from the channel
3. Return success/failure status

**Acceptance Criteria:**

- [ ] Given a valid channel and user ID, when I call remove, then the user is removed from the channel
- [ ] Given a user who is not a member, when I call remove, then an appropriate error or warning is returned
- [ ] Given an invalid channel or user ID, when I call remove, then an appropriate error is returned

---

## 3. Scope and Boundaries

### In-Scope

- Creating public channels
- Creating private channels
- Inviting users to channels (1-1000 users per call)
- Removing users from channels
- Idempotent channel creation based on ownership detection (creator + MCP marker)

### Out-of-Scope

- Converting channels between public and private (requires Enterprise Grid - not available for standard workspaces)
- Deleting channels (not supported by Slack API)
- Archiving/unarchiving channels
- Renaming channels
- Updating channel topic/purpose after creation