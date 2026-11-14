"""Flask application: a thin, local-only HTTP layer over the tritobol engine."""

from __future__ import annotations

import hmac
import logging
import secrets as pysecrets
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from . import __version__
from .export import export_text
from .files import decode_text_upload
from .schemas import MAX_INPUT_BYTES, MAX_TOKENIZER_BYTES, AppError, parse_optimize_request
from .service import TokenizerRegistry, run_optimization

STATIC_DIR = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
JSON_BODY_LIMIT = 12 * 1024 * 1024
log = logging.getLogger("tritobol_app")


def _host_only(host: str) -> str:
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.split(":")[0]


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_TOKENIZER_BYTES + 2 * 1024 * 1024
    app.config["TRITOBOL_TOKEN"] = pysecrets.token_urlsafe(24)
    if test_config:
        app.config.update(test_config)
    registry = TokenizerRegistry()
    app.extensions["tritobol_registry"] = registry

    # ---------------------------------------------------------------- guards
    @app.before_request
    def guard():
        if _host_only(request.host.lower()) not in LOCAL_HOSTS:
            raise AppError("forbidden", "This app only answers requests addressed to localhost.", status=403)
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and _host_only(origin.split("://", 1)[-1].lower()) not in LOCAL_HOSTS:
                raise AppError("forbidden", "Cross-site requests are not allowed.", status=403)
            token = request.headers.get("X-Tritobol-Token", "")
            if not hmac.compare_digest(token, app.config["TRITOBOL_TOKEN"]):
                raise AppError("forbidden", "Missing or invalid session token. Reload the page.", status=403)

    @app.after_request
    def headers(resp: Response) -> Response:
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.path.startswith("/api/") or request.path == "/":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------------------------------------------------------------- errors
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        return jsonify(err.to_dict()), err.status

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_err):
        return jsonify(AppError("input_too_large", "The request is too large for this app.", status=413).to_dict()), 413

    @app.errorhandler(HTTPException)
    def handle_http(err: HTTPException):
        code = "not_found" if err.code == 404 else "validation_error"
        return jsonify({"ok": False, "error": {"code": code, "message": err.description or err.name, "field": None}}), err.code or 400

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        log.error("Unhandled %s", type(err).__name__)  # never log request bodies
        return jsonify(AppError("processing_error", f"Unexpected server error ({type(err).__name__}).", status=500).to_dict()), 500

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__TRITOBOL_TOKEN__", app.config["TRITOBOL_TOKEN"])
        return Response(html, mimetype="text/html")

    # ---------------------------------------------------------------- API
    @app.get("/api/health")
    def health():
        entries = registry.list()
        return jsonify({"ok": True, "app_version": __version__, "local_only": True,
                        "bundled_tokenizer_available": entries[0]["available"],
                        "max_input_bytes": MAX_INPUT_BYTES})

    @app.get("/api/tokenizers")
    def tokenizers():
        return jsonify({"ok": True, "tokenizers": registry.list()})

    def _upload(field: str = "file"):
        if request.content_length is not None and request.content_length > app.config["MAX_CONTENT_LENGTH"]:
            raise AppError("input_too_large", "The upload is too large.", status=413)
        file = request.files.get(field)
        if file is None:
            raise AppError("validation_error", "No file was uploaded (expected form field 'file').", field="file")
        return file

    @app.post("/api/tokenizers/upload")
    def upload_tokenizer():
        file = _upload()
        data = file.stream.read(MAX_TOKENIZER_BYTES + 1)
        entry = registry.add_custom(file.filename or "", data)
        return jsonify({"ok": True, "tokenizer": entry, "tokenizers": registry.list()})

    @app.post("/api/load-file")
    def load_file():
        file = _upload()
        data = file.stream.read(MAX_INPUT_BYTES + 1)
        return jsonify({"ok": True, **decode_text_upload(file.filename or "", data)})

    def _json_body() -> Any:
        if request.content_length is not None and request.content_length > JSON_BODY_LIMIT:
            raise AppError("input_too_large", "The request body is too large.", status=413)
        payload = request.get_json(silent=True)
        if payload is None:
            raise AppError("validation_error", "Request body must be valid JSON (Content-Type: application/json).")
        return payload

    @app.post("/api/optimize")
    def optimize():
        req = parse_optimize_request(_json_body())
        return jsonify({"ok": True, "result": run_optimization(req, registry)})

    @app.post("/api/export")
    def export():
        payload = _json_body()
        if not isinstance(payload, dict):
            raise AppError("validation_error", "Request body must be a JSON object.")
        saved = export_text(payload.get("text"), payload.get("filename"), payload.get("directory"))
        return jsonify({"ok": True, "export": saved})

    return app
