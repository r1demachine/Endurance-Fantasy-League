"""Secure outbound adapters for user-selected personal-analysis providers."""
from __future__ import annotations

import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit, urlunsplit
from typing import Any

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend, SyncStream

from .personal_interpretation import (
    PERSONAL_INTERPRETATION_JSON_SCHEMA,
    SYSTEM_PROMPT,
    PersonalInterpretation,
    PersonalInterpretationError,
    _model_input,
    _validate_interpretation_claims,
)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
MAX_PROVIDER_RESPONSE_BYTES = 256 * 1024
MAX_PROVIDER_TIMEOUT_SECONDS = 30.0
MAX_API_KEY_LENGTH = 512
MAX_MODEL_LENGTH = 120


def _normalise_ip(value: str):
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _is_public_ip(address) -> bool:
    return address.is_global and not (
        address.is_private or address.is_loopback or address.is_link_local
        or address.is_multicast or address.is_reserved or address.is_unspecified
    )


def resolve_public_addresses(host: str) -> tuple[str, ...]:
    """Resolve a host and reject it if any A/AAAA answer is not globally routable."""
    host = host.rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise ValueError("unsafe_host")
    try:
        literal = _normalise_ip(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public_ip(literal):
            raise ValueError("unsafe_ip")
        return (str(literal),)
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:
        raise ValueError("dns_resolution_failed") from exc
    addresses = set()
    for record in records:
        try:
            address = _normalise_ip(record[4][0])
        except (ValueError, IndexError, TypeError) as exc:
            raise ValueError("dns_resolution_failed") from exc
        if not _is_public_ip(address):
            raise ValueError("unsafe_ip")
        addresses.add(str(address))
    if not addresses:
        raise ValueError("dns_resolution_failed")
    return tuple(sorted(addresses))


def validate_provider_base_url(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise ValueError("invalid_base_url")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid_base_url") from exc
    if (
        parsed.scheme.lower() != "https" or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or port not in (None, 443) or parsed.query or parsed.fragment
    ):
        raise ValueError("invalid_base_url")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("unsafe_host")
    try:
        literal = _normalise_ip(host)
    except ValueError:
        literal = None
    if literal is not None and not _is_public_ip(literal):
        raise ValueError("unsafe_ip")
    return urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))


class _PinnedNetworkBackend(SyncBackend):
    """Connect to checked IPs while httpcore retains the hostname for TLS SNI."""
    def __init__(self, hostname: str, addresses: tuple[str, ...]):
        self.hostname = hostname
        self.addresses = set(addresses)

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if str(host).rstrip(".").lower() != self.hostname or port != 443:
            raise httpcore.ConnectError("destination_not_approved")
        current = set(resolve_public_addresses(self.hostname))
        if not current or not current.issubset(self.addresses):
            raise httpcore.ConnectError("dns_changed_after_validation")
        last_error = None
        for address in sorted(current):
            try:
                sock = socket.create_connection((address, port), timeout=timeout)
                for option in socket_options or ():
                    sock.setsockopt(*option)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                return SyncStream(sock)
            except OSError as exc:
                last_error = exc
        raise httpcore.ConnectError("public_destination_unavailable") from last_error


class _CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    def __iter__(self):
        yield from self.stream

    def close(self):
        self.stream.close()


class _PinnedHttpxTransport(httpx.BaseTransport):
    def __init__(self, hostname: str, addresses: tuple[str, ...]):
        self.pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=1,
            max_keepalive_connections=0,
            network_backend=_PinnedNetworkBackend(hostname, addresses),
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.scheme, host=request.url.host,
                port=request.url.port, target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.read(),
            extensions=request.extensions,
        )
        response = self.pool.handle_request(core_request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(response.stream),
            extensions=response.extensions,
            request=request,
        )

    def close(self):
        self.pool.close()


