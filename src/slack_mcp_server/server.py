"""FastMCP server for Slack with tools and resources."""

import base64
import csv
import io
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from pydantic import Field
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .provider import SlackProvider
from .text_utils import attachments_to_csv_suffix, is_unfurling_enabled, process_text, timestamp_to_iso

TokenType = Literal["bot", "user"]

logger = logging.getLogger(__name__)

# Global provider instance (set by CLI)
_provider: SlackProvider | None = None


def get_provider() -> SlackProvider:
    """Get the global Slack provider instance."""
    if _provider is None:
        raise RuntimeError("Slack provider not initialized. Call init_provider() first.")
    return _provider


def init_provider(
    bot_token: str | None = None,
    user_token: str | None = None,
    users_cache_path: str | None = None,
    channels_cache_path: str | None = None,
) -> SlackProvider:
    """Initialize the global Slack provider."""
    global _provider
    _provider = SlackProvider(
        bot_token=bot_token,
        user_token=user_token,
        users_cache_path=users_cache_path,
        channels_cache_path=channels_cache_path,
    )
    return _provider


# Create FastMCP server
mcp = FastMCP(
    name="Slack MCP Server",
    version="1.0.0",
)


# ---------- Constants ----------

MCP_MARKER = "[managed by slack-mcp]"


# ---------- Helper Functions ----------


def is_channel_management_enabled() -> bool:
    """Check if channel management is enabled via environment variable."""
    config = os.environ.get("SLACK_MCP_CHANNEL_MANAGEMENT", "")
    return config.lower() in ("true", "1", "yes")


