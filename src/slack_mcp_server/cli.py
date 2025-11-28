"""CLI entry point for Slack MCP Server."""

import argparse
import logging
import os
import sys

from . import __version__


def setup_logging(log_level: str, transport: str) -> None:
    """Configure logging based on environment."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Use stderr for stdio transport to not interfere with MCP protocol
    handler = logging.StreamHandler(sys.stderr if transport == "stdio" else sys.stdout)

    # Determine format based on environment
    use_json = (
        os.environ.get("SLACK_MCP_LOG_FORMAT", "").lower() == "json"
        or os.environ.get("KUBERNETES_SERVICE_HOST")
        or os.environ.get("DOCKER_CONTAINER")
        or os.environ.get("container")
    )

    if use_json:
        fmt = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s", "app": "slack-mcp-server"}'
    else:
        fmt = "%(asctime)s | %(levelname)s | %(message)s"

    handler.setFormatter(logging.Formatter(fmt))
    logging.root.handlers = [handler]
    logging.root.setLevel(level)


def main() -> None:
    """Main entry point for slack-mcp-server CLI."""
    parser = argparse.ArgumentParser(
        description="Slack MCP Server - A powerful MCP server for Slack workspaces",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Authentication (one of these is required):
  --xoxp-token       User OAuth token (xoxp-...)
  --xoxc-token       Browser token (xoxc-...) with --xoxd-token

Environment Variables:
  SLACK_MCP_XOXP_TOKEN         User OAuth token
  SLACK_MCP_XOXC_TOKEN         Browser token
  SLACK_MCP_XOXD_TOKEN         Browser cookie d value
  SLACK_MCP_ADD_MESSAGE_TOOL   Enable message posting (true/1/channel-list)
  SLACK_MCP_ADD_MESSAGE_MARK   Mark messages as read after posting
  SLACK_MCP_ADD_MESSAGE_UNFURLING  Control link unfurling (yes/domain-list)
  SLACK_MCP_USERS_CACHE        Custom path for users cache
  SLACK_MCP_CHANNELS_CACHE     Custom path for channels cache
  SLACK_MCP_LOG_LEVEL          Log level (debug/info/warn/error)
  SLACK_MCP_LOG_FORMAT         Log format (json/console)

Example:
  # Using uvx with OAuth token
  uvx --from git+https://github.com/korotovsky/slack-mcp-server slack-mcp-server \\
      --xoxp-token xoxp-your-token

  # Using browser tokens
  slack-mcp-server --xoxc-token xoxc-... --xoxd-token xoxd-...
""",
    )

    # Authentication options
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument(
        "--xoxp-token",
        dest="xoxp_token",
        help="User OAuth token (xoxp-...)",
        default=os.environ.get("SLACK_MCP_XOXP_TOKEN"),
    )
    auth_group.add_argument(
        "--xoxc-token",
        dest="xoxc_token",
        help="Browser token (xoxc-...)",
        default=os.environ.get("SLACK_MCP_XOXC_TOKEN"),
    )
    auth_group.add_argument(
        "--xoxd-token",
        dest="xoxd_token",
        help="Browser cookie d value (xoxd-...)",
        default=os.environ.get("SLACK_MCP_XOXD_TOKEN"),
    )

    # Cache options
    cache_group = parser.add_argument_group("Cache")
    cache_group.add_argument(
        "--users-cache",
        dest="users_cache",
        help="Path to users cache file",
        default=os.environ.get("SLACK_MCP_USERS_CACHE"),
    )
    cache_group.add_argument(
        "--channels-cache",
        dest="channels_cache",
        help="Path to channels cache file",
        default=os.environ.get("SLACK_MCP_CHANNELS_CACHE"),
    )

    # Logging options
    log_group = parser.add_argument_group("Logging")
    log_group.add_argument(
        "--log-level",
        dest="log_level",
        choices=["debug", "info", "warning", "error"],
        default=os.environ.get("SLACK_MCP_LOG_LEVEL", "info"),
        help="Log level",
    )

    # Transport (for future HTTP/SSE support)
    parser.add_argument(
        "-t",
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="Transport type (currently only stdio supported)",
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level, args.transport)
    logger = logging.getLogger(__name__)

    # Validate authentication
    if not args.xoxp_token and not (args.xoxc_token and args.xoxd_token):
        parser.error(
            "Authentication required: Either --xoxp-token or both --xoxc-token and --xoxd-token must be provided"
        )

    logger.info(f"Starting Slack MCP Server v{__version__}")

    # Initialize provider
    from .server import init_provider, run_server

    try:
        provider = init_provider(
            xoxp_token=args.xoxp_token,
            xoxc_token=args.xoxc_token,
            xoxd_token=args.xoxd_token,
            users_cache_path=args.users_cache,
            channels_cache_path=args.channels_cache,
        )

        # Test authentication
        auth_response = provider.auth_test()
        logger.info(f"Authenticated with Slack - Team: {auth_response.get('team')}, User: {auth_response.get('user')}")

        # Load caches
        logger.info("Caching users...")
        provider.refresh_users()

        logger.info("Caching channels...")
        provider.refresh_channels()

        logger.info("Slack MCP Server is ready")

        # Run the server
        run_server()

    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
