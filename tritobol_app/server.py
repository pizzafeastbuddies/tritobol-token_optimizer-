
"""Flask application: a thin, local-only HTTP layer over the tritobol engine."""

from __future__ import annotations

import hmac
import html
import logging
import os
import secrets as pysecrets
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, Response, jsonify, request, session
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from . import __version__
from .accounts import CREATED_MESSAGE, AccountStore, password_tag, public_user
from .export import export_text
from .files import decode_text_upload
from .schemas import MAX_INPUT_BYTES, MAX_TOKENIZER_BYTES, AppError, parse_optimize_request
from .service import TokenizerRegistry, run_optimization

STATIC_DIR = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
# Allow overriding the localhost-only check via environment variable.
# Set TRITOBOL_LOCAL_ONLY=0 to accept requests from any host (e.g. when deployed
# behind a reverse proxy or on a public server).
# Disable local-only host check only when env var is explicitly set to 0 or false.
# Default (not set or any other value): keep localhost-only guard active.
_DisableLocalOnly = os.environ.get("TRITOBOL_LOCAL_ONLY", None) in ("0", "false", "False", "")
if _DisableLocalOnly:
    LOCAL_HOSTS = set()  # disable the host guard entirely
JSON_BODY_LIMIT = 12 * 1024 * 1024
log = logging.getLogger("tritobol_app")


def _host_only(host: str) -> str:
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.split(":")[0]


def _database_path(config: Dict[str, Any]) -> Path:
    configured = config.get("DATABASE_PATH") or os.environ.get("TRITOBOL_DB") or ""
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / "data" / "tritobol.sqlite"


