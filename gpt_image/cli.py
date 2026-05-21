#!/usr/bin/env python3
"""GPT Image CLI — generate images via ChatGPT OAuth without an API key."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import secrets
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

DEFAULT_AUTH_FILE = "~/.gpt-image/auth.json"
DEFAULT_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_AUTH_URL = "https://auth.openai.com"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEVICE_CALLBACK = f"{OPENAI_AUTH_URL}/deviceauth/callback"

DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_RESPONSES_MODEL = "gpt-5.5"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "high"
DEFAULT_FORMAT = "png"
DEFAULT_TIMEOUT = 180
DEFAULT_COUNT = 1
MAX_COUNT = 4
MAX_INPUT_IMAGES = 5
MAX_BYTES = 64 * 1024 * 1024

SUPPORTED_QUALITIES = {"low", "medium", "high", "auto"}
SUPPORTED_FORMATS = {"png", "jpeg", "jpg", "webp"}
SUPPORTED_BACKGROUNDS = {"transparent", "opaque", "auto"}
SUPPORTED_DETAILS = {"low", "high", "auto", "original"}
SUPPORTED_ACTIONS = {"generate", "edit", "auto"}
SUPPORTED_FIDELITIES = {"low", "high"}
SUPPORTED_MODERATIONS = {"auto", "low"}

GPT_IMAGE_2_MIN = 655_360
GPT_IMAGE_2_MAX = 8_294_400
GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MAX_RATIO = 3.0


class CliError(RuntimeError):
    pass


@dataclass
class Auth:
    access_token: str
    account_id: str | None = None
    last_refresh: str | None = None


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def die(msg: str, code: int = 1) -> None:
    eprint(f"Error: {msg}")
    raise SystemExit(code)


def auth_path() -> Path:
    return Path(os.getenv("GPT_IMAGE_AUTH_FILE", DEFAULT_AUTH_FILE)).expanduser()


def _headers(content_type: str) -> dict[str, str]:
    return {
        "Content-Type": content_type,
        "User-Agent": "gpt-image/0.2.0",
    }


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=_headers("application/json"),
    )
    return _read_json(req, timeout)


def _post_form(url: str, payload: dict[str, str], timeout: int) -> dict[str, Any]:
    req = request.Request(
        url,
        data=parse.urlencode(payload).encode("utf-8"),
        method="POST",
        headers=_headers("application/x-www-form-urlencoded"),
    )
    return _read_json(req, timeout)


def _read_json(req: request.Request, timeout: int) -> dict[str, Any]:
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            text = resp.read(MAX_BYTES).decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise CliError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise CliError(f"Request failed: {exc.reason}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"Expected JSON, got: {text[:500]}") from exc
    if not isinstance(data, dict):
        raise CliError("Expected JSON object response.")
    return data


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _infer_account_id(access_token: str) -> str | None:
    payload = _decode_jwt_payload(access_token)
    for key in (
        "https://api.openai.com/auth",
        "https://api.openai.com/account_id",
        "account_id",
        "sub",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("account_id") or value.get("accountId")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        __import__("hashlib").sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _start_callback_server(port: int) -> tuple[Any, Any]:
    """Start a minimal HTTP server on localhost:port to receive the OAuth callback."""
    import http.server
    import socketserver
    import threading

    result: dict[str, str | None] = {"code": None, "error": None}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = parse.urlparse(self.path)
            query = parse.parse_qs(parsed.query)
            if parsed.path == "/auth/callback":
                if "code" in query:
                    result["code"] = query["code"][0]
                if "error" in query:
                    result["error"] = query["error"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authentication complete</h2>"
                    b"<p>You can close this window and return to the terminal.</p></body></html>"
                )
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, _fmt, *_args):
            pass

    server = socketserver.TCPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, result


def _request_device_code(timeout: int) -> dict[str, Any]:
    data = _post_json(
        f"{OPENAI_AUTH_URL}/api/accounts/deviceauth/usercode",
        {"client_id": CLIENT_ID},
        timeout,
    )
    device_auth_id = str(data.get("device_auth_id") or "").strip()
    user_code = str(data.get("user_code") or data.get("usercode") or "").strip()
    if not device_auth_id or not user_code:
        raise CliError("Device-code response missing required fields.")
    interval = data.get("interval", 5)
    try:
        interval = max(1, int(interval))
    except (TypeError, ValueError):
        interval = 5
    return {
        "device_auth_id": device_auth_id,
        "user_code": user_code,
        "verification_url": f"{OPENAI_AUTH_URL}/codex/device",
        "interval": interval,
    }


def _poll_device_code(device_code: dict[str, Any], timeout: int) -> dict[str, str]:
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        try:
            data = _post_json(
                f"{OPENAI_AUTH_URL}/api/accounts/deviceauth/token",
                {
                    "device_auth_id": device_code["device_auth_id"],
                    "user_code": device_code["user_code"],
                },
                timeout,
            )
        except CliError as exc:
            if "HTTP 403" in str(exc) or "HTTP 404" in str(exc):
                time.sleep(min(device_code["interval"], max(1, int(deadline - time.time()))))
                continue
            raise
        auth_code = str(data.get("authorization_code") or "").strip()
        code_verifier = str(data.get("code_verifier") or "").strip()
        if not auth_code or not code_verifier:
            raise CliError("Device authorization response missing exchange fields.")
        return {"authorization_code": auth_code, "code_verifier": code_verifier}
    raise CliError("Device authorization timed out after 15 minutes.")


def _exchange_code(authz: dict[str, str], timeout: int) -> dict[str, Any]:
    data = _post_form(
        f"{OPENAI_AUTH_URL}/oauth/token",
        {
            "grant_type": "authorization_code",
            "code": authz["authorization_code"],
            "redirect_uri": DEVICE_CALLBACK,
            "client_id": CLIENT_ID,
            "code_verifier": authz["code_verifier"],
        },
        timeout,
    )
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    if not isinstance(access, str) or not access.strip():
        raise CliError("Token exchange succeeded but did not return access_token.")
    if not isinstance(refresh, str) or not refresh.strip():
        raise CliError("Token exchange succeeded but did not return refresh_token.")
    return data


def _write_auth(tokens: dict[str, Any]) -> Path:
    path = auth_path()
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}
    access = str(tokens["access_token"]).strip()
    refresh = str(tokens["refresh_token"]).strip()
    account_id = _infer_account_id(access)
    existing["auth_mode"] = existing.get("auth_mode") or "chatgpt"
    existing["last_refresh"] = datetime.now(timezone.utc).isoformat()
    existing["tokens"] = {
        "access_token": access,
        "refresh_token": refresh,
        **({"id_token": tokens["id_token"]} if isinstance(tokens.get("id_token"), str) else {}),
        **({"account_id": account_id} if account_id else {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _load_auth() -> Auth:
    path = auth_path()
    if not path.exists():
        raise CliError(f"Auth file not found: {path}. Run `gpt-image login` first.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"Auth file is not valid JSON: {path}") from exc
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        raise CliError(f"Auth file has no tokens object: {path}")
    token = tokens.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise CliError(f"Access token missing in {path}. Run `gpt-image login` again.")
    account_id = tokens.get("account_id")
    return Auth(
        access_token=token.strip(),
        account_id=account_id if isinstance(account_id, str) else None,
        last_refresh=data.get("last_refresh") if isinstance(data.get("last_refresh"), str) else None,
    )


def _load_or_login(args: argparse.Namespace) -> Auth:
    try:
        return _load_auth()
    except CliError:
        if getattr(args, "login_if_missing", False):
            return _cmd_login(args)
        raise


def _redact(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def _canonicalize_base_url(base_url: str | None) -> str:
    raw = (base_url or os.getenv("GPT_IMAGE_BASE_URL") or DEFAULT_BASE_URL).strip()
    if not raw:
        return DEFAULT_BASE_URL
    return raw.rstrip("/")


def _response_url(base_url: str | None) -> str:
    return f"{_canonicalize_base_url(base_url)}/responses"


def _read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt and prompt_file:
        raise CliError("Use --prompt or --prompt-file, not both.")
    if prompt_file:
        text = Path(prompt_file).read_text(encoding="utf-8").strip()
    elif prompt:
        text = prompt.strip()
    else:
        raise CliError("Missing prompt. Use --prompt or --prompt-file.")
    if not text:
        raise CliError("Prompt is empty.")
    return text


def _normalize_format(value: str | None) -> str:
    fmt = (value or DEFAULT_FORMAT).lower()
    if fmt not in SUPPORTED_FORMATS:
        raise CliError("output format must be png, jpeg, jpg, or webp.")
    return "jpeg" if fmt == "jpg" else fmt


def _validate_quality(value: str) -> None:
    if value not in SUPPORTED_QUALITIES:
        raise CliError("quality must be low, medium, high, or auto.")


def _validate_background(value: str | None) -> None:
    if value is not None and value not in SUPPORTED_BACKGROUNDS:
        raise CliError("background must be transparent, opaque, or auto.")


def _validate_detail(value: str) -> None:
    if value not in SUPPORTED_DETAILS:
        raise CliError("detail must be low, high, auto, or original.")


def _validate_action(value: str | None) -> None:
    if value is not None and value not in SUPPORTED_ACTIONS:
        raise CliError("action must be generate, edit, or auto.")


def _validate_input_fidelity(value: str | None) -> None:
    if value is not None and value not in SUPPORTED_FIDELITIES:
        raise CliError("input-fidelity must be low or high.")


def _validate_moderation(value: str | None) -> None:
    if value is not None and value not in SUPPORTED_MODERATIONS:
        raise CliError("moderation must be auto or low.")


def _validate_partial_images(value: int | None) -> None:
    if value is not None and (value < 0 or value > 3):
        raise CliError("partial-images must be between 0 and 3.")


def _parse_size(value: str) -> tuple[int, int] | None:
    import re
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _validate_size(size: str, model: str) -> None:
    if size == "auto":
        return
    parsed = _parse_size(size)
    if parsed is None:
        raise CliError("size must be auto or WIDTHxHEIGHT, for example 1024x1024.")
    width, height = parsed
    if "gpt-image-2" not in model:
        if size not in {"1024x1024", "1536x1024", "1024x1536"}:
            raise CliError("this image model only supports 1024x1024, 1536x1024, 1024x1536, or auto.")
        return
    max_edge = max(width, height)
    min_edge = min(width, height)
    pixels = width * height
    if max_edge > GPT_IMAGE_2_MAX_EDGE:
        raise CliError("gpt-image-2 max edge must be <= 3840.")
    if width % 16 != 0 or height % 16 != 0:
        raise CliError("gpt-image-2 width and height must be multiples of 16.")
    if max_edge / min_edge > GPT_IMAGE_2_MAX_RATIO:
        raise CliError("gpt-image-2 long-to-short ratio must be <= 3:1.")
    if pixels < GPT_IMAGE_2_MIN or pixels > GPT_IMAGE_2_MAX:
        raise CliError("gpt-image-2 total pixels must be between 655,360 and 8,294,400.")


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return mime
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _image_to_data_url(path: Path) -> str:
    if not path.exists():
        raise CliError(f"Input image not found: {path}")
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{_guess_mime(path)};base64,{encoded}"


def _build_content(prompt: str, image_paths: list[str], detail: str) -> list[dict[str, Any]]:
    if len(image_paths) > MAX_INPUT_IMAGES:
        raise CliError(f"At most {MAX_INPUT_IMAGES} input images are supported.")
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for raw in image_paths:
        content.append({
            "type": "input_image",
            "image_url": _image_to_data_url(Path(raw)),
            "detail": detail,
        })
    return content


def _build_body(args: argparse.Namespace, prompt: str, image_paths: list[str]) -> dict[str, Any]:
    image_model = args.model
    if args.background == "transparent" and image_model == DEFAULT_IMAGE_MODEL:
        image_model = "gpt-image-1.5"
    _validate_quality(args.quality)
    _validate_background(args.background)
    _validate_size(args.size, image_model)
    _validate_detail(args.detail)
    _validate_action(args.action)
    _validate_input_fidelity(args.input_fidelity)
    _validate_moderation(args.moderation)
    _validate_partial_images(args.partial_images)

    tool: dict[str, Any] = {
        "type": "image_generation",
        "model": image_model,
        "size": args.size,
        "quality": args.quality,
    }
    if args.output_format:
        tool["output_format"] = _normalize_format(args.output_format)
    if args.background:
        tool["background"] = args.background
    if args.action:
        tool["action"] = args.action
    if args.input_fidelity:
        tool["input_fidelity"] = args.input_fidelity
    if args.moderation:
        tool["moderation"] = args.moderation
    if args.partial_images is not None:
        tool["partial_images"] = args.partial_images
    if args.output_compression is not None:
        tool["output_compression"] = args.output_compression
    if args.input_image_mask:
        tool["input_image_mask"] = {"image_url": _image_to_data_url(Path(args.input_image_mask))}

    return {
        "model": args.responses_model,
        "input": [{"role": "user", "content": _build_content(prompt, image_paths, args.detail)}],
        "instructions": "You are an image generation assistant.",
        "tools": [tool],
        "tool_choice": {"type": "image_generation"},
        "stream": True,
        "store": False,
    }


def _post_sse(url: str, token: str, body: dict[str, Any], timeout: int) -> str:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "gpt-image/0.2.0",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(1024 * 64)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise CliError("Response exceeded size limit.")
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise CliError(f"Request failed (HTTP {exc.code}): {detail}") from exc
    except error.URLError as exc:
        raise CliError(f"Request failed: {exc.reason}") from exc


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _extract_images(body: str) -> list[tuple[str, str | None]]:
    events = _parse_sse(body)
    for event in events:
        if event.get("type") in {"response.failed", "error"}:
            error_obj = event.get("error")
            if isinstance(error_obj, dict):
                message = error_obj.get("message") or error_obj.get("code")
            else:
                message = event.get("message")
            raise CliError(str(message or "Image generation failed."))

    payloads: list[tuple[str, str | None]] = []
    for event in events:
        item = event.get("item")
        if (
            event.get("type") == "response.output_item.done"
            and isinstance(item, dict)
            and item.get("type") == "image_generation_call"
            and isinstance(item.get("result"), str)
        ):
            payloads.append((item["result"], item.get("revised_prompt")))

    if payloads:
        return payloads

    for event in events:
        if event.get("type") != "response.completed":
            continue
        response_obj = event.get("response")
        output = response_obj.get("output") if isinstance(response_obj, dict) else None
        if not isinstance(output, list):
            continue
        for item in output:
            if (
                isinstance(item, dict)
                and item.get("type") == "image_generation_call"
                and isinstance(item.get("result"), str)
            ):
                payloads.append((item["result"], item.get("revised_prompt")))
    return payloads


def _write_images(payloads: list[tuple[str, str | None]], out: str, output_format: str) -> list[Path]:
    if not payloads:
        raise CliError("No image payload found in response.")
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if output_format == "jpeg" else output_format
    multi = len(payloads) > 1
    written: list[Path] = []
    for index, (payload, _revised) in enumerate(payloads, start=1):
        data = base64.b64decode(payload)
        path = target
        if multi:
            stem = target.stem or "image"
            suffix = target.suffix or f".{ext}"
            path = target.with_name(f"{stem}-{index:02d}{suffix}")
        path.write_bytes(data)
        written.append(path)
    return written


# Commands

def _cmd_login(args: argparse.Namespace) -> Auth:
    if getattr(args, "device_code", False):
        return _cmd_login_device_code(args)

    # Web redirect flow (default): click URL → click Connect → token flows back
    # Uses the same localhost:1455 redirect that Codex CLI registers with OpenAI.
    FIXED_PORT = 1455
    redirect_uri = f"http://localhost:{FIXED_PORT}/auth/callback"

    verifier, challenge = _generate_pkce()
    state = base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode("ascii")

    auth_url = (
        f"{OPENAI_AUTH_URL}/oauth/authorize?"
        + parse.urlencode({
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email offline_access api.connectors.read api.connectors.invoke",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "codex_cli_rs",
        })
    )

    server, result = _start_callback_server(FIXED_PORT)
    try:
        print()
        print("Opening browser for ChatGPT authentication...")
        print(f"If it doesn't open automatically, visit:\n  {auth_url}")
        print()
        if args.open_browser:
            try:
                webbrowser.open(auth_url)
            except Exception:
                eprint("Could not open browser automatically.")

        deadline = time.time() + 5 * 60
        while time.time() < deadline:
            if result["code"]:
                break
            if result["error"]:
                raise CliError(f"OAuth error: {result['error']}")
            time.sleep(0.2)
        else:
            raise CliError("Browser authentication timed out after 5 minutes.")

        auth_code = result["code"]
        eprint("Exchanging authorization code for tokens...")
        data = _post_form(
            f"{OPENAI_AUTH_URL}/oauth/token",
            {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": redirect_uri,
                "client_id": CLIENT_ID,
                "code_verifier": verifier,
            },
            args.timeout,
        )
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        if not isinstance(access, str) or not access.strip():
            raise CliError("Token exchange succeeded but did not return access_token.")
        if not isinstance(refresh, str) or not refresh.strip():
            raise CliError("Token exchange succeeded but did not return refresh_token.")
        path = _write_auth(data)
        eprint(f"Auth saved to {path}.")
        return _load_auth()
    finally:
        server.shutdown()


def _cmd_login_device_code(args: argparse.Namespace) -> Auth:
    eprint("Requesting device code...")
    device_code = _request_device_code(args.timeout)
    print()
    print("Open this URL in your browser and enter the code:")
    print(f"  URL:  {device_code['verification_url']}")
    print(f"  Code: {device_code['user_code']}")
    print("The code expires in about 15 minutes. Never share it.")
    print()
    if args.open_browser:
        try:
            webbrowser.open(device_code["verification_url"])
        except Exception:
            eprint(f"Could not open browser. Open manually: {device_code['verification_url']}")
    eprint("Waiting for browser authorization...")
    authz = _poll_device_code(device_code, args.timeout)
    eprint("Exchanging device code for tokens...")
    tokens = _exchange_code(authz, args.timeout)
    path = _write_auth(tokens)
    eprint(f"Auth saved to {path}.")
    return _load_auth()


def cmd_auth_status(args: argparse.Namespace) -> int:
    auth = _load_or_login(args)
    payload = {
        "auth_file": str(auth_path()),
        "has_access_token": True,
        "account_id": _redact(auth.account_id),
        "last_refresh": auth.last_refresh,
        "base_url": _canonicalize_base_url(args.base_url),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("GPT Image auth is available.")
        print(f"Auth file: {payload['auth_file']}")
        if payload["account_id"]:
            print(f"Account: {payload['account_id']}")
        if payload["last_refresh"]:
            print(f"Last refresh: {payload['last_refresh']}")
        print(f"Responses base URL: {payload['base_url']}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    prompt = _read_prompt(args.prompt, args.prompt_file)
    image_paths = (args.image or []) + (args.reference_image or [])
    if args.count < 1 or args.count > MAX_COUNT:
        raise CliError(f"--count must be between 1 and {MAX_COUNT}.")
    output_format = _normalize_format(args.output_format)
    url = _response_url(args.base_url)
    body = _build_body(args, prompt, image_paths)
    if args.dry_run:
        summary = {
            "url": url,
            "auth": "ChatGPT OAuth access token from local auth file",
            "responses_model": body["model"],
            "image_model": body["tools"][0]["model"],
            "size": body["tools"][0]["size"],
            "quality": body["tools"][0].get("quality"),
            "output_format": output_format,
            "input_images": len(image_paths),
            "count": args.count,
        }
        if args.action:
            summary["action"] = args.action
        if args.input_fidelity:
            summary["input_fidelity"] = args.input_fidelity
        if args.moderation:
            summary["moderation"] = args.moderation
        if args.partial_images is not None:
            summary["partial_images"] = args.partial_images
        if args.output_compression is not None:
            summary["output_compression"] = args.output_compression
        if args.input_image_mask:
            summary["input_image_mask"] = args.input_image_mask
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    auth = _load_or_login(args)
    all_payloads: list[tuple[str, str | None]] = []
    start = time.time()
    for _ in range(args.count):
        text = _post_sse(url, auth.access_token, dict(body), args.timeout)
        all_payloads.extend(_extract_images(text))
    written = _write_images(all_payloads, args.out, output_format)
    for path in written:
        print(path)
    eprint(f"Generated {len(written)} image(s) in {time.time() - start:.1f}s.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate images with GPT Image 2 via ChatGPT OAuth — no API key needed.",
        prog="gpt-image",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth-status", help="Check whether local auth is available.")
    auth.add_argument("--base-url", default=None)
    auth.add_argument("--login-if-missing", action="store_true")
    auth.add_argument("--open-browser", action="store_true")
    auth.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    auth.add_argument("--json", action="store_true")
    auth.set_defaults(func=cmd_auth_status)

    login = sub.add_parser("login", help="Run ChatGPT OAuth login and save auth.")
    login.add_argument("--open-browser", action="store_true")
    login.add_argument("--device-code", action="store_true", help="Use device-code flow for headless environments.")
    login.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    login.set_defaults(func=lambda args: 0 if _cmd_login(args) else 1)

    gen = sub.add_parser("generate", help="Generate or edit an image.")
    gen.add_argument("--prompt", "-p")
    gen.add_argument("--prompt-file")
    gen.add_argument("--image", "-i", action="append", help="Input image path (edit target or reference). Repeatable.")
    gen.add_argument("--reference-image", "-r", action="append", help="Reference image path for style/content guidance. Repeatable. (Same API mechanism as --image.)")
    gen.add_argument("--detail", default="high", choices=sorted(SUPPORTED_DETAILS), help="Detail level for input images. Default: high (matches Codex CLI default).")
    gen.add_argument("--action", choices=sorted(SUPPORTED_ACTIONS), help="Whether to generate a new image or edit an existing one. Default: auto.")
    gen.add_argument("--input-fidelity", choices=sorted(SUPPORTED_FIDELITIES), help="How strongly to preserve details from input images. Only supported for gpt-image-1/1.5.")
    gen.add_argument("--moderation", choices=sorted(SUPPORTED_MODERATIONS), help="Moderation level for generated images. Default: auto.")
    gen.add_argument("--partial-images", type=int, help="Number of partial images to stream (0-3). Default: 0.")
    gen.add_argument("--output-compression", type=int, help="Output compression level (0-100). Default: 100.")
    gen.add_argument("--input-image-mask", help="Path to a mask image for inpainting/editing.")
    gen.add_argument("--out", "-o", default="output.png")
    gen.add_argument("--model", default=os.getenv("GPT_IMAGE_MODEL", DEFAULT_IMAGE_MODEL))
    gen.add_argument("--responses-model", default=os.getenv("GPT_IMAGE_RESPONSES_MODEL", DEFAULT_RESPONSES_MODEL))
    gen.add_argument("--size", default=DEFAULT_SIZE)
    gen.add_argument("--quality", default=DEFAULT_QUALITY)
    gen.add_argument("--output-format", default=DEFAULT_FORMAT)
    gen.add_argument("--background", choices=sorted(SUPPORTED_BACKGROUNDS))
    gen.add_argument("--count", type=int, default=DEFAULT_COUNT)
    gen.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    gen.add_argument("--base-url", default=None)
    gen.add_argument("--login-if-missing", action="store_true")
    gen.add_argument("--open-browser", action="store_true")
    gen.add_argument("--dry-run", action="store_true")
    gen.set_defaults(func=cmd_generate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except CliError as exc:
        die(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