def messages_to_csv(messages: list[dict[str, Any]]) -> str:
    """Convert messages to CSV format."""
    if not messages:
        return ""

    output = io.StringIO()
    fieldnames = ["msgID", "userID", "userName", "realName", "channelID", "ThreadTs", "text", "time", "reactions", "cursor"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(messages)
    return output.getvalue()


def channels_to_csv(channels: list[dict[str, Any]]) -> str:
    """Convert channels to CSV format."""
    if not channels:
        return ""

    output = io.StringIO()
    fieldnames = ["id", "name", "topic", "purpose", "memberCount", "cursor"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(channels)
    return output.getvalue()


def users_to_csv(users: list[dict[str, Any]]) -> str:
    """Convert users to CSV format."""
    if not users:
        return ""

    output = io.StringIO()
    fieldnames = ["userID", "userName", "realName"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(users)
    return output.getvalue()


def channel_info_to_csv(channel_info: dict[str, Any]) -> str:
    """Convert channel info dict to CSV format.

    Args:
        channel_info: Channel information dict with keys:
            channelID, name, is_private, creator, purpose, is_new

    Returns:
        CSV formatted string with channel information.
    """
    output = io.StringIO()
    fieldnames = ["channelID", "name", "is_private", "creator", "purpose", "is_new"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(channel_info)
    return output.getvalue()


def parse_limit_expression(limit: str) -> tuple[int, str | None, str | None]:
    """Parse a limit expression like '1d', '1w', '30d' or a number.

    Returns:
        Tuple of (limit_count, oldest_ts, latest_ts)
    """
    if not limit:
        limit = "1d"

    # Check if numeric
    if limit.isdigit():
        return int(limit), None, None

    # Parse duration expression
    match = re.match(r"^(\d+)([dwm])$", limit.lower())
    if not match:
        raise ValueError(f"Invalid limit format: {limit}. Use '1d', '1w', '30d', or a number.")

    num = int(match.group(1))
    unit = match.group(2)

    now = datetime.now(timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if unit == "d":
        oldest = start_of_today - timedelta(days=num - 1)
    elif unit == "w":
        oldest = start_of_today - timedelta(weeks=num) + timedelta(days=1)
    elif unit == "m":
        # Approximate months
        oldest = start_of_today - timedelta(days=num * 30)
    else:
        raise ValueError(f"Invalid duration unit: {unit}")

    oldest_ts = f"{int(oldest.timestamp())}.000000"
    latest_ts = f"{int(now.timestamp())}.000000"

    return 100, oldest_ts, latest_ts


def convert_slack_message(msg: dict[str, Any], channel_id: str, provider: SlackProvider) -> dict[str, Any]:
    """Convert a Slack message to our output format."""
    user_id = msg.get("user", "")
    user = provider.get_user(user_id)
    user_name = user.name if user else user_id
    real_name = user.real_name if user else user_id

    # Handle bot messages
    if msg.get("subtype") == "bot_message" and not user:
        user_name = msg.get("username", user_id)
        real_name = user_name

    # Convert timestamp
    try:
        time_str = timestamp_to_iso(msg.get("timestamp", msg.get("ts", "")))
    except ValueError:
        time_str = ""

    # Process text with attachments
    text = msg.get("text", "")
    text += attachments_to_csv_suffix(text, msg.get("attachments", []))
    text = process_text(text)

    # Format reactions
    reactions = []
    for r in msg.get("reactions", []):
        reactions.append(f"{r['name']}:{r['count']}")
    reactions_str = "|".join(reactions)

    return {
        "msgID": msg.get("ts", ""),
        "userID": user_id,
        "userName": user_name,
        "realName": real_name,
        "channelID": channel_id,
        "ThreadTs": msg.get("thread_ts", ""),
        "text": text,
        "time": time_str,
        "reactions": reactions_str,
        "cursor": "",
    }


def is_channel_allowed(channel_id: str) -> bool:
    """Check if posting to a channel is allowed based on config."""
    config = os.environ.get("SLACK_MCP_ADD_MESSAGE_TOOL", "")
    if not config or config in ("true", "1"):
        return True

    items = [item.strip() for item in config.split(",") if item.strip()]
    if not items:
        return True

    # Check if using negation pattern
    is_negated = items[0].startswith("!")

    for item in items:
        if is_negated:
            if item.lstrip("!") == channel_id:
                return False
        else:
            if item == channel_id:
                return True

    return is_negated  # Allow if negation pattern and not in blocklist


def check_channel_ownership(provider: SlackProvider, client: WebClient, channel_id: str) -> tuple[bool, dict[str, Any]]:
    """Check if a channel is owned by this MCP instance.

    A channel is considered owned if:
    1. The creator field matches the current authenticated user, AND
    2. The channel purpose/description contains the MCP marker

    Args:
        provider: The Slack provider instance
        client: The Slack WebClient to use for API calls
        channel_id: The channel ID to check

    Returns:
        Tuple of (is_owned, channel_info):
            - is_owned: True if channel is MCP-managed by current user
            - channel_info: Full channel info from Slack API
    """
    try:
        response = client.conversations_info(channel=channel_id)
        channel = response["channel"]

        creator = channel.get("creator", "")
        purpose = channel.get("purpose", {}).get("value", "")

        is_owned = (creator == provider.user_id) and (MCP_MARKER in purpose)
        return is_owned, channel

    except SlackApiError as e:
        logger.error(f"Failed to check channel ownership for {channel_id}: {e}")
        raise RuntimeError(f"Failed to check channel ownership: {e.response.get('error', 'unknown_error')}") from e


def resolve_user_list(provider: SlackProvider, user_refs: str) -> list[str]:
    """Resolve comma-separated user references to user IDs.

    Args:
        provider: The Slack provider instance
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


# ---------- Conversation Tools ----------


@mcp.tool
def conversations_history(
    channel_id: Annotated[str, Field(description="ID of the channel (Cxxxxxxxxxx) or name (#general, @username)")],
    include_activity_messages: Annotated[
        bool, Field(description="Include activity messages like channel_join")
    ] = False,
    cursor: Annotated[str | None, Field(description="Cursor for pagination")] = None,
    limit: Annotated[
        str, Field(description="Limit: '1d', '1w', '30d', '90d' for time range, or number like '50'")
    ] = "1d",
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'bot' (default) or 'user'. Different tokens have different permissions.")
    ] = "bot",
) -> str:
    """Get messages from a channel or DM. Returns CSV with cursor in last row for pagination.

    Use `token_type` to select 'bot' (default) or 'user' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    # Resolve channel reference to ID
    resolved_channel = provider.resolve_channel(channel_id)
    if not resolved_channel:
        ready, err = provider.is_ready()
        if not ready:
            raise ValueError(f"Channel '{channel_id}' not found. Cache status: {err}")
        raise ValueError(f"Channel '{channel_id}' not found in cache.")

    # Parse limit
    limit_count, oldest, latest = parse_limit_expression(limit if not cursor else "")

    try:
        params = {
            "channel": resolved_channel,
            "limit": limit_count,
            "inclusive": False,
        }
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest
        if cursor:
            params["cursor"] = cursor

        response = client.conversations_history(**params)
        slack_messages = response.get("messages", [])

        # Filter activity messages if needed
        messages = []
        for msg in slack_messages:
            subtype = msg.get("subtype", "")
            if subtype and subtype != "bot_message" and not include_activity_messages:
                continue
            messages.append(convert_slack_message(msg, resolved_channel, provider))

        # Add pagination cursor to last message
        if messages and response.get("has_more"):
            next_cursor = response.get("response_metadata", {}).get("next_cursor", "")
            messages[-1]["cursor"] = next_cursor

        return messages_to_csv(messages)

    except SlackApiError as e:
        raise RuntimeError(f"Slack API error: {e.response['error']}") from e


@mcp.tool
def conversations_replies(
    channel_id: Annotated[str, Field(description="ID of the channel (Cxxxxxxxxxx) or name (#general, @username)")],
    thread_ts: Annotated[str, Field(description="Thread timestamp (1234567890.123456)")],
    include_activity_messages: Annotated[
        bool, Field(description="Include activity messages like channel_join")
    ] = False,
    cursor: Annotated[str | None, Field(description="Cursor for pagination")] = None,
    limit: Annotated[
        str, Field(description="Limit: '1d', '30d', '90d' for time range, or number like '50'")
    ] = "1d",
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'bot' (default) or 'user'. Different tokens have different permissions.")
    ] = "bot",
) -> str:
    """Get thread replies. Returns CSV with cursor in last row for pagination.

    Use `token_type` to select 'bot' (default) or 'user' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    # Resolve channel reference to ID
    resolved_channel = provider.resolve_channel(channel_id)
    if not resolved_channel:
        raise ValueError(f"Channel '{channel_id}' not found.")

    if not thread_ts or "." not in thread_ts:
        raise ValueError("thread_ts must be a valid timestamp in format 1234567890.123456")

    # Parse limit
    limit_count, oldest, latest = parse_limit_expression(limit if not cursor else "")

    try:
        params = {
            "channel": resolved_channel,
            "ts": thread_ts,
            "limit": limit_count,
            "inclusive": False,
        }
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest
        if cursor:
            params["cursor"] = cursor

        response = client.conversations_replies(**params)
        slack_messages = response.get("messages", [])

        # Filter activity messages if needed
        messages = []
        for msg in slack_messages:
            subtype = msg.get("subtype", "")
            if subtype and subtype != "bot_message" and not include_activity_messages:
                continue
            messages.append(convert_slack_message(msg, resolved_channel, provider))

        # Add pagination cursor to last message
        if messages and response.get("has_more"):
            next_cursor = response.get("response_metadata", {}).get("next_cursor", "")
            messages[-1]["cursor"] = next_cursor

        return messages_to_csv(messages)

    except SlackApiError as e:
        raise RuntimeError(f"Slack API error: {e.response['error']}") from e


@mcp.tool
def conversations_add_message(
    channel_id: Annotated[str, Field(description="ID of the channel (Cxxxxxxxxxx) or name (#general, @username)")],
    payload: Annotated[str, Field(description="Message text (markdown or plain text)")],
    thread_ts: Annotated[str | None, Field(description="Thread timestamp to reply to")] = None,
    content_type: Annotated[str, Field(description="'text/markdown' or 'text/plain'")] = "text/markdown",
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'bot' (default) or 'user'. Different tokens have different permissions.")
    ] = "bot",
) -> str:
    """Post a message to a channel or thread. Returns the posted message as CSV.

    Use `token_type` to select 'bot' (default) or 'user' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    # Check if tool is enabled
    tool_config = os.environ.get("SLACK_MCP_ADD_MESSAGE_TOOL", "")
    if not tool_config:
        raise ValueError(
            "The conversations_add_message tool is disabled by default to prevent accidental spamming. "
            "Set SLACK_MCP_ADD_MESSAGE_TOOL=true or to a comma-separated list of allowed channel IDs."
        )

    # Resolve channel
    resolved_channel = provider.resolve_channel(channel_id)
    if not resolved_channel:
        raise ValueError(f"Channel '{channel_id}' not found.")

    if not is_channel_allowed(resolved_channel):
        raise ValueError(f"Posting to channel '{resolved_channel}' is not allowed by policy: {tool_config}")

    if thread_ts and "." not in thread_ts:
        raise ValueError("thread_ts must be a valid timestamp in format 1234567890.123456")

    if content_type not in ("text/markdown", "text/plain"):
        raise ValueError("content_type must be 'text/markdown' or 'text/plain'")

    try:
        # Build message options
        kwargs: dict[str, Any] = {
            "channel": resolved_channel,
            "text": payload,
        }

        if thread_ts:
            kwargs["thread_ts"] = thread_ts

        if content_type == "text/plain":
            kwargs["mrkdwn"] = False

        # Handle link unfurling
        unfurl_opt = os.environ.get("SLACK_MCP_ADD_MESSAGE_UNFURLING", "")
        if is_unfurling_enabled(payload, unfurl_opt):
            kwargs["unfurl_links"] = True
        else:
            kwargs["unfurl_links"] = False
            kwargs["unfurl_media"] = False

        response = client.chat_postMessage(**kwargs)

        # Optionally mark as read
        mark_config = os.environ.get("SLACK_MCP_ADD_MESSAGE_MARK", "")
        if mark_config in ("1", "true", "yes"):
            client.conversations_mark(channel=resolved_channel, ts=response["ts"])

        # Fetch the posted message
        history_response = client.conversations_history(
            channel=resolved_channel,
            oldest=response["ts"],
            latest=response["ts"],
            inclusive=True,
            limit=1,
        )

        messages = []
        for msg in history_response.get("messages", []):
            messages.append(convert_slack_message(msg, resolved_channel, provider))

        return messages_to_csv(messages)

    except SlackApiError as e:
        raise RuntimeError(f"Slack API error: {e.response['error']}") from e


@mcp.tool
def conversations_search_messages(
    search_query: Annotated[str | None, Field(description="Search query or Slack message URL")] = None,
    filter_in_channel: Annotated[str | None, Field(description="Filter by channel ID or #name")] = None,
    filter_in_im_or_mpim: Annotated[str | None, Field(description="Filter by DM ID or @username")] = None,
    filter_users_with: Annotated[str | None, Field(description="Filter threads/DMs with user")] = None,
    filter_users_from: Annotated[str | None, Field(description="Filter messages from user")] = None,
    filter_date_before: Annotated[str | None, Field(description="Filter before date (YYYY-MM-DD)")] = None,
    filter_date_after: Annotated[str | None, Field(description="Filter after date (YYYY-MM-DD)")] = None,
    filter_date_on: Annotated[str | None, Field(description="Filter on specific date (YYYY-MM-DD)")] = None,
    filter_date_during: Annotated[str | None, Field(description="Filter during period")] = None,
    filter_threads_only: Annotated[bool, Field(description="Only return thread messages")] = False,
    cursor: Annotated[str | None, Field(description="Cursor for pagination")] = None,
    limit: Annotated[int, Field(description="Maximum results (1-100)")] = 20,
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'user' (default) or 'bot'. Search typically requires user token.")
    ] = "user",
) -> str:
    """Search messages with filters. Returns CSV with cursor in last row for pagination.

    Use `token_type` to select 'user' (default, required for search API) or 'bot' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    # Build query string
    query_parts = []

    if search_query:
        query_parts.append(search_query)

    if filter_threads_only:
        query_parts.append("is:thread")

    if filter_in_channel:
        channel = provider.get_channel_by_name(filter_in_channel) or provider.get_channel(filter_in_channel)
        if channel:
            query_parts.append(f"in:{channel.name.lstrip('#')}")
        else:
            query_parts.append(f"in:{filter_in_channel.lstrip('#')}")

    if filter_in_im_or_mpim:
        user_id = provider.resolve_user(filter_in_im_or_mpim)
        if user_id:
            query_parts.append(f"in:<@{user_id}>")
        else:
            query_parts.append(f"in:{filter_in_im_or_mpim}")

    if filter_users_with:
        user_id = provider.resolve_user(filter_users_with)
        if user_id:
            query_parts.append(f"with:<@{user_id}>")

    if filter_users_from:
        user_id = provider.resolve_user(filter_users_from)
        if user_id:
            query_parts.append(f"from:<@{user_id}>")

    # Date filters (can't combine on/during with before/after)
    if filter_date_on:
        query_parts.append(f"on:{filter_date_on}")
    elif filter_date_during:
        query_parts.append(f"during:{filter_date_during}")
    else:
        if filter_date_after:
            query_parts.append(f"after:{filter_date_after}")
        if filter_date_before:
            query_parts.append(f"before:{filter_date_before}")

    query = " ".join(query_parts)
    if not query:
        raise ValueError("At least one search parameter is required.")

    # Parse pagination cursor
    page = 1
    if cursor:
        try:
            decoded = base64.b64decode(cursor).decode()
            if decoded.startswith("page:"):
                page = int(decoded.split(":")[1])
        except Exception:
            raise ValueError(f"Invalid cursor: {cursor}")

    try:
        response = client.search_messages(query=query, count=limit, page=page, highlight=False)
        matches = response.get("messages", {}).get("matches", [])
        pagination = response.get("messages", {}).get("pagination", {})

        messages = []
        for msg in matches:
            user_id = msg.get("user", "")
            user = provider.get_user(user_id)
            user_name = user.name if user else msg.get("username", user_id)
            real_name = user.real_name if user else user_name

            # Extract thread_ts from permalink if available
            thread_ts = ""
            if permalink := msg.get("permalink"):
                match = re.search(r"thread_ts=([0-9.]+)", permalink)
                if match:
                    thread_ts = match.group(1)

            try:
                time_str = timestamp_to_iso(msg.get("ts", ""))
            except ValueError:
                time_str = ""

            text = msg.get("text", "")
            text += attachments_to_csv_suffix(text, msg.get("attachments", []))
            text = process_text(text)

            channel_name = msg.get("channel", {}).get("name", "")
            messages.append({
                "msgID": msg.get("ts", ""),
                "userID": user_id,
                "userName": user_name,
                "realName": real_name,
                "channelID": f"#{channel_name}" if channel_name else "",
                "ThreadTs": thread_ts,
                "text": text,
                "time": time_str,
                "reactions": "",
                "cursor": "",
            })

        # Add pagination cursor to last message
        if messages and pagination.get("page", 1) < pagination.get("page_count", 1):
            next_page = pagination.get("page", 1) + 1
            next_cursor = base64.b64encode(f"page:{next_page}".encode()).decode()
            messages[-1]["cursor"] = next_cursor

        return messages_to_csv(messages)

    except SlackApiError as e:
        raise RuntimeError(f"Slack API error: {e.response['error']}") from e


# ---------- Channels Tool ----------


@mcp.tool
def channels_list(
    channel_types: Annotated[
        str, Field(description="Comma-separated types: 'mpim', 'im', 'public_channel', 'private_channel'")
    ],
    sort: Annotated[str | None, Field(description="Sort by 'popularity' (member count)")] = None,
    limit: Annotated[int, Field(description="Maximum results (1-999)")] = 100,
    cursor: Annotated[str | None, Field(description="Cursor for pagination")] = None,
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'bot' (default) or 'user'. Different tokens have different permissions.")
    ] = "bot",
) -> str:
    """Get list of channels. Returns CSV with cursor in last row for pagination.

    Use `token_type` to select 'bot' (default) or 'user' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    ready, err = provider.is_ready()
    if not ready:
        raise RuntimeError(f"Provider not ready: {err}")

    # Parse channel types
    valid_types = {"mpim", "im", "public_channel", "private_channel"}
    types = [t.strip() for t in channel_types.split(",") if t.strip() in valid_types]

    if not types:
        types = ["public_channel", "private_channel"]

    # Cap limit
    if limit > 999:
        limit = 999

    # Get channels from cache
    all_channels = provider.get_channels_by_types(types)

    # Sort by ID for consistent pagination
    all_channels.sort(key=lambda c: c.id)

    # Apply cursor-based pagination
    start_index = 0
    if cursor:
        try:
            decoded = base64.b64decode(cursor).decode()
            for i, ch in enumerate(all_channels):
                if ch.id > decoded:
                    start_index = i
                    break
        except Exception:
            pass

    end_index = min(start_index + limit, len(all_channels))
    paged_channels = all_channels[start_index:end_index]

    # Sort by popularity if requested
    if sort == "popularity":
        paged_channels.sort(key=lambda c: c.member_count, reverse=True)

    # Convert to output format
    channels = []
    for ch in paged_channels:
        channels.append({
            "id": ch.id,
            "name": ch.name,
            "topic": ch.topic,
            "purpose": ch.purpose,
            "memberCount": ch.member_count,
            "cursor": "",
        })

    # Add pagination cursor
    if channels and end_index < len(all_channels):
        next_cursor = base64.b64encode(all_channels[end_index - 1].id.encode()).decode()
        channels[-1]["cursor"] = next_cursor

    return channels_to_csv(channels)


@mcp.tool
def channels_create(
    name: Annotated[str, Field(description="Channel name (lowercase, numbers, hyphens, underscores; max 80 chars)")],
    is_private: Annotated[bool, Field(description="Create as private channel")] = False,
    description: Annotated[str | None, Field(description="Channel description/purpose")] = None,
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'bot' (default) or 'user'. Different tokens have different permissions.")
    ] = "bot",
) -> str:
    """Create a new Slack channel (idempotent). Returns channel info as CSV.

    If a channel with the given name already exists and is managed by this MCP
    instance (created by current user with MCP marker), it will be returned
    instead of creating a new one.

    If a channel exists but is NOT managed by this MCP, an error is raised.

    Use `token_type` to select 'bot' (default) or 'user' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    # Check if feature is enabled
    if not is_channel_management_enabled():
        raise ValueError(
            "Channel management is disabled. Set SLACK_MCP_CHANNEL_MANAGEMENT=true to enable this feature."
        )

    # Validate channel name
    if not name:
        raise ValueError("Channel name cannot be empty")

    if len(name) > 80:
        raise ValueError(f"Channel name too long: {len(name)} chars (max 80)")

    # Channel name must be lowercase alphanumeric with hyphens/underscores
    if not re.match(r"^[a-z0-9_-]+$", name):
        raise ValueError(
            "Channel name must be lowercase alphanumeric with hyphens/underscores only. "
            f"Invalid name: '{name}'"
        )

    # Check if channel already exists in cache
    # Channels are stored with '#' prefix in the cache (e.g., '#my-channel')
    cached_channel_id = provider._channels_inv.get(f"#{name}")

    if cached_channel_id:
        # Channel exists - check ownership
        is_owned, channel_data = check_channel_ownership(provider, client, cached_channel_id)

        if is_owned:
            # Channel is MCP-managed - return it (idempotent behavior)
            channel_info = {
                "channelID": cached_channel_id,
                "name": name,
                "is_private": channel_data.get("is_private", False),
                "creator": channel_data.get("creator", ""),
                "purpose": channel_data.get("purpose", {}).get("value", ""),
                "is_new": False,
            }
            return channel_info_to_csv(channel_info)
        else:
            # Channel exists but not managed by this MCP
            raise ValueError(
                f"Channel '#{name}' already exists but is not managed by this MCP instance. "
                f"Cannot create or modify channels not created by this MCP."
            )

    try:
        # Create the channel
        response = client.conversations_create(
            name=name,
            is_private=is_private,
        )

        channel_data = response.get("channel", {})
        channel_id = channel_data.get("id", "")
        creator_id = channel_data.get("creator", "")

        # Build purpose string with MCP marker
        if description:
            purpose_string = f"{description} {MCP_MARKER}"
        else:
            purpose_string = MCP_MARKER

        # Set the channel purpose
        client.conversations_setPurpose(
            channel=channel_id,
            purpose=purpose_string,
        )

        # Refresh channel cache to include the new channel (force API fetch)
        provider.refresh_channels(force=True)

        # Build response
        channel_info = {
            "channelID": channel_id,
            "name": name,
            "is_private": is_private,
            "creator": creator_id,
            "purpose": purpose_string,
            "is_new": True,
        }

        return channel_info_to_csv(channel_info)

    except SlackApiError as e:
        error_msg = e.response.get("error", "unknown_error")

        # Handle race condition: channel was created between our check and create
        if error_msg == "name_taken":
            # Refresh channel cache to get the newly created channel (force API fetch)
            provider.refresh_channels(force=True)

            # Try to find the channel again
            cached_channel_id = provider._channels_inv.get(f"#{name}")
            if cached_channel_id:
                # Check ownership
                is_owned, channel_data = check_channel_ownership(provider, client, cached_channel_id)

                if is_owned:
                    # Channel is MCP-managed - return it
                    channel_info = {
                        "channelID": cached_channel_id,
                        "name": name,
                        "is_private": channel_data.get("is_private", False),
                        "creator": channel_data.get("creator", ""),
                        "purpose": channel_data.get("purpose", {}).get("value", ""),
                        "is_new": False,
                    }
                    return channel_info_to_csv(channel_info)
                else:
                    # Channel exists but not managed by this MCP
                    raise ValueError(
                        f"Channel '#{name}' already exists but is not managed by this MCP instance. "
                        f"Cannot create or modify channels not created by this MCP."
                    )
            else:
                # Channel not found even after refresh - unusual case
                raise RuntimeError(
                    f"Channel '#{name}' was reported as taken but could not be found in channel list."
                )

        # Re-raise other API errors
        raise RuntimeError(f"Slack API error: {error_msg}") from e


@mcp.tool
def channels_invite_users(
    channel_id: Annotated[str, Field(description="Channel ID or name (e.g., C1234567890 or #project-alpha)")],
    user_ids: Annotated[str, Field(description="Comma-separated user IDs or @mentions (e.g., 'U123,U456' or '@alice,@bob')")],
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'bot' (default) or 'user'. Different tokens have different permissions.")
    ] = "bot",
) -> str:
    """Invite users to a Slack channel. Returns result as CSV.

    This tool invites one or more users to a specified channel. Users already
    in the channel are silently skipped (idempotent behavior).

    Requires SLACK_MCP_CHANNEL_MANAGEMENT=true to be enabled.

    Use `token_type` to select 'bot' (default) or 'user' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    # Check if feature is enabled
    if not is_channel_management_enabled():
        raise ValueError(
            "Channel management is disabled. Set SLACK_MCP_CHANNEL_MANAGEMENT=true to enable this feature."
        )

    # Resolve channel reference to ID
    resolved_channel = provider.resolve_channel(channel_id)
    if not resolved_channel:
        raise ValueError(f"Channel '{channel_id}' not found.")

    # Resolve user references to IDs
    try:
        user_id_list = resolve_user_list(provider, user_ids)
    except ValueError as e:
        raise ValueError(f"Failed to resolve users: {e}") from e

    if not user_id_list:
        raise ValueError("No valid users specified")

    # Track results
    invited_users = []
    already_members = []

    # Invite users one by one to handle already_in_channel gracefully
    for user_id in user_id_list:
        try:
            client.conversations_invite(
                channel=resolved_channel,
                users=user_id,
            )
            invited_users.append(user_id)
        except SlackApiError as e:
            error_msg = e.response.get("error", "unknown_error")
            if error_msg == "already_in_channel":
                # User already in channel - not an error (idempotent behavior)
                already_members.append(user_id)
            else:
                # Other errors are real problems
                raise RuntimeError(f"Slack API error for user {user_id}: {error_msg}") from e

    # Build CSV response
    output = io.StringIO()
    fieldnames = ["channelID", "invited_users", "already_members"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow({
        "channelID": resolved_channel,
        "invited_users": ",".join(invited_users) if invited_users else "",
        "already_members": ",".join(already_members) if already_members else "",
    })
    return output.getvalue()


@mcp.tool
def channels_remove_user(
    channel_id: Annotated[str, Field(description="Channel ID or name (e.g., C1234567890 or #project-alpha)")],
    user_id: Annotated[str, Field(description="User ID or @mention to remove (e.g., 'U123' or '@alice')")],
    token_type: Annotated[
        TokenType,
        Field(description="Token to use: 'bot' (default) or 'user'. Different tokens have different permissions.")
    ] = "bot",
) -> str:
    """Remove a user from a Slack channel. Returns result as CSV.

    This tool removes a user from a specified channel. If the user is not
    in the channel, returns a 'not_in_channel' status (not an error).

    Requires SLACK_MCP_CHANNEL_MANAGEMENT=true to be enabled.

    Use `token_type` to select 'bot' (default) or 'user' token.
    """
    provider = get_provider()
    client = get_client(provider, token_type)

    # Check if feature is enabled
    if not is_channel_management_enabled():
        raise ValueError(
            "Channel management is disabled. Set SLACK_MCP_CHANNEL_MANAGEMENT=true to enable this feature."
        )

    # Resolve channel reference to ID
    resolved_channel = provider.resolve_channel(channel_id)
    if not resolved_channel:
        raise ValueError(f"Channel '{channel_id}' not found.")

    # Resolve user reference to ID
    resolved_user = provider.resolve_user(user_id)
    if not resolved_user:
        raise ValueError(f"User '{user_id}' not found.")

    # Try to remove user from channel
    try:
        client.conversations_kick(
            channel=resolved_channel,
            user=resolved_user,
        )
        status = "removed"
    except SlackApiError as e:
        error_msg = e.response.get("error", "unknown_error")
        if error_msg == "not_in_channel":
            # User wasn't in channel - not an error (idempotent behavior)
            status = "not_in_channel"
        else:
            # Other errors are real problems
            raise RuntimeError(f"Slack API error: {error_msg}") from e

    # Build CSV response
    output = io.StringIO()
    fieldnames = ["channelID", "user_id", "status"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow({
        "channelID": resolved_channel,
        "user_id": resolved_user,
        "status": status,
    })
    return output.getvalue()


# ---------- Resources ----------


@mcp.resource("slack://{workspace}/channels")
def channels_resource(workspace: str) -> str:
    """Directory of Slack channels as CSV."""
    provider = get_provider()

    ready, err = provider.is_ready()
    if not ready:
        raise RuntimeError(f"Provider not ready: {err}")

    channels = []
    for ch in provider.channels.values():
        channels.append({
            "id": ch.id,
            "name": ch.name,
            "topic": ch.topic,
            "purpose": ch.purpose,
            "memberCount": ch.member_count,
            "cursor": "",
        })

    return channels_to_csv(channels)


@mcp.resource("slack://{workspace}/users")
def users_resource(workspace: str) -> str:
    """Directory of Slack users as CSV."""
    provider = get_provider()

    ready, err = provider.is_ready()
    if not ready:
        raise RuntimeError(f"Provider not ready: {err}")

    users = []
    for u in provider.users.values():
        users.append({
            "userID": u.id,
            "userName": u.name,
            "realName": u.real_name,
        })

    return users_to_csv(users)


def run_server():
    """Run the MCP server."""
    mcp.run()
