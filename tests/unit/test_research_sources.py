from datetime import UTC, datetime

import httpx
import pytest

from src.research.sources import (
    ContentSource,
    RSSSource,
    canonicalize_url,
    ensure_public_http_url,
    html_to_text,
)


def test_canonicalize_url_removes_tracking_sorts_query_and_fragment() -> None:
    canonical = canonicalize_url(
        "HTTPS://Example.COM:443/a/../posts/?utm_source=news&b=2&a=1#section"
    )
    assert canonical == "https://example.com/posts/?a=1&b=2"


def test_canonicalize_url_rejects_credentials() -> None:
    with pytest.raises(ValueError, match="credentials"):
        canonicalize_url("https://user:secret@example.com/feed")


@pytest.mark.asyncio
async def test_public_url_guard_rejects_loopback_without_network() -> None:
    with pytest.raises(ValueError, match="public IP"):
        await ensure_public_http_url("http://127.0.0.1/feed")


def test_rss_parser_normalizes_entries() -> None:
    xml = """
    <rss version="2.0">
      <channel>
        <item>
          <guid>post-1</guid>
          <title>Practical &amp; useful</title>
          <link>/posts/1?utm_source=feed</link>
          <description><![CDATA[<p>A clear <strong>example</strong>.</p>]]></description>
          <author>Ada</author>
          <pubDate>Mon, 11 Aug 2025 10:00:00 +0000</pubDate>
        </item>
      </channel>
    </rss>
    """
    documents = RSSSource.parse(xml, feed_url="https://example.com/feed")
    assert len(documents) == 1
    assert documents[0].external_id == "post-1"
    assert documents[0].url == "https://example.com/posts/1?utm_source=feed"
    assert documents[0].title == "Practical & useful"
    assert documents[0].content == "A clear example ."
    assert documents[0].author == "Ada"
    assert documents[0].published_at == datetime(2025, 8, 11, 10, tzinfo=UTC)


def test_atom_parser_handles_namespaces_and_author() -> None:
    xml = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>tag:example.com,2025:2</id>
        <title>Agent systems</title>
        <link href="https://example.com/posts/2" rel="alternate" />
        <summary>Bounded workflows beat loops.</summary>
        <updated>2025-08-11T12:00:00Z</updated>
        <author><name>Grace</name></author>
      </entry>
    </feed>
    """
    documents = RSSSource.parse(xml, feed_url="https://example.com/atom")
    assert len(documents) == 1
    assert documents[0].external_id == "tag:example.com,2025:2"
    assert documents[0].author == "Grace"
    assert documents[0].published_at == datetime(2025, 8, 11, 12, tzinfo=UTC)


def test_html_to_text_collapses_markup_and_whitespace() -> None:
    assert html_to_text("<p>Hello   <b>world</b></p>") == "Hello world"


def test_rss_source_satisfies_content_source_protocol() -> None:
    source: ContentSource = RSSSource("https://example.com/feed")
    assert source is not None


@pytest.mark.asyncio
async def test_feed_fetch_validates_redirects_and_parses_bounded_response() -> None:
    checked_urls: list[str] = []

    async def record_url(url: str) -> None:
        checked_urls.append(url)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed":
            return httpx.Response(302, headers={"location": "/actual"})
        return httpx.Response(
            200,
            content=(
                b"<rss><channel><item><title>One</title>"
                b"<link>https://example.com/one</link>"
                b"<description>A sufficiently detailed feed entry.</description>"
                b"</item></channel></rss>"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = RSSSource(
            "https://example.com/feed",
            client=client,
            url_validator=record_url,
        )
        documents = await source.fetch()

    assert checked_urls == ["https://example.com/feed", "https://example.com/actual"]
    assert len(documents) == 1
    assert documents[0].title == "One"


@pytest.mark.asyncio
async def test_feed_fetch_rejects_declared_oversized_response() -> None:
    async def allow_url(url: str) -> None:
        assert url == "https://example.com/feed"

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-length": "2000001"},
            content=b"small body",
            request=request,
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        source = RSSSource(
            "https://example.com/feed",
            client=client,
            url_validator=allow_url,
        )
        with pytest.raises(ValueError, match="size limit"):
            await source.fetch()