def _load_or_create_secret_key(database_path: Path) -> str:
    """Load a persistent local session key, creating it on first startup."""
    secret_path = database_path.parent / ".secret_key"
    secret_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        existing = secret_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    except FileNotFoundError:
        pass

    generated = pysecrets.token_hex(32)

    try:
        with secret_path.open("x", encoding="utf-8") as secret_file:
            secret_file.write(generated + "\n")
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
        return generated
    except FileExistsError:
        existing = secret_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
        raise RuntimeError("The local session secret file is invalid.")


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_TOKENIZER_BYTES + 2 * 1024 * 1024
    app.config["TRITOBOL_TOKEN"] = pysecrets.token_urlsafe(24)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("TRITOBOL_COOKIE_SECURE") == "1"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    if test_config:
        app.config.update(test_config)

    database_path = _database_path(app.config)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = (
            os.environ.get("TRITOBOL_SECRET_KEY")
            or _load_or_create_secret_key(database_path)
        )

    accounts = AccountStore(database_path)
    app.extensions["tritobol_accounts"] = accounts

    registry = TokenizerRegistry()
    app.extensions["tritobol_registry"] = registry

    # ---------------------------------------------------------------- guards
    @app.before_request
    def guard():
        # Skip host-origin check if local-only mode is disabled.
        if LOCAL_HOSTS and _host_only(request.host.lower()) not in LOCAL_HOSTS:
            raise AppError(
                "forbidden",
                "This app only answers requests addressed to localhost.",
                status=403,
            )

        if request.method == "POST":
            origin = request.headers.get("Origin")
            if LOCAL_HOSTS and origin and _host_only(origin.split("://", 1)[-1].lower()) not in LOCAL_HOSTS:
                raise AppError(
                    "forbidden",
                    "Cross-site requests are not allowed.",
                    status=403,
                )

            token = request.headers.get("X-Tritobol-Token", "")
            if not hmac.compare_digest(token, app.config["TRITOBOL_TOKEN"]):
                raise AppError(
                    "forbidden",
                    "Missing or invalid session token. Reload the page.",
                    status=403,
                )

    @app.after_request
    def headers(resp: Response) -> Response:
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'none'"
        )

        if (
            request.path.startswith("/api/")
            or request.path == "/"
            or request.path.startswith("/static/")
        ):
            resp.headers["Cache-Control"] = "no-store"

        return resp

    # ---------------------------------------------------------------- errors
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        return jsonify(err.to_dict()), err.status

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_err):
        return (
            jsonify(
                AppError(
                    "input_too_large",
                    "The request is too large for this app.",
                    status=413,
                ).to_dict()
            ),
            413,
        )

    @app.errorhandler(HTTPException)
    def handle_http(err: HTTPException):
        code = "not_found" if err.code == 404 else "validation_error"
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": code,
                        "message": err.description or err.name,
                        "field": None,
                    },
                }
            ),
            err.code or 400,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        log.error("Unhandled %s", type(err).__name__)
        return (
            jsonify(
                AppError(
                    "processing_error",
                    f"Unexpected server error ({type(err).__name__}).",
                    status=500,
                ).to_dict()
            ),
            500,
        )

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        page = page.replace(
            "__TRITOBOL_TOKEN__",
            html.escape(app.config["TRITOBOL_TOKEN"], quote=True),
        )
        return Response(page, mimetype="text/html")

    # ---------------------------------------------------------------- accounts
    def _csrf() -> str:
        token = session.get("csrf_token")

        if not isinstance(token, str) or len(token) < 20:
            token = pysecrets.token_urlsafe(32)
            session["csrf_token"] = token
            session.permanent = True

        return token

    def _check_csrf() -> None:
        expected = session.get("csrf_token") or ""
        sent = request.headers.get("X-CSRF-Token", "")

        if (
            not isinstance(expected, str)
            or not expected
            or not hmac.compare_digest(expected, sent)
        ):
            raise AppError(
                "forbidden",
                "The form token is missing or expired. Reload the page.",
                status=403,
            )

    def _establish(row) -> None:
        session.clear()
        session.permanent = True
        session["user_id"] = row["id"]
        session["pwd_tag"] = password_tag(
            app.config["SECRET_KEY"],
            row["password_hash"],
        )
        session["csrf_token"] = pysecrets.token_urlsafe(32)

    def _current():
        tag = session.get("pwd_tag")

        try:
            user_id = int(session.get("user_id"))
        except (TypeError, ValueError):
            return None

        if not isinstance(tag, str):
            return None

        row = accounts.get(user_id)

        if row is None or not row["is_active"]:
            return None

        if not hmac.compare_digest(
            tag,
            password_tag(app.config["SECRET_KEY"], row["password_hash"]),
        ):
            return None

        return row

    def _require_user():
        row = _current()

        if row is None:
            raise AppError(
                "unauthorized",
                "Sign in to use the workspace.",
                status=401,
            )

        return row

    @app.get("/api/auth/session")
    def auth_session():
        row = _current()

        return jsonify(
            {
                "ok": True,
                "authenticated": row is not None,
                "user": public_user(row) if row is not None else None,
                "csrf_token": _csrf(),
            }
        )

    @app.post("/api/auth/register")
    def auth_register():
        _check_csrf()

        if _current() is not None:
            raise AppError(
                "conflict",
                "You are already signed in.",
                status=409,
            )

        body = _json_body()

        if not isinstance(body, dict):
            raise AppError(
                "validation_error",
                "Request body must be a JSON object.",
            )

        accounts.register(
            body.get("name"),
            body.get("email"),
            body.get("password"),
            body.get("confirm"),
        )

        return jsonify(
            {
                "ok": True,
                "message": CREATED_MESSAGE,
                "email": str(body.get("email") or "").strip().lower(),
            }
        )

    @app.post("/api/auth/login")
    def auth_login():
        _check_csrf()
        body = _json_body()

        if not isinstance(body, dict):
            raise AppError(
                "validation_error",
                "Request body must be a JSON object.",
            )

        row = accounts.authenticate(
            body.get("email"),
            body.get("password"),
            request.remote_addr or "",
        )

        _establish(row)

        return jsonify(
            {
                "ok": True,
                "user": public_user(row),
                "csrf_token": session["csrf_token"],
            }
        )

    @app.post("/api/auth/logout")
    def auth_logout():
        _check_csrf()
        session.clear()

        return jsonify(
            {
                "ok": True,
                "csrf_token": _csrf(),
            }
        )

    @app.post("/api/auth/password")
    def auth_password():
        _check_csrf()
        row = _require_user()
        body = _json_body()

        if not isinstance(body, dict):
            raise AppError(
                "validation_error",
                "Request body must be a JSON object.",
            )

        updated = accounts.change_password(
            row["id"],
            body.get("current_password"),
            body.get("new_password"),
            body.get("confirm"),
        )

        _establish(updated)

        return jsonify(
            {
                "ok": True,
                "user": public_user(updated),
                "csrf_token": session["csrf_token"],
            }
        )

    # ---------------------------------------------------------------- API
    @app.get("/api/health")
    def health():
        entries = registry.list()

        return jsonify(
            {
                "ok": True,
                "app_version": __version__,
                "local_only": True,
                "bundled_tokenizer_available": entries[0]["available"],
                "max_input_bytes": MAX_INPUT_BYTES,
            }
        )

    @app.get("/api/tokenizers")
    def tokenizers():
        return jsonify(
            {
                "ok": True,
                "tokenizers": registry.list(),
            }
        )

    def _upload(field: str = "file"):
        if (
            request.content_length is not None
            and request.content_length > app.config["MAX_CONTENT_LENGTH"]
        ):
            raise AppError(
                "input_too_large",
                "The upload is too large.",
                status=413,
            )

        file = request.files.get(field)

        if file is None:
            raise AppError(
                "validation_error",
                "No file was uploaded (expected form field 'file').",
                field="file",
            )

        return file

    @app.post("/api/tokenizers/upload")
    def upload_tokenizer():
        _require_user()
        file = _upload()
        data = file.stream.read(MAX_TOKENIZER_BYTES + 1)
        entry = registry.add_custom(file.filename or "", data)

        return jsonify(
            {
                "ok": True,
                "tokenizer": entry,
                "tokenizers": registry.list(),
            }
        )

    @app.post("/api/load-file")
    def load_file():
        _require_user()
        file = _upload()
        data = file.stream.read(MAX_INPUT_BYTES + 1)

        return jsonify(
            {
                "ok": True,
                **decode_text_upload(file.filename or "", data),
            }
        )

    def _json_body() -> Any:
        if (
            request.content_length is not None
            and request.content_length > JSON_BODY_LIMIT
        ):
            raise AppError(
                "input_too_large",
                "The request body is too large.",
                status=413,
            )

        payload = request.get_json(silent=True)

        if payload is None:
            raise AppError(
                "validation_error",
                "Request body must be valid JSON (Content-Type: application/json).",
            )

        return payload

    @app.post("/api/optimize")
    def optimize():
        _require_user()
        req = parse_optimize_request(_json_body())

        return jsonify(
            {
                "ok": True,
                "result": run_optimization(req, registry),
            }
        )

    @app.post("/api/export")
    def export():
        _require_user()
        payload = _json_body()

        if not isinstance(payload, dict):
            raise AppError(
                "validation_error",
                "Request body must be a JSON object.",
            )

        saved = export_text(
            payload.get("text"),
            payload.get("filename"),
            payload.get("directory"),
        )

        return jsonify(
            {
                "ok": True,
                "export": saved,
            }
        )

    return app