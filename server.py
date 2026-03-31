#!/usr/bin/env python3

import json
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ips_api import ApiError, ScopusClient, _ips_row_to_csv_dict, build_scopus_tables


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "IpsApiPrototype/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/scopus/ips-table":
            self._handle_scopus_ips(parsed.query)
            return
        if parsed.path == "/api/scopus/detailed-table":
            self._handle_scopus_detailed(parsed.query)
            return
        if parsed.path == "/api/scopus/author-search":
            self._handle_scopus_author_search(parsed.query)
            return
        self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        return

    def _handle_scopus_ips(self, query_string: str) -> None:
        params = parse_qs(query_string)
        try:
            author_id = _first(params, "author_id")
            researcher_name = _first(params, "researcher_name")
            ssd = _first(params, "ssd")
            start_year = int(_first(params, "start_year", "2022"))
            end_year = int(_first(params, "end_year", "2026"))
            ips_rows, _ = build_scopus_tables(author_id, researcher_name, ssd, start_year, end_year)
            payload = [_ips_row_to_csv_dict(item) for item in ips_rows]
            self._send_json(payload)
        except (ApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_scopus_detailed(self, query_string: str) -> None:
        params = parse_qs(query_string)
        try:
            author_id = _first(params, "author_id")
            researcher_name = _first(params, "researcher_name")
            ssd = _first(params, "ssd")
            start_year = int(_first(params, "start_year", "2022"))
            end_year = int(_first(params, "end_year", "2026"))
            _, detailed_rows = build_scopus_tables(author_id, researcher_name, ssd, start_year, end_year)
            payload = [asdict(item) for item in detailed_rows]
            self._send_json(payload)
        except (ApiError, ValueError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_scopus_author_search(self, query_string: str) -> None:
        params = parse_qs(query_string)
        try:
            query = _first(params, "query")
            count = int(_first(params, "count", "10"))
            start = int(_first(params, "start", "0"))
            client = ScopusClient(os.environ["SCOPUS_API_KEY"], os.getenv("SCOPUS_INSTTOKEN"))
            payload = client.author_search(query=query, count=count, start=start)
            normalized = [asdict(item) for item in client.normalize_author_search(payload)]
            self._send_json(normalized)
        except (ApiError, ValueError, KeyError) as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def _first(params: dict[str, list[str]], key: str, default: str | None = None) -> str:
    values = params.get(key)
    if values and values[0]:
        return values[0]
    if default is not None:
        return default
    raise ValueError(f"Missing required query parameter: {key}")


def main() -> int:
    host = os.getenv("IPS_API_HOST", "127.0.0.1")
    port = int(os.getenv("IPS_API_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"http://{host}:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
