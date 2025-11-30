# Task List: Token Selection for MCP Tools

**Functional Spec:** `context/spec/002-token-selection/functional-spec.md`
**Technical Spec:** `context/spec/002-token-selection/technical-considerations.md`

---

## Slice 1: Require both tokens at startup (Breaking Change)

This slice ensures the server won't start without both tokens, establishing the foundation for token selection.

- [x] **Slice 1: Require both tokens at startup**
  - [x] Update `SlackProvider.__init__` to validate both `bot_token` and `user_token` are provided
  - [x] Update error message to list which token(s) are missing
  - [x] Make `user_client` non-optional (always initialized when user_token provided)
  - [x] Test: Verify server fails to start with only bot token
  - [x] Test: Verify server fails to start with only user token
  - [x] Test: Verify server starts successfully with both tokens

---

## Slice 2: Rename `client` to `bot_client` (Internal Refactoring)

This slice improves code clarity by using consistent naming.

- [x] **Slice 2: Rename `client` to `bot_client`**
  - [x] Rename `self.client` to `self.bot_client` in `SlackProvider.__init__`
  - [x] Update `SlackProvider.auth_test()` to use `bot_client`
  - [x] Update `SlackProvider.refresh_users()` to use `bot_client`
  - [x] Update `SlackProvider._fetch_channels_by_type()` to use `bot_client`
  - [x] Update all tool implementations in `server.py` to use `provider.bot_client`
  - [x] Test: Verify all existing functionality still works

---

## Slice 3: Add `token_type` parameter infrastructure

This slice adds the type definition and helper function without changing tool signatures yet.

- [x] **Slice 3: Add token selection infrastructure**
  - [x] Add `TokenType = Literal["bot", "user"]` type alias in `server.py`
  - [x] Add `get_client(provider, token_type)` helper function
  - [x] Test: Verify helper returns correct client for each token type

---

## Slice 4: Add `token_type` to read-only tools

This slice enables token selection for tools that read data, with minimal risk.

- [x] **Slice 4: Add `token_type` to read-only tools**
  - [x] Add `token_type` parameter to `conversations_history` (default: `"bot"`)
  - [x] Add `token_type` parameter to `conversations_replies` (default: `"bot"`)
  - [x] Add `token_type` parameter to `channels_list` (default: `"bot"`)
  - [x] Update each tool to use `get_client(provider, token_type)`
  - [x] Update docstrings to mention token selection
  - [x] Test: Verify default behavior unchanged
  - [x] Test: Verify explicit `token_type="user"` works

---

## Slice 5: Add `token_type` to search tool

This slice updates the search tool which already defaults to user token.

- [x] **Slice 5: Add `token_type` to search tool**
  - [x] Add `token_type` parameter to `conversations_search_messages` (default: `"user"`)
  - [x] Remove the manual `user_client` check (now guaranteed at startup)
  - [x] Update to use `get_client(provider, token_type)`
  - [x] Update docstring to mention token selection
  - [x] Test: Verify search still works with default (user token)
  - [x] Test: Verify explicit `token_type="bot"` is accepted

---

## Slice 6: Add `token_type` to write tools

This slice enables token selection for tools that modify data.

- [x] **Slice 6: Add `token_type` to write tools**
  - [x] Add `token_type` parameter to `conversations_add_message` (default: `"bot"`)
  - [x] Add `token_type` parameter to `channels_create` (default: `"bot"`)
  - [x] Add `token_type` parameter to `channels_invite_users` (default: `"bot"`)
  - [x] Add `token_type` parameter to `channels_remove_user` (default: `"bot"`)
  - [x] Update each tool to use `get_client(provider, token_type)`
  - [x] Update docstrings to mention token selection
  - [x] Test: Verify default behavior unchanged
  - [x] Test: Verify explicit `token_type="user"` works
