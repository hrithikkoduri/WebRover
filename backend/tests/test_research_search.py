"""Focused provider/SDK tests; no model credentials or full NLP stack needed.

Requires from backend: poetry install -E parallel-search
Run from backend: poetry run python -m unittest discover -s tests -v
"""
import asyncio
from contextlib import contextmanager
import json
import os
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
from app import research_search as search


class MCPServer:
    """Exercise the real MCP SDK against deterministic HTTP protocol responses."""
    def __init__(self, results=None, error=False, delay=0):
        self.requests = []
        self.results = results if results is not None else [
            {"url": "https://example.com/source", "title": "Source", "excerpts": ["Evidence"]}
        ]
        self.error = error
        self.delay = delay

    async def handle(self, request):
        body = json.loads(request.content)
        self.requests.append((request, body))
        method = body["method"]
        if method.startswith("notifications/"):
            return httpx.Response(202)
        if method == "initialize":
            result = {"protocolVersion": body["params"]["protocolVersion"],
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "test-search", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "web_search", "description": "Search",
                                "inputSchema": {"type": "object"}}]}
        elif method == "tools/call":
            await asyncio.sleep(self.delay)
            result = {"content": [{"type": "text", "text": "quota reached" if self.error else
                       json.dumps({"results": self.results})}], "isError": self.error}
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    @contextmanager
    def transport(self):
        original = httpx.AsyncClient
        def client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(self.handle)
            return original(*args, **kwargs)
        with patch("httpx.AsyncClient", side_effect=client):
            yield self

    @property
    def calls(self):
        return [body["params"] for _, body in self.requests if body["method"] == "tools/call"]


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_saved_override_and_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(search.initialize_search({})["search_provider"], "google")
        with patch.dict(os.environ, {"WEBROVER_SEARCH_PROVIDER": "parallel"}, clear=True):
            self.assertEqual(search.initialize_search({})["search_provider"], "parallel")
            state = search.initialize_search({"search_provider": "google"})
            self.assertEqual(state["search_provider"], "google")
            self.assertEqual(search.initialize_search(state), state)
            page = AsyncMock()
            await search.go_to_search({**state, "page": page})
            page.goto.assert_awaited_once_with("https://www.google.com", timeout=30000,
                                              wait_until="domcontentloaded")
            page = AsyncMock()
            with self.assertRaises(PermissionError):
                await search.go_to_search({**search.initialize_search({"search_provider": "disabled"}),
                                           "page": page})
            page.goto.assert_not_awaited()
        with patch.dict(os.environ, {"WEBROVER_SEARCH_PROVIDER": "unknown"}, clear=True):
            with self.assertRaises(ValueError):
                search.initialize_search({})

    async def test_real_sdk_anonymous_requests_and_rendered_results(self):
        server = MCPServer()
        page = AsyncMock()
        state = {**search.initialize_search({"search_provider": "parallel"}), "page": page,
                 "input": "initial query", "action": {"args": "refined query"}}
        # Ambient credentials must never leak into this anonymous connection.
        with patch.dict(os.environ, {"PARALLEL_API_KEY": "unused-test-value"}), server.transport():
            result = await search.go_to_search(state)
        self.assertEqual(server.calls[0]["name"], "web_search")
        self.assertEqual(server.calls[0]["arguments"], {
            "objective": "refined query", "search_queries": ["refined query"],
            "session_id": state["search_session_id"]})
        for request, _ in server.requests:
            self.assertEqual(str(request.url), search.MCP_URL)
            self.assertEqual(request.headers["user-agent"], search.USER_AGENT)
            self.assertNotIn("authorization", request.headers)
        self.assertEqual({body["method"] for _, body in server.requests},
                         {"initialize", "notifications/initialized", "tools/list", "tools/call"})
        page.goto.assert_awaited_once_with("about:blank")
        self.assertIn('<a href="https://example.com/source">Source</a>', page.set_content.call_args.args[0])
        self.assertIn("Evidence", page.set_content.call_args.args[0])
        self.assertEqual(result["page"], page)

    async def test_interleaved_conversations_and_retry_keep_ids(self):
        server = MCPServer()
        states = [{**search.initialize_search({"search_provider": "parallel"}),
                   "page": AsyncMock(), "input": f"query {n}"} for n in range(2)]
        self.assertNotEqual(states[0]["search_session_id"], states[1]["search_session_id"])
        for state in states:
            UUID(state["search_session_id"])
        with server.transport():
            await asyncio.gather(*(search.go_to_search(s) for s in states))
            await search.go_to_search({**states[0], "action": {"args": "follow-up"}})
            server.error = True
            with self.assertRaisesRegex(RuntimeError, "quota reached"):
                await search.go_to_search(states[0])
            server.error = False
            await search.go_to_search(states[0])
        self.assertEqual([x["arguments"]["session_id"] for x in server.calls].count(states[0]["search_session_id"]), 4)
        self.assertNotEqual(search.initialize_search({})["search_session_id"], states[0]["search_session_id"])

    async def test_errors_timeout_and_cancellation_never_navigate(self):
        for mode in ("quota", "empty", "timeout", "cancel"):
            with self.subTest(mode=mode):
                server = MCPServer(results=[] if mode == "empty" else None,
                                   error=mode == "quota", delay=10 if mode in ("timeout", "cancel") else 0)
                page = AsyncMock()
                state = {**search.initialize_search({"search_provider": "parallel"}),
                         "input": "query", "page": page}
                with server.transport(), patch.object(search, "SEARCH_TIMEOUT", 0.05 if mode == "timeout" else 30):
                    if mode == "cancel":
                        task = asyncio.create_task(search.go_to_search(state))
                        while not server.calls:
                            await asyncio.sleep(0)
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                    else:
                        with self.assertRaises(TimeoutError if mode == "timeout" else RuntimeError):
                            await search.go_to_search(state)
                page.goto.assert_not_awaited()
                page.set_content.assert_not_awaited()

    def test_result_urls_and_html_are_untrusted(self):
        results = [{"url": url, "title": '<script>alert(1)</script>', "excerpts": ['<img src=x onerror=alert(1)>']}
                   for url in ['javascript:alert(1)', 'file:///etc/passwd', 'https://user:pass@example.com',
                               'https://example.com/\nattack', 'https://[broken', 'https://example.com/?a=1&b=2']]
        html = search.results_html('<query>', results)
        self.assertEqual(html.count('<a href='), 1)
        self.assertIn('https://example.com/?a=1&amp;b=2', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;query&gt;', html)
        self.assertTrue(search.is_google_search('https://www.google.com/search?q=topic'))
        self.assertFalse(search.is_google_search('https://www.google.com/maps'))
        self.assertFalse(search.is_google_search('https://google.com.attacker.example/'))


if __name__ == '__main__':
    unittest.main()
