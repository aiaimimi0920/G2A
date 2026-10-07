"""仅回环地址的 HTTP+JSON 参考绑定，不是生产互联网服务器。"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit

from .validation import ProtocolError, validate


MAX_BODY = 65536


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("Non-finite JSON number")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def handler_for(host):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            # 不在默认日志中写入会话路径、请求正文或 Authorization。
            pass

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def dispatch(self, method):
            try:
                if self.headers.get("Origin"):
                    raise ProtocolError("origin_denied", "Browser origins are not enabled", 403)
                url = urlsplit(self.path)
                if url.scheme or url.netloc or url.fragment:
                    raise ProtocolError("invalid_route", "Relative request target required")
                parts = url.path.strip("/").split("/")
                token = self.headers.get("Authorization", "")
                token = token[7:] if token.startswith("Bearer ") else ""
                if method == "GET" and url.path == "/.well-known/g2a.json" and not url.query:
                    with host.lock:
                        result = dict(host.descriptor)
                elif method == "POST" and url.path == "/sessions" and not url.query:
                    result = host.join(token, self.body())
                elif len(parts) >= 3 and parts[0] == "sessions":
                    sid = parts[1]
                    # 路径存在性和载荷解析前检查凭据。
                    with host.lock:
                        host.authorize(sid, token)
                    if method == "GET" and len(parts) == 3 and parts[2] == "events":
                        query = parse_qs(url.query, keep_blank_values=True)
                        if set(query) - {"cursor"} or len(query.get("cursor", ["0"])) != 1:
                            raise ProtocolError("invalid_cursor", "One cursor is allowed")
                        cursor = query.get("cursor", ["0"])[0]
                        if not cursor.isascii() or not cursor.isdecimal() or len(cursor) > 10:
                            raise ProtocolError("invalid_cursor", "Cursor must be a nonnegative integer")
                        result = host.poll(sid, token, int(cursor))
                    elif method == "POST" and len(parts) == 3 and parts[2] == "events" and not url.query:
                        result = host.send(sid, token, self.body())
                    elif method == "POST" and len(parts) == 3 and parts[2] == "leave" and not url.query:
                        body = validate("leave", self.body())
                        result = host.leave(sid, token, body["reason"])
                    elif method == "POST" and len(parts) == 5 and parts[2] == "actions" and parts[4] == "claim" and not url.query:
                        if self.body() != {}:
                            raise ProtocolError("invalid_message", "Claim body must be empty")
                        result = host.claim_action(sid, token, parts[3])
                    elif method == "GET" and len(parts) == 4 and parts[2] == "actions" and not url.query:
                        result = host.get_action(sid, token, parts[3])
                    else:
                        raise ProtocolError("not_found", "Unknown operation", 404)
                else:
                    raise ProtocolError("not_found", "Unknown operation", 404)
                self.reply(200, result)
            except ProtocolError as error:
                self.reply(error.status, error.as_dict())
            except (ValueError, UnicodeError, RecursionError):
                self.reply(400, ProtocolError("invalid_message", "Invalid JSON or request parameter").as_dict())
            except (TimeoutError, ConnectionError, BrokenPipeError):
                self.close_connection = True

        def body(self):
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Encoding"):
                raise ProtocolError("unsupported_encoding", "Encoded or chunked request bodies are not supported", 415)
            if self.headers.get_content_type() != "application/json":
                raise ProtocolError("unsupported_media_type", "Use application/json", 415)
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                raise ProtocolError("invalid_length", "One Content-Length is required", 411)
            size = int(lengths[0])
            if size > MAX_BODY:
                raise ProtocolError("message_too_large", "Request exceeds binding size limit", 413)
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ProtocolError("invalid_length", "Truncated request body")
            return strict_json(raw)

        def reply(self, status, value):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

    return Handler


@contextmanager
def serve(host):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(host))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
