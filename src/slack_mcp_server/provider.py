"""Slack API provider with caching for users and channels."""

import json
import logging
import os
import re
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import certifi
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


@dataclass
class Channel:
    """Represents a Slack channel."""

    id: str
    name: str
    topic: str = ""
    purpose: str = ""
    member_count: int = 0
    is_im: bool = False
    is_mpim: bool = False
    is_private: bool = False
    user: str = ""  # User ID for IM channels
    members: list[str] = field(default_factory=list)


@dataclass
class User:
    """Represents a Slack user."""

    id: str
    name: str
    real_name: str = ""


class SlackProvider:
    """Provides access to Slack API with caching for users and channels."""

    ALL_CHANNEL_TYPES = ["mpim", "im", "public_channel", "private_channel"]

    def __init__(
        self,
        bot_token: str | None = None,
        user_token: str | None = None,
        users_cache_path: str | None = None,
        channels_cache_path: str | None = None,
    ):
        """Initialize the Slack provider.

        Args:
            bot_token: Bot OAuth token (xoxb-...) - used for most operations
            user_token: User OAuth token (xoxp-...) - used for search operations
            users_cache_path: Path to users cache file
            channels_cache_path: Path to channels cache file
        """
        # Validate both tokens are provided
        missing = []
        if not bot_token:
            missing.append("SLACK_MCP_BOT_TOKEN")
        if not user_token:
            missing.append("SLACK_MCP_USER_TOKEN")
        if missing:
            raise ValueError(
                f"Both bot and user tokens are required. Missing: {', '.join(missing)}"
            )

        # Create SSL context with certifi certificates (fixes macOS SSL issues)
        ssl_context = ssl.create_default_context(cafile=certifi.where())

        # Primary client (bot token) - used for most operations
        self.bot_client = WebClient(token=bot_token, ssl=ssl_context)

        # User client (user token) - used for search operations
        self.user_client: WebClient = WebClient(token=user_token, ssl=ssl_context)

        self._workspace: str | None = None
        self._team_id: str | None = None
        self._user_id: str | None = None

        # Cache setup
        cache_dir = self._get_cache_dir()
        self.users_cache_path = Path(users_cache_path or cache_dir / "users_cache.json")
        self.channels_cache_path = Path(channels_cache_path or cache_dir / "channels_cache_v2.json")

        # In-memory caches
        self._users: dict[str, User] = {}
        self._users_inv: dict[str, str] = {}  # name -> id
        self._channels: dict[str, Channel] = {}
        self._channels_inv: dict[str, str] = {}  # name -> id

        self._users_ready = False
        self._channels_ready = False

    def _get_cache_dir(self) -> Path:
        """Get the cache directory for slack-mcp-server."""
        cache_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "slack-mcp-server"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def auth_test(self) -> dict[str, Any]:
        """Test authentication and return workspace info."""
        response = self.bot_client.auth_test()
        self._workspace = self._extract_workspace(response.get("url", ""))
        self._team_id = response.get("team_id")
        self._user_id = response.get("user_id")
        return response

    def _extract_workspace(self, url: str) -> str:
        """Extract workspace name from Slack URL."""
        # URL format: https://workspace.slack.com/
        match = re.match(r"https?://([^.]+)\.slack\.com", url)
        if match:
            return match.group(1)
        raise ValueError(f"Invalid Slack URL: {url}")

    @property
    def workspace(self) -> str:
        """Get the workspace name."""
        if not self._workspace:
            self.auth_test()
        return self._workspace  # type: ignore

    def is_ready(self) -> tuple[bool, str | None]:
        """Check if the provider is ready with cached data."""
        if not self._users_ready:
            return False, "users cache is not ready yet"
        if not self._channels_ready:
            return False, "channels cache is not ready yet"
        return True, None

    # ---------- User Cache Methods ----------

    def refresh_users(self) -> None:
        """Load users from cache or fetch from API."""
        # Try loading from cache first
        if self.users_cache_path.exists():
            try:
                with open(self.users_cache_path) as f:
                    cached_users = json.load(f)
                for u in cached_users:
                    user = User(id=u["id"], name=u["name"], real_name=u.get("real_name", ""))
                    self._users[user.id] = user
                    self._users_inv[user.name] = user.id
                logger.info(f"Loaded {len(cached_users)} users from cache")
                self._users_ready = True
                return
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load users cache: {e}")

        # Fetch from API
        try:
            response = self.bot_client.users_list(limit=1000)
            users_data = response.get("members", [])

            users_to_cache = []
            for u in users_data:
                user = User(
                    id=u["id"],
                    name=u.get("name", ""),
                    real_name=u.get("real_name", u.get("profile", {}).get("real_name", "")),
                )
                self._users[user.id] = user
                self._users_inv[user.name] = user.id
                users_to_cache.append({"id": user.id, "name": user.name, "real_name": user.real_name})

            # Save to cache
            with open(self.users_cache_path, "w") as f:
                json.dump(users_to_cache, f, indent=2)
            logger.info(f"Cached {len(users_to_cache)} users")

        except SlackApiError as e:
            logger.error(f"Failed to fetch users: {e}")
            raise

        self._users_ready = True

    def get_user(self, user_id: str) -> User | None:
        """Get a user by ID."""
        return self._users.get(user_id)

    def get_user_by_name(self, name: str) -> User | None:
        """Get a user by name."""
        user_id = self._users_inv.get(name.lstrip("@"))
        return self._users.get(user_id) if user_id else None

    def resolve_user(self, user_ref: str) -> str | None:
        """Resolve a user reference (@name or Uxxxx) to user ID."""
        user_ref = user_ref.strip()
        if user_ref.startswith("U"):
            return user_ref if user_ref in self._users else None
        if user_ref.startswith("<@"):
            user_ref = user_ref[2:].rstrip(">")
            return user_ref if user_ref in self._users else None
        if user_ref.startswith("@"):
            user_ref = user_ref[1:]
        return self._users_inv.get(user_ref)

    # ---------- Channel Cache Methods ----------

    def refresh_channels(self, force: bool = False) -> None:
        """Load channels from cache or fetch from API.

        Args:
            force: If True, skip cache and fetch directly from API.
        """
        # Try loading from cache first (unless force=True)
        if not force and self.channels_cache_path.exists():
            try:
                with open(self.channels_cache_path) as f:
                    cached_channels = json.load(f)
                for c in cached_channels:
                    channel = Channel(
                        id=c["id"],
                        name=c["name"],
                        topic=c.get("topic", ""),
                        purpose=c.get("purpose", ""),
                        member_count=c.get("memberCount", 0),
                        is_im=c.get("im", False),
                        is_mpim=c.get("mpim", False),
                        is_private=c.get("private", False),
                        user=c.get("user", ""),
                        members=c.get("members", []),
                    )
                    # Re-map IM channel names if we have user cache
                    if channel.is_im and channel.user:
                        channel = self._remap_im_channel(channel)
                    self._channels[channel.id] = channel
                    self._channels_inv[channel.name] = channel.id
                logger.info(f"Loaded {len(cached_channels)} channels from cache")
                self._channels_ready = True
                return
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load channels cache: {e}")

        # Fetch from API
        channels_to_cache = []
        for channel_type in self.ALL_CHANNEL_TYPES:
            channels = self._fetch_channels_by_type(channel_type)
            for channel in channels:
                self._channels[channel.id] = channel
                self._channels_inv[channel.name] = channel.id
                channels_to_cache.append(
                    {
                        "id": channel.id,
                        "name": channel.name,
                        "topic": channel.topic,
                        "purpose": channel.purpose,
                        "memberCount": channel.member_count,
                        "im": channel.is_im,
                        "mpim": channel.is_mpim,
                        "private": channel.is_private,
                        "user": channel.user,
                        "members": channel.members,
                    }
                )

        # Save to cache
        with open(self.channels_cache_path, "w") as f:
            json.dump(channels_to_cache, f, indent=2)
        logger.info(f"Cached {len(channels_to_cache)} channels")

        self._channels_ready = True

    def _fetch_channels_by_type(self, channel_type: str) -> list[Channel]:
        """Fetch channels of a specific type from API."""
        channels = []
        cursor = None

        while True:
            try:
                response = self.bot_client.conversations_list(
                    types=channel_type,
                    limit=999,
                    exclude_archived=True,
                    cursor=cursor,
                )
                for c in response.get("channels", []):
                    channel = self._map_channel(c)
                    channels.append(channel)

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            except SlackApiError as e:
                logger.error(f"Failed to fetch {channel_type} channels: {e}")
                break

        return channels

    def _map_channel(self, c: dict[str, Any]) -> Channel:
        """Map a Slack API channel response to a Channel object."""
        is_im = c.get("is_im", False)
        is_mpim = c.get("is_mpim", False)
        is_private = c.get("is_private", False)

        name = c.get("name", "")
        name_normalized = c.get("name_normalized", name)
        topic = c.get("topic", {}).get("value", "")
        purpose = c.get("purpose", {}).get("value", "")
        member_count = c.get("num_members", 0)
        user_id = c.get("user", "")
        members = c.get("members", [])

        # Format channel name based on type
        if is_im:
            member_count = 2
            user = self._users.get(user_id)
            if user:
                name = f"@{user.name}"
                purpose = f"DM with {user.real_name}"
            else:
                name = f"@{user_id}" if user_id else "@"
                purpose = f"DM with {user_id}" if user_id else "DM with "
            topic = ""
        elif is_mpim:
            member_count = len(members) if members else member_count
            user_names = []
            for uid in members:
                user = self._users.get(uid)
                user_names.append(user.real_name if user else uid)
            name = f"@{name_normalized}"
            purpose = f"Group DM with {', '.join(user_names)}"
            topic = ""
        else:
            name = f"#{name_normalized}"

        return Channel(
            id=c["id"],
            name=name,
            topic=topic,
            purpose=purpose,
            member_count=member_count,
            is_im=is_im,
            is_mpim=is_mpim,
            is_private=is_private,
            user=user_id,
            members=members,
        )

    def _remap_im_channel(self, channel: Channel) -> Channel:
        """Re-map an IM channel with updated user info."""
        user = self._users.get(channel.user)
        if user:
            channel.name = f"@{user.name}"
            channel.purpose = f"DM with {user.real_name}"
        return channel

    def get_channel(self, channel_id: str) -> Channel | None:
        """Get a channel by ID."""
        return self._channels.get(channel_id)

    def get_channel_by_name(self, name: str) -> Channel | None:
        """Get a channel by name."""
        channel_id = self._channels_inv.get(name)
        return self._channels.get(channel_id) if channel_id else None

    def resolve_channel(self, channel_ref: str) -> str | None:
        """Resolve a channel reference (#name, @name, or Cxxxx/Dxxxx/Gxxxx) to channel ID."""
        channel_ref = channel_ref.strip()

        # Direct ID references
        if channel_ref.startswith(("C", "D", "G")):
            return channel_ref if channel_ref in self._channels else None

        # Name references
        if channel_ref.startswith(("#", "@")):
            return self._channels_inv.get(channel_ref)

        return None

    def get_channels_by_types(self, types: list[str]) -> list[Channel]:
        """Get channels filtered by type."""
        type_set = set(types)
        result = []

        for channel in self._channels.values():
            if "public_channel" in type_set and not channel.is_private and not channel.is_im and not channel.is_mpim:
                result.append(channel)
            elif "private_channel" in type_set and channel.is_private and not channel.is_im and not channel.is_mpim:
                result.append(channel)
            elif "im" in type_set and channel.is_im:
                result.append(channel)
            elif "mpim" in type_set and channel.is_mpim:
                result.append(channel)

        return result

    @property
    def user_id(self) -> str | None:
        """Get the authenticated user ID."""
        return self._user_id

    @property
    def users(self) -> dict[str, User]:
        """Get all cached users."""
        return self._users

    @property
    def channels(self) -> dict[str, Channel]:
        """Get all cached channels."""
        return self._channels