def _request_json(url: str, *, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
        raise PersonalInterpretationError("Provider URL rejected", category="unsafe_destination")
    try:
        approved = resolve_public_addresses(parsed.hostname)
    except ValueError as exc:
        raise PersonalInterpretationError("Provider destination rejected", category="unsafe_destination") from exc
    timeout = min(max(float(timeout_seconds), 1.0), MAX_PROVIDER_TIMEOUT_SECONDS)
    transport = _PinnedHttpxTransport(parsed.hostname.rstrip(".").lower(), approved)
    headers = {**headers, "Accept-Encoding": "identity"}
    try:
        with httpx.Client(transport=transport, follow_redirects=False, timeout=httpx.Timeout(timeout), trust_env=False) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                if 300 <= response.status_code < 400:
                    raise PersonalInterpretationError("Provider redirect blocked", category="redirect_blocked", upstream_status=response.status_code)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise PersonalInterpretationError("Provider response is not JSON", category="invalid_content_type")
                chunks, total = [], 0
                for chunk in response.iter_raw():
                    total += len(chunk)
                    if total > MAX_PROVIDER_RESPONSE_BYTES:
                        raise PersonalInterpretationError("Provider response too large", category="response_too_large")
                    chunks.append(chunk)
                if response.status_code >= 400:
                    raise PersonalInterpretationError("Provider rejected request", category="upstream_http_error", upstream_status=response.status_code)
                try:
                    decoded = json.loads(b"".join(chunks))
                except (ValueError, TypeError) as exc:
                    raise PersonalInterpretationError("Provider returned invalid JSON", category="invalid_response") from exc
                if not isinstance(decoded, dict):
                    raise PersonalInterpretationError("Provider returned invalid JSON", category="invalid_response")
                return decoded
    except PersonalInterpretationError:
        raise
    except Exception as exc:
        if isinstance(exc, (httpx.TimeoutException, httpcore.TimeoutException, TimeoutError)):
            raise PersonalInterpretationError("Provider timed out", category="timeout") from exc
        raise PersonalInterpretationError("Provider request failed", category="connection_error") from exc
    finally:
        transport.close()


def _parse_interpretation(content: str) -> PersonalInterpretation:
    from pydantic import ValidationError
    try:
        decoded = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise PersonalInterpretationError("Provider returned invalid JSON", category="invalid_response") from exc
    try:
        return PersonalInterpretation.model_validate(decoded)
    except ValidationError as exc:
        raise PersonalInterpretationError("Provider returned unexpected schema", category="invalid_schema") from exc


def _openai_content(body: dict[str, Any]) -> str:
    try:
        value = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PersonalInterpretationError("Provider returned invalid response", category="invalid_response") from exc
    if not isinstance(value, str) or not value.strip():
        raise PersonalInterpretationError("Provider returned empty response", category="invalid_response")
    return value


def _anthropic_content(body: dict[str, Any]) -> str:
    try:
        value = next(block["text"] for block in body["content"] if block.get("type") == "text")
    except (KeyError, IndexError, StopIteration, TypeError) as exc:
        raise PersonalInterpretationError("Provider returned invalid response", category="invalid_response") from exc
    if not isinstance(value, str) or not value.strip():
        raise PersonalInterpretationError("Provider returned empty response", category="invalid_response")
    return value


def _openai_request(base_url: str, *, api_key: str, model: str, user_content: str, timeout_seconds: float) -> PersonalInterpretation:
    base = validate_provider_base_url(base_url)
    url = base + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "personal_interpretation", "strict": True, "schema": PERSONAL_INTERPRETATION_JSON_SCHEMA,
        }},
        "max_tokens": 900,
        "temperature": 0.7,
    }
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json", "Accept": "application/json"}
    try:
        body = _request_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)
    except PersonalInterpretationError as exc:
        if exc.upstream_status != 400:
            raise
        payload["messages"][0]["content"] = SYSTEM_PROMPT + "\n\nВерни строго один JSON-объект по указанной схеме, без Markdown и текста вне JSON."
        payload["response_format"] = {"type": "json_object"}
        body = _request_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)
    return _parse_interpretation(_openai_content(body))


def _anthropic_request(*, api_key: str, model: str, user_content: str, timeout_seconds: float) -> PersonalInterpretation:
    body = _request_json(
        ANTHROPIC_MESSAGES_URL,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json", "accept": "application/json"},
        payload={
            "model": model, "max_tokens": 900,
            "system": SYSTEM_PROMPT + "\n\nВерни строго один JSON-объект без Markdown.",
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout_seconds=timeout_seconds,
    )
    return _parse_interpretation(_anthropic_content(body))


def generate_custom_interpretation(trends: dict[str, Any], *, provider: str, api_key: str, model: str, base_url: str | None = None, timeout_seconds: float = 20.0) -> PersonalInterpretation:
    if provider not in {"openai_compatible", "anthropic"}:
        raise PersonalInterpretationError("Provider is not supported", category="invalid_provider")
    if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 512:
        raise PersonalInterpretationError("Provider key is invalid", category="invalid_key")
    if not isinstance(model, str) or not model.strip() or len(model) > 120:
        raise PersonalInterpretationError("Provider model is invalid", category="invalid_model")
    user_content = json.dumps(_model_input(trends), ensure_ascii=False, separators=(",", ":"))
    if provider == "openai_compatible":
        if not base_url:
            raise PersonalInterpretationError("Provider base URL missing", category="invalid_base_url")
        analysis = _openai_request(base_url, api_key=api_key, model=model.strip(), user_content=user_content, timeout_seconds=timeout_seconds)
    else:
        analysis = _anthropic_request(api_key=api_key, model=model.strip(), user_content=user_content, timeout_seconds=timeout_seconds)
    _validate_interpretation_claims(analysis, trends)
    return analysis


def test_custom_provider(*, provider: str, api_key: str, model: str, base_url: str | None = None, timeout_seconds: float = 20.0) -> None:
    """Test a provider with synthetic text only; no personal trend data is sent."""
    if provider not in {"openai_compatible", "anthropic"}:
        raise PersonalInterpretationError("Provider is not supported", category="invalid_provider")
    if not api_key or len(api_key) > 512 or not model or len(model) > 120:
        raise PersonalInterpretationError("Provider configuration invalid", category="invalid_configuration")
    prompt = '{"test":"Return one JSON object with key ok and boolean true."}'
    if provider == "openai_compatible":
        if not base_url:
            raise PersonalInterpretationError("Provider base URL missing", category="invalid_base_url")
        base = validate_provider_base_url(base_url)
        _request_json(base + "/chat/completions", headers={
            "Authorization": "Bearer " + api_key, "Content-Type": "application/json", "Accept": "application/json",
        }, payload={
            "model": model, "messages": [
                {"role": "system", "content": 'Return only JSON: {"ok":true}.'},
                {"role": "user", "content": prompt},
            ], "response_format": {"type": "json_object"}, "max_tokens": 32,
        }, timeout_seconds=timeout_seconds)
    else:
        _request_json(ANTHROPIC_MESSAGES_URL, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json", "accept": "application/json",
        }, payload={
            "model": model, "max_tokens": 32, "system": 'Return only JSON: {"ok":true}.',
            "messages": [{"role": "user", "content": prompt}],
        }, timeout_seconds=timeout_seconds)
