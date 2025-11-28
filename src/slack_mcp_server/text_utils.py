"""Text processing utilities for Slack messages."""

import re
from datetime import datetime, timezone
from typing import Any


def timestamp_to_iso(slack_ts: str) -> str:
    """Convert Slack timestamp to ISO 8601 format.

    Args:
        slack_ts: Slack timestamp in format "1234567890.123456"

    Returns:
        ISO 8601 formatted timestamp
    """
    try:
        parts = slack_ts.split(".")
        if len(parts) != 2:
            raise ValueError(f"Invalid slack timestamp format: {slack_ts}")

        seconds = int(parts[0])
        microseconds = int(parts[1])

        dt = datetime.fromtimestamp(seconds + microseconds / 1_000_000, tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, IndexError) as e:
        raise ValueError(f"Failed to convert timestamp: {e}") from e


def attachment_to_text(attachment: dict[str, Any]) -> str:
    """Convert a Slack attachment to plain text.

    Args:
        attachment: Slack attachment dict

    Returns:
        Plain text representation
    """
    parts = []

    if title := attachment.get("title"):
        parts.append(f"Title: {title}")

    if author := attachment.get("author_name"):
        parts.append(f"Author: {author}")

    if pretext := attachment.get("pretext"):
        parts.append(f"Pretext: {pretext}")

    if text := attachment.get("text"):
        parts.append(f"Text: {text}")

    if footer := attachment.get("footer"):
        ts = attachment.get("ts", "")
        if ts:
            try:
                ts_str = timestamp_to_iso(f"{ts}.000000")
                parts.append(f"Footer: {footer} @ {ts_str}")
            except ValueError:
                parts.append(f"Footer: {footer}")
        else:
            parts.append(f"Footer: {footer}")

    result = "; ".join(parts)

    # Clean up whitespace and special characters
    result = result.replace("\n", " ")
    result = result.replace("\r", " ")
    result = result.replace("\t", " ")
    result = result.replace("(", "[")
    result = result.replace(")", "]")

    return result.strip()


def attachments_to_csv_suffix(msg_text: str, attachments: list[dict[str, Any]]) -> str:
    """Convert attachments to a suffix for CSV output.

    Args:
        msg_text: Original message text
        attachments: List of attachments

    Returns:
        String to append to message text
    """
    if not attachments:
        return ""

    descriptions = []
    for att in attachments:
        plain_text = attachment_to_text(att)
        if plain_text:
            descriptions.append(plain_text)

    if not descriptions:
        return ""

    prefix = ". " if msg_text else ""
    return prefix + ", ".join(descriptions)


def process_text(text: str) -> str:
    """Process message text for output.

    Handles Slack-style links, markdown links, and cleans special characters.

    Args:
        text: Raw message text

    Returns:
        Processed text
    """
    # Helper to format link replacements
    def format_link(url: str, link_text: str, is_last: bool) -> str:
        replacement = f"{url} - {link_text}"
        if not is_last:
            replacement += ","
        return replacement

    def is_last_in_text(original: str, current_text: str) -> bool:
        pos = current_text.rfind(original)
        if pos == -1:
            return False
        after = current_text[pos + len(original) :].strip()
        return after == ""

    # Handle Slack-style links: <URL|Description>
    slack_link_re = re.compile(r"<(https?://[^>|]+)\|([^>]+)>")
    for match in slack_link_re.finditer(text):
        original = match.group(0)
        url = match.group(1)
        link_text = match.group(2)
        is_last = is_last_in_text(original, text)
        replacement = format_link(url, link_text, is_last)
        text = text.replace(original, replacement, 1)

    # Handle markdown links: [Description](URL)
    md_link_re = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
    for match in md_link_re.finditer(text):
        original = match.group(0)
        link_text = match.group(1)
        url = match.group(2)
        is_last = is_last_in_text(original, text)
        replacement = format_link(url, link_text, is_last)
        text = text.replace(original, replacement, 1)

    # Handle HTML links: <a href="URL">text</a>
    html_link_re = re.compile(r'<a\s+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>')
    for match in html_link_re.finditer(text):
        original = match.group(0)
        url = match.group(1)
        link_text = match.group(2)
        is_last = is_last_in_text(original, text)
        replacement = format_link(url, link_text, is_last)
        text = text.replace(original, replacement, 1)

    # Protect URLs before cleaning
    url_re = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
    urls = url_re.findall(text)

    protected = text
    for i, url in enumerate(urls):
        placeholder = f"___URL_PLACEHOLDER_{i}___"
        protected = protected.replace(url, placeholder, 1)

    # Clean special characters (keep alphanumeric, spaces, common punctuation)
    clean_re = re.compile(r"[^0-9\w\s.,\-_:/?=&%]", re.UNICODE)
    cleaned = clean_re.sub("", protected)

    # Restore URLs
    for i, url in enumerate(urls):
        placeholder = f"___URL_PLACEHOLDER_{i}___"
        cleaned = cleaned.replace(placeholder, url, 1)

    # Normalize whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    return cleaned.strip()


def is_unfurling_enabled(text: str, opt: str | None) -> bool:
    """Check if link unfurling should be enabled.

    Args:
        text: Message text containing URLs
        opt: Unfurling option (yes/no/domain-list)

    Returns:
        True if unfurling should be enabled
    """
    if not opt or opt in ("", "no", "false", "0"):
        return False

    if opt in ("yes", "true", "1"):
        return True

    # opt is a comma-separated list of allowed domains
    allowed = set()
    for domain in opt.split(","):
        domain = domain.lower().strip()
        if domain:
            allowed.add(domain)

    # Check all URLs in text
    url_re = re.compile(r"https?://[^\s]+")
    urls = url_re.findall(text)

    for url in urls:
        try:
            # Extract host from URL
            match = re.match(r"https?://([^/:]+)", url)
            if not match:
                continue
            host = match.group(1).lower()
            # Strip port if present
            if ":" in host:
                host = host.split(":")[0]
            # Strip www prefix
            host = host.removeprefix("www.")

            if host not in allowed:
                return False
        except Exception:
            continue

    return True
