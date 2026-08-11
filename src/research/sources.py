"""Public content-source contracts plus the credential-free RSS/Atom adapter."""

import asyncio
import ipaddress
import posixpath
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

DEFAULT_TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})
MAX_FEED_BYTES = 2_000_000
MAX_REDIRECTS = 3


@dataclass(frozen=True)
class SourceDocument:
    url: str
    title: str
    content: str
    external_id: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    raw_metadata: dict[str, object] = field(default_factory=dict)


class ContentSource(Protocol):
    async def fetch(self) -> Sequence[SourceDocument]: ...


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def canonicalize_url(
    url: str,
    *,
    tracking_parameters: frozenset[str] = DEFAULT_TRACKING_PARAMETERS,
) -> str:
    """Return a deterministic HTTP(S) URL suitable for duplicate matching."""
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be absolute HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed")

    scheme = parsed.scheme.lower()
    raw_hostname = parsed.hostname.rstrip(".").lower()
    try:
        hostname = ipaddress.ip_address(raw_hostname).compressed
    except ValueError:
        try:
            hostname = raw_hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("URL has an invalid hostname") from exc
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL has an invalid port") from exc
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = host if port is None or default_port else f"{host}:{port}"

    decoded_path = unquote(parsed.path or "/")
    normalized_path = posixpath.normpath(decoded_path)
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if decoded_path.endswith("/") and normalized_path != "/":
        normalized_path = f"{normalized_path}/"
    encoded_path = quote(normalized_path, safe="/:@-._~!$&'()*+,;=")

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in tracking_parameters and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit((scheme, netloc, encoded_path, query, ""))


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global


async def ensure_public_http_url(url: str) -> None:
    """Reject local/private destinations before any feed network request."""
    parsed = urlsplit(canonicalize_url(url))
    assert parsed.hostname is not None
    hostname = parsed.hostname
    if hostname.casefold() == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("local feed URLs are not allowed")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        resolved = {str(item[4][0]) for item in addresses}
    else:
        resolved = {str(literal)}

    if not resolved or any(not _is_public_address(address) for address in resolved):
        raise ValueError("feed URL must resolve only to public IP addresses")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _first_text(element: ElementTree.Element, *names: str) -> str | None:
    wanted = set(names)
    for child in element:
        if _local_name(child.tag) in wanted and child.text and child.text.strip():
            return child.text.strip()
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _rss_documents(root: ElementTree.Element, feed_url: str) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    for item in (element for element in root.iter() if _local_name(element.tag) == "item"):
        title = _first_text(item, "title") or "Untitled"
        link = _first_text(item, "link")
        guid = _first_text(item, "guid")
        if not link and guid and urlsplit(guid).scheme in {"http", "https"}:
            link = guid
        if not link:
            continue
        content = _first_text(item, "encoded", "description") or title
        author = _first_text(item, "creator", "author")
        published = _parse_datetime(_first_text(item, "pubDate", "published", "date"))
        documents.append(
            SourceDocument(
                external_id=guid,
                url=urljoin(feed_url, link),
                title=html_to_text(title),
                content=html_to_text(content),
                author=html_to_text(author) if author else None,
                published_at=published,
                raw_metadata={"feed_format": "rss"},
            )
        )
    return documents


def _atom_documents(root: ElementTree.Element, feed_url: str) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    for entry in (element for element in root.iter() if _local_name(element.tag) == "entry"):
        title = _first_text(entry, "title") or "Untitled"
        external_id = _first_text(entry, "id")
        links = _children(entry, "link")
        link = next(
            (
                candidate.attrib.get("href")
                for candidate in links
                if candidate.attrib.get("href")
                and candidate.attrib.get("rel", "alternate") == "alternate"
            ),
            None,
        )
        if not link:
            continue
        content = _first_text(entry, "content", "summary") or title
        published = _parse_datetime(_first_text(entry, "published", "updated"))
        author = None
        author_nodes = _children(entry, "author")
        if author_nodes:
            author = _first_text(author_nodes[0], "name")
        documents.append(
            SourceDocument(
                external_id=external_id,
                url=urljoin(feed_url, link),
                title=html_to_text(title),
                content=html_to_text(content),
                author=html_to_text(author) if author else None,
                published_at=published,
                raw_metadata={"feed_format": "atom"},
            )
        )
    return documents


class RSSSource:
    def __init__(
        self,
        url: str,
        *,
        client: httpx.AsyncClient | None = None,
        url_validator: Callable[[str], Awaitable[None]] = ensure_public_http_url,
    ) -> None:
        self.url = canonicalize_url(url)
        self._client = client
        self._url_validator = url_validator

    @staticmethod
    def parse(xml: str | bytes, *, feed_url: str) -> list[SourceDocument]:
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise ValueError("feed returned invalid XML") from exc
        if _local_name(root.tag).casefold() == "feed":
            return _atom_documents(root, feed_url)
        return _rss_documents(root, feed_url)

    async def _download(self) -> bytes:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=10)
        current_url = self.url
        try:
            for _ in range(MAX_REDIRECTS + 1):
                await self._url_validator(current_url)
                async with client.stream("GET", current_url, follow_redirects=False) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("feed redirect omitted its destination")
                        current_url = canonicalize_url(urljoin(current_url, location))
                        continue
                    response.raise_for_status()
                    declared_size = response.headers.get("content-length")
                    if declared_size and int(declared_size) > MAX_FEED_BYTES:
                        raise ValueError("feed response exceeds the size limit")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_FEED_BYTES:
                            raise ValueError("feed response exceeds the size limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            raise ValueError("feed exceeded the redirect limit")
        finally:
            if owns_client:
                await client.aclose()

    async def fetch(self) -> Sequence[SourceDocument]:
        payload = await self._download()
        return self.parse(payload, feed_url=self.url)
