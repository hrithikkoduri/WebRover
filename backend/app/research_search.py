"""Search providers for the Research Agent's browser-based source discovery."""

import asyncio
from html import escape
import json
import os
from urllib.parse import urlsplit
from uuid import uuid4


MCP_URL = "https://search.parallel.ai/mcp"
USER_AGENT = "WebRover/0.1.0 (+https://github.com/hrithikkoduri/WebRover)"
SEARCH_TIMEOUT = 30


def initialize_search(state):
    """Freeze the provider and create one opaque ID per research invocation."""
    provider = state.get("search_provider")
    if provider is None:
        provider = os.getenv("WEBROVER_SEARCH_PROVIDER", "google")
    if provider not in ("google", "parallel", "disabled"):
        raise ValueError("WEBROVER_SEARCH_PROVIDER must be google, parallel, or disabled")
    return {
        "search_provider": provider,
        "search_session_id": state.get("search_session_id") or str(uuid4()),
    }


def is_google_search(url):
    """Identify the Google landing/search URLs chosen by the URL decision node."""
    parsed = urlsplit(url)
    return parsed.hostname in ("google.com", "www.google.com") and parsed.path in (
        "", "/", "/search"
    )


async def parallel_search(query, session_id):
    # Keep the default installation independent of the optional MCP dependency.
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        raise RuntimeError("Enable Parallel search with: poetry install -E parallel-search") from exc

    try:
        async with asyncio.timeout(SEARCH_TIMEOUT):
            async with streamablehttp_client(
                MCP_URL, headers={"User-Agent": USER_AGENT}
            ) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    if not any(tool.name == "web_search" for tool in tools.tools):
                        raise RuntimeError("Parallel MCP did not advertise web_search")
                    result = await client.call_tool("web_search", {
                        "objective": query,
                        "search_queries": [query],
                        "session_id": session_id,
                    })
    except ExceptionGroup as exc:
        # SDK transport task groups can wrap HTTP/protocol failures. Keep the
        # underlying message useful to the API's existing streamed-error handler.
        def messages(error):
            if isinstance(error, ExceptionGroup):
                return "; ".join(messages(child) for child in error.exceptions)
            return str(error)
        raise RuntimeError("Parallel MCP request failed: " + messages(exc)) from exc
    if result.isError:
        raise RuntimeError("Parallel search failed: " + "\n".join(
            block.text for block in result.content if block.type == "text"
        ))
    for block in result.content:
        if block.type == "text":
            data = json.loads(block.text)
            if isinstance(data, dict) and isinstance(data.get("results"), list):
                return data["results"]
    raise RuntimeError("Parallel search returned no results payload")


def results_html(query, results):
    """Render untrusted search data as text and ordinary, absolute browser links."""
    items = []
    for result in results:
        if not isinstance(result, dict):
            continue
        url = result.get("url")
        if not isinstance(url, str) or any(ord(c) <= 32 for c in url):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                continue
            if parsed.username is not None or parsed.password is not None:
                continue
        except ValueError:
            continue
        title = result.get("title") or url
        excerpts = result.get("excerpts", [])
        if not isinstance(excerpts, list):
            excerpts = []
        items.append(
            '<li><a href="' + escape(url, quote=True) + '">'
            + escape(str(title)) + '</a><p>'
            + escape("\n".join(x for x in excerpts if isinstance(x, str)))
            + '</p></li>'
        )
    if not items:
        raise RuntimeError("Parallel search returned no usable source links; refine the query")
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src \'none\'; base-uri \'none\'; form-action \'none\'">'
        '<title>Parallel search results</title></head><body>'
        '<h1>Search: ' + escape(query) + '</h1><ol>' + "".join(items)
        + '</ol></body></html>'
    )


async def go_to_search(state):
    """Execute the selected provider without falling back after explicit failures."""
    provider = state["search_provider"]
    page = state["page"]
    if provider == "disabled":
        raise PermissionError("Research search is disabled")
    if provider == "google":
        await page.goto("https://www.google.com", timeout=30000, wait_until="domcontentloaded")
        return {"actions_taken": ["Navigated to Google"]}
    if provider != "parallel":
        raise ValueError("Unknown research search provider")
    action = state.get("action") or {}
    query = action.get("args", "").strip() or state["input"]
    results = await parallel_search(query, state["search_session_id"])
    html = results_html(query, results)
    # Use a blank origin: never inject service results into an authenticated site.
    await page.goto("about:blank")
    await page.set_content(html, wait_until="domcontentloaded")
    return {"actions_taken": [f"Searched Parallel for {query}"], "page": page}
