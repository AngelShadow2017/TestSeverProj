from __future__ import annotations

import base64
import binascii
import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Callable
from urllib.parse import unquote, urlsplit


_TCHAR = set("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _is_valid_header_name(name: str) -> bool:
    return bool(name) and all(ch in _TCHAR for ch in name)


def _validate_no_ctl(value: str) -> bool:
    for ch in value:
        code = ord(ch)
        if code == 0x09:
            continue
        if 0x20 <= code <= 0xFF:
            continue
        return False
    return True


def _split_quoted(value: str, sep: str) -> list[str]:
    parts: list[str] = []
    token: list[str] = []
    in_quote = False
    escape = False
    for ch in value:
        if escape:
            token.append(ch)
            escape = False
            continue
        if in_quote and ch == "\\":
            escape = True
            token.append(ch)
            continue
        if ch == '"':
            in_quote = not in_quote
            token.append(ch)
            continue
        if ch == sep and not in_quote:
            item = "".join(token).strip()
            if item:
                parts.append(item)
            token = []
            continue
        token.append(ch)
    tail = "".join(token).strip()
    if tail:
        parts.append(tail)
    return parts


def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        inner = v[1:-1]
        return inner.replace(r"\"", '"').replace(r"\\", "\\")
    return v


def _parse_http_date(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value.strip())
    except Exception:
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ParsePolicy(str, Enum):
    STRICT = "strict"
    COMPAT = "compat"


class HeaderErrorCode(str, Enum):
    INVALID_HEADER_LINE = "invalid_header_line"
    INVALID_HEADER_NAME = "invalid_header_name"
    INVALID_HEADER_VALUE = "invalid_header_value"
    HOST_REQUIRED = "host_required"
    HOST_INVALID = "host_invalid"
    HOST_DUPLICATE = "host_duplicate"
    CONTENT_LENGTH_INVALID = "content_length_invalid"
    CONTENT_LENGTH_CONFLICT = "content_length_conflict"
    CONTENT_LENGTH_WITH_TRANSFER_ENCODING = "content_length_with_transfer_encoding"
    TRANSFER_ENCODING_INVALID = "transfer_encoding_invalid"
    TRANSFER_ENCODING_NOT_FINAL_CHUNKED = "transfer_encoding_not_final_chunked"
    TRANSFER_ENCODING_UNSUPPORTED = "transfer_encoding_unsupported"
    CONTENT_TYPE_INVALID = "content_type_invalid"
    AUTHORIZATION_INVALID = "authorization_invalid"
    RANGE_INVALID = "range_invalid"
    IF_RANGE_INVALID = "if_range_invalid"
    DATE_INVALID = "date_invalid"


class ConnectionToken(str, Enum):
    CLOSE = "close"
    KEEP_ALIVE = "keep-alive"
    UPGRADE = "upgrade"
    UNKNOWN = "unknown"


class TransferCoding(str, Enum):
    CHUNKED = "chunked"
    GZIP = "gzip"
    DEFLATE = "deflate"
    COMPRESS = "compress"
    BR = "br"
    IDENTITY = "identity"
    UNKNOWN = "unknown"


class AuthScheme(str, Enum):
    BASIC = "basic"
    BEARER = "bearer"
    UNKNOWN = "unknown"


class UpgradeProtocol(str, Enum):
    WEBSOCKET = "websocket"
    H2C = "h2c"
    TLS_1_3 = "tls/1.3"
    UNKNOWN = "unknown"


class FetchSite(str, Enum):
    SAME_ORIGIN = "same-origin"
    SAME_SITE = "same-site"
    CROSS_SITE = "cross-site"
    NONE = "none"
    UNKNOWN = "unknown"


class FetchMode(str, Enum):
    NAVIGATE = "navigate"
    NESTED_NAVIGATE = "nested-navigate"
    NO_CORS = "no-cors"
    CORS = "cors"
    SAME_ORIGIN = "same-origin"
    WEBSOCKET = "websocket"
    UNKNOWN = "unknown"


class FetchUser(str, Enum):
    YES = "?1"
    UNKNOWN = "unknown"


@dataclass
class HeaderIssue:
    code: HeaderErrorCode
    header: str
    message: str
    http_status: int = 400
    fatal: bool = True


@dataclass
class ParseHeaderResult:
    ok: bool
    normalized: Any = None
    issue: HeaderIssue | None = None


@dataclass
class WeightedValue:
    value: str
    q: float = 1.0
    params: dict[str, str] = field(default_factory=dict)
    order: int = 0


@dataclass
class AuthorizationInfo:
    scheme: AuthScheme
    credentials: str
    username: str | None = None
    password: str | None = None


@dataclass
class RangeSpec:
    start: int | None
    end: int | None


@dataclass
class ForwardedElement:
    by: str | None = None
    for_value: str | None = None
    host: str | None = None
    proto: str | None = None


@dataclass
class ParsedHeaders:
    host: str = ""
    port: int | None = None
    content_length: int | None = None
    transfer_codings: list[TransferCoding] = field(default_factory=list)
    transfer_coding_raw: list[str] = field(default_factory=list)
    content_type: str | None = None
    content_type_params: dict[str, str] = field(default_factory=dict)
    connection_tokens: list[ConnectionToken] = field(default_factory=list)
    connection_raw_tokens: list[str] = field(default_factory=list)
    hop_by_hop_headers: set[str] = field(default_factory=set)
    upgrade_tokens: list[UpgradeProtocol] = field(default_factory=list)
    upgrade_raw_tokens: list[str] = field(default_factory=list)
    accept: list[WeightedValue] = field(default_factory=list)
    accept_encoding: list[WeightedValue] = field(default_factory=list)
    accept_language: list[WeightedValue] = field(default_factory=list)
    authorization: AuthorizationInfo | None = None
    cookies: dict[str, str] = field(default_factory=dict)
    range_values: list[RangeSpec] = field(default_factory=list)
    if_range_etag: str | None = None
    if_range_date: datetime | None = None
    if_none_match: list[str] = field(default_factory=list)
    if_match: list[str] = field(default_factory=list)
    if_modified_since: datetime | None = None
    if_unmodified_since: datetime | None = None
    origin: str | None = None
    referer: str | None = None
    user_agent: str | None = None
    x_forwarded_for: list[str] = field(default_factory=list)
    forwarded: list[ForwardedElement] = field(default_factory=list)
    date: datetime | None = None
    expires: datetime | None = None
    retry_after_seconds: int | None = None
    retry_after_date: datetime | None = None
    sec_fetch_site: FetchSite | None = None
    sec_fetch_mode: FetchMode | None = None
    sec_fetch_dest: str | None = None
    sec_fetch_user: FetchUser | None = None


@dataclass
class ResolveResult:
    ok: bool
    parsed: ParsedHeaders
    normalized_map: dict[str, list[str]]
    issues: list[HeaderIssue]


class HeaderResolver:
    def __init__(self, policy: ParsePolicy = ParsePolicy.STRICT, decode_cookie: bool = True):
        self.policy = policy
        self.decode_cookie = decode_cookie
        self.registry: dict[str, Callable[[list[str]], ParseHeaderResult]] = {
            "host": self.parse_host,
            "content-length": self.parse_content_length,
            "transfer-encoding": self.parse_transfer_encoding,
            "content-type": self.parse_content_type,
            "connection": self.parse_connection,
            "upgrade": self.parse_upgrade,
            "accept": self.parse_accept,
            "accept-encoding": self.parse_accept_encoding,
            "accept-language": self.parse_accept_language,
            "authorization": self.parse_authorization,
            "cookie": self.parse_cookie,
            "range": self.parse_range,
            "if-range": self.parse_if_range,
            "if-none-match": self.parse_if_none_match,
            "if-match": self.parse_if_match,
            "if-modified-since": self.parse_if_modified_since,
            "if-unmodified-since": self.parse_if_unmodified_since,
            "origin": self.parse_origin,
            "referer": self.parse_referer,
            "user-agent": self.parse_user_agent,
            "x-forwarded-for": self.parse_x_forwarded_for,
            "forwarded": self.parse_forwarded,
            "date": self.parse_date,
            "expires": self.parse_expires,
            "retry-after": self.parse_retry_after,
            "sec-fetch-site": self.parse_sec_fetch_site,
            "sec-fetch-mode": self.parse_sec_fetch_mode,
            "sec-fetch-dest": self.parse_sec_fetch_dest,
            "sec-fetch-user": self.parse_sec_fetch_user,
        }

    def parse_header(self, name: str, raw_values: list[str]) -> ParseHeaderResult:
        parser = self.registry.get(name)
        if parser is None:
            return ParseHeaderResult(True, None)
        return parser(raw_values)

    def normalize_pairs(self, pairs: list[tuple[str, str]]) -> tuple[dict[str, list[str]], list[HeaderIssue]]:
        normalized: dict[str, list[str]] = {}
        issues: list[HeaderIssue] = []
        for key, raw_value in pairs:
            name = key.strip().lower()
            value = raw_value.strip(" \t")
            if not _is_valid_header_name(name):
                issues.append(HeaderIssue(HeaderErrorCode.INVALID_HEADER_NAME, name, "invalid header name token"))
                continue
            if not _validate_no_ctl(value):
                issues.append(HeaderIssue(HeaderErrorCode.INVALID_HEADER_VALUE, name, "invalid control char in header value"))
                continue
            normalized.setdefault(name, []).append(value)
        return normalized, issues

    def normalize_lines(self, raw_lines: list[str]) -> tuple[dict[str, list[str]], list[HeaderIssue]]:
        pairs: list[tuple[str, str]] = []
        issues: list[HeaderIssue] = []
        for line in raw_lines:
            if not line:
                continue
            if line.startswith((" ", "\t")):
                issues.append(HeaderIssue(HeaderErrorCode.INVALID_HEADER_LINE, "*", "obs-fold is not supported"))
                continue
            if ":" not in line:
                issues.append(HeaderIssue(HeaderErrorCode.INVALID_HEADER_LINE, "*", "missing colon in header line"))
                continue
            key, raw_value = line.split(":", 1)
            pairs.append((key, raw_value))
        normalized, pair_issues = self.normalize_pairs(pairs)
        issues.extend(pair_issues)
        return normalized, issues

    def resolve_map(self, normalized_map: dict[str, list[str]], http_version: str = "HTTP/1.1") -> ResolveResult:
        parsed = ParsedHeaders()
        issues: list[HeaderIssue] = []
        for name, raw_values in normalized_map.items():
            result = self.parse_header(name, raw_values)
            if not result.ok and result.issue is not None:
                issues.append(result.issue)
                continue
            if result.normalized is None:
                continue
            if name == "host":
                parsed.host, parsed.port = result.normalized
            elif name == "content-length":
                parsed.content_length = result.normalized
            elif name == "transfer-encoding":
                parsed.transfer_codings, parsed.transfer_coding_raw = result.normalized
            elif name == "content-type":
                parsed.content_type, parsed.content_type_params = result.normalized
            elif name == "connection":
                parsed.connection_tokens, parsed.connection_raw_tokens = result.normalized
                parsed.hop_by_hop_headers = set(parsed.connection_raw_tokens)
            elif name == "upgrade":
                parsed.upgrade_tokens, parsed.upgrade_raw_tokens = result.normalized
            elif name == "accept":
                parsed.accept = result.normalized
            elif name == "accept-encoding":
                parsed.accept_encoding = result.normalized
            elif name == "accept-language":
                parsed.accept_language = result.normalized
            elif name == "authorization":
                parsed.authorization = result.normalized
            elif name == "cookie":
                parsed.cookies = result.normalized
            elif name == "range":
                parsed.range_values = result.normalized
            elif name == "if-range":
                parsed.if_range_etag, parsed.if_range_date = result.normalized
            elif name == "if-none-match":
                parsed.if_none_match = result.normalized
            elif name == "if-match":
                parsed.if_match = result.normalized
            elif name == "if-modified-since":
                parsed.if_modified_since = result.normalized
            elif name == "if-unmodified-since":
                parsed.if_unmodified_since = result.normalized
            elif name == "origin":
                parsed.origin = result.normalized
            elif name == "referer":
                parsed.referer = result.normalized
            elif name == "user-agent":
                parsed.user_agent = result.normalized
            elif name == "x-forwarded-for":
                parsed.x_forwarded_for = result.normalized
            elif name == "forwarded":
                parsed.forwarded = result.normalized
            elif name == "date":
                parsed.date = result.normalized
            elif name == "expires":
                parsed.expires = result.normalized
            elif name == "retry-after":
                parsed.retry_after_seconds, parsed.retry_after_date = result.normalized
            elif name == "sec-fetch-site":
                parsed.sec_fetch_site = result.normalized
            elif name == "sec-fetch-mode":
                parsed.sec_fetch_mode = result.normalized
            elif name == "sec-fetch-dest":
                parsed.sec_fetch_dest = result.normalized
            elif name == "sec-fetch-user":
                parsed.sec_fetch_user = result.normalized

        if http_version == "HTTP/1.1" and not parsed.host:
            issues.append(HeaderIssue(HeaderErrorCode.HOST_REQUIRED, "host", "host is required in HTTP/1.1"))
        if parsed.transfer_codings and parsed.content_length is not None:
            issues.append(
                HeaderIssue(
                    HeaderErrorCode.CONTENT_LENGTH_WITH_TRANSFER_ENCODING,
                    "content-length",
                    "content-length with transfer-encoding is rejected for request-smuggling safety",
                )
            )

        fatal = [i for i in issues if i.fatal]
        return ResolveResult(ok=(len(fatal) == 0), parsed=parsed, normalized_map=normalized_map, issues=issues)

    def resolve_lines(self, raw_lines: list[str], http_version: str = "HTTP/1.1") -> ResolveResult:
        normalized_map, issues = self.normalize_lines(raw_lines)
        resolved = self.resolve_map(normalized_map, http_version=http_version)
        merged = issues + resolved.issues
        fatal = [i for i in merged if i.fatal]
        return ResolveResult(ok=(len(fatal) == 0), parsed=resolved.parsed, normalized_map=normalized_map, issues=merged)

    def _pairs_from_bytes_map(
        self,
        raw_headers: dict[bytes, bytes | list[bytes]],
    ) -> tuple[list[tuple[str, str]], list[HeaderIssue]]:
        pairs: list[tuple[str, str]] = []
        issues: list[HeaderIssue] = []
        for raw_key, raw_value in raw_headers.items():
            try:
                key = raw_key.decode("ascii")
            except UnicodeDecodeError:
                issues.append(
                    HeaderIssue(
                        HeaderErrorCode.INVALID_HEADER_NAME,
                        "*",
                        "header name must be ASCII when decoding bytes map",
                    )
                )
                continue
            values: list[bytes]
            if isinstance(raw_value, bytes):
                values = [raw_value]
            elif isinstance(raw_value, list):
                values = raw_value
            else:
                issues.append(
                    HeaderIssue(
                        HeaderErrorCode.INVALID_HEADER_VALUE,
                        key.lower(),
                        "header value in bytes map must be bytes or list[bytes]",
                    )
                )
                continue

            for raw_item in values:
                if not isinstance(raw_item, bytes):
                    issues.append(
                        HeaderIssue(
                            HeaderErrorCode.INVALID_HEADER_VALUE,
                            key.lower(),
                            "header list item must be bytes",
                        )
                    )
                    continue
                try:
                    value = raw_item.decode("latin-1")
                except UnicodeDecodeError:
                    issues.append(
                        HeaderIssue(
                            HeaderErrorCode.INVALID_HEADER_VALUE,
                            key.lower(),
                            "header value cannot be decoded from bytes map",
                        )
                    )
                    continue
                pairs.append((key, value))
        return pairs, issues

    def resolve_bytes_map(self, raw_headers: dict[bytes, bytes | list[bytes]], http_version: str = "HTTP/1.1") -> ResolveResult:
        pairs, decode_issues = self._pairs_from_bytes_map(raw_headers)
        normalized_map, normalize_issues = self.normalize_pairs(pairs)
        resolved = self.resolve_map(normalized_map, http_version=http_version)
        merged = decode_issues + normalize_issues + resolved.issues
        fatal = [i for i in merged if i.fatal]
        return ResolveResult(ok=(len(fatal) == 0), parsed=resolved.parsed, normalized_map=normalized_map, issues=merged)

    def _issue(self, code: HeaderErrorCode, header: str, message: str, fatal: bool = True) -> ParseHeaderResult:
        if self.policy == ParsePolicy.COMPAT and fatal:
            fatal = False
        return ParseHeaderResult(False, None, HeaderIssue(code, header, message, fatal=fatal))

    def parse_host(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.HOST_DUPLICATE, "host", "host must appear once")
        raw = raw_values[0].strip()
        if not raw:
            return self._issue(HeaderErrorCode.HOST_INVALID, "host", "empty host value")
        host = ""
        port: int | None = None
        if raw.startswith("["):
            rb = raw.find("]")
            if rb < 2:
                return self._issue(HeaderErrorCode.HOST_INVALID, "host", "invalid IPv6 host format")
            host_literal = raw[1:rb]
            try:
                ipaddress.IPv6Address(host_literal)
            except ValueError:
                return self._issue(HeaderErrorCode.HOST_INVALID, "host", "invalid IPv6 address")
            host = host_literal.lower()
            tail = raw[rb + 1 :]
            if tail:
                if not tail.startswith(":"):
                    return self._issue(HeaderErrorCode.HOST_INVALID, "host", "invalid host:port format")
                p = tail[1:]
                if not p.isdigit():
                    return self._issue(HeaderErrorCode.HOST_INVALID, "host", "port must be decimal")
                port = int(p)
        else:
            if raw.count(":") > 1:
                return self._issue(HeaderErrorCode.HOST_INVALID, "host", "IPv6 host must use brackets")
            if ":" in raw:
                h, p = raw.rsplit(":", 1)
                if not p.isdigit():
                    return self._issue(HeaderErrorCode.HOST_INVALID, "host", "port must be decimal")
                host = h.strip().lower()
                port = int(p)
            else:
                host = raw.lower()
        if not host:
            return self._issue(HeaderErrorCode.HOST_INVALID, "host", "host is empty")
        if port is not None and not (1 <= port <= 65535):
            return self._issue(HeaderErrorCode.HOST_INVALID, "host", "port out of range")
        return ParseHeaderResult(True, (host, port))

    def parse_content_length(self, raw_values: list[str]) -> ParseHeaderResult:
        values: list[int] = []
        for raw in raw_values:
            for token in _split_quoted(raw, ","):
                if not token.isdigit():
                    return self._issue(HeaderErrorCode.CONTENT_LENGTH_INVALID, "content-length", "must be non-negative decimal")
                values.append(int(token))
        if not values:
            return self._issue(HeaderErrorCode.CONTENT_LENGTH_INVALID, "content-length", "missing value")
        if any(v != values[0] for v in values):
            return self._issue(HeaderErrorCode.CONTENT_LENGTH_CONFLICT, "content-length", "multiple values conflict")
        return ParseHeaderResult(True, values[0])

    def parse_transfer_encoding(self, raw_values: list[str]) -> ParseHeaderResult:
        known = {
            "chunked": TransferCoding.CHUNKED,
            "gzip": TransferCoding.GZIP,
            "deflate": TransferCoding.DEFLATE,
            "compress": TransferCoding.COMPRESS,
            "br": TransferCoding.BR,
            "identity": TransferCoding.IDENTITY,
        }
        raw_tokens: list[str] = []
        codings: list[TransferCoding] = []
        for raw in raw_values:
            for token in _split_quoted(raw, ","):
                t = token.lower().strip()
                if not t:
                    continue
                raw_tokens.append(t)
                codings.append(known.get(t, TransferCoding.UNKNOWN))
        if not codings:
            return self._issue(HeaderErrorCode.TRANSFER_ENCODING_INVALID, "transfer-encoding", "missing transfer-coding")
        if TransferCoding.CHUNKED in codings and codings[-1] != TransferCoding.CHUNKED:
            return self._issue(
                HeaderErrorCode.TRANSFER_ENCODING_NOT_FINAL_CHUNKED,
                "transfer-encoding",
                "chunked must be the final coding",
            )
        if self.policy == ParsePolicy.STRICT:
            for item in codings:
                if item not in (TransferCoding.CHUNKED, TransferCoding.IDENTITY):
                    return self._issue(
                        HeaderErrorCode.TRANSFER_ENCODING_UNSUPPORTED,
                        "transfer-encoding",
                        "strict mode accepts only chunked/identity",
                    )
                if item == TransferCoding.UNKNOWN:
                    return self._issue(
                        HeaderErrorCode.TRANSFER_ENCODING_UNSUPPORTED,
                        "transfer-encoding",
                        "unknown transfer-coding",
                    )
        return ParseHeaderResult(True, (codings, raw_tokens))

    def parse_content_type(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.CONTENT_TYPE_INVALID, "content-type", "content-type must appear once")
        raw = raw_values[0]
        parts = _split_quoted(raw, ";")
        if not parts:
            return self._issue(HeaderErrorCode.CONTENT_TYPE_INVALID, "content-type", "empty content-type")
        mime = parts[0].strip().lower()
        if "/" not in mime:
            return self._issue(HeaderErrorCode.CONTENT_TYPE_INVALID, "content-type", "type/subtype required")
        main_type, sub_type = mime.split("/", 1)
        if not main_type or not sub_type:
            return self._issue(HeaderErrorCode.CONTENT_TYPE_INVALID, "content-type", "type/subtype required")
        params: dict[str, str] = {}
        for seg in parts[1:]:
            if "=" not in seg:
                continue
            k, v = seg.split("=", 1)
            params[k.strip().lower()] = _unquote(v.strip())
        if mime == "multipart/form-data" and not params.get("boundary"):
            return self._issue(HeaderErrorCode.CONTENT_TYPE_INVALID, "content-type", "multipart boundary is required")
        return ParseHeaderResult(True, (mime, params))

    def parse_connection(self, raw_values: list[str]) -> ParseHeaderResult:
        mapping = {
            "close": ConnectionToken.CLOSE,
            "keep-alive": ConnectionToken.KEEP_ALIVE,
            "upgrade": ConnectionToken.UPGRADE,
        }
        raw_tokens: list[str] = []
        enum_tokens: list[ConnectionToken] = []
        for raw in raw_values:
            for item in _split_quoted(raw, ","):
                v = item.strip().lower()
                if not v:
                    continue
                raw_tokens.append(v)
                enum_tokens.append(mapping.get(v, ConnectionToken.UNKNOWN))
        return ParseHeaderResult(True, (enum_tokens, raw_tokens))

    def parse_upgrade(self, raw_values: list[str]) -> ParseHeaderResult:
        mapping = {
            "websocket": UpgradeProtocol.WEBSOCKET,
            "h2c": UpgradeProtocol.H2C,
            "tls/1.3": UpgradeProtocol.TLS_1_3,
        }
        raw_tokens: list[str] = []
        enum_tokens: list[UpgradeProtocol] = []
        for raw in raw_values:
            for item in _split_quoted(raw, ","):
                v = item.strip().lower()
                if not v:
                    continue
                raw_tokens.append(v)
                enum_tokens.append(mapping.get(v, UpgradeProtocol.UNKNOWN))
        return ParseHeaderResult(True, (enum_tokens, raw_tokens))

    def _parse_weighted_list(self, raw_values: list[str]) -> ParseHeaderResult:
        out: list[WeightedValue] = []
        order = 0
        for raw in raw_values:
            for item in _split_quoted(raw, ","):
                parts = _split_quoted(item, ";")
                if not parts:
                    continue
                value = parts[0].strip().lower()
                q = 1.0
                params: dict[str, str] = {}
                for seg in parts[1:]:
                    if "=" not in seg:
                        continue
                    k, v = seg.split("=", 1)
                    key = k.strip().lower()
                    raw_v = _unquote(v.strip())
                    if key == "q":
                        try:
                            q = float(raw_v)
                        except ValueError:
                            q = -1.0
                    else:
                        params[key] = raw_v
                if q < 0.0 or q > 1.0:
                    q = 0.0
                out.append(WeightedValue(value=value, q=q, params=params, order=order))
                order += 1
        out.sort(key=lambda x: (-x.q, x.order))
        return ParseHeaderResult(True, out)

    def parse_accept(self, raw_values: list[str]) -> ParseHeaderResult:
        return self._parse_weighted_list(raw_values)

    def parse_accept_encoding(self, raw_values: list[str]) -> ParseHeaderResult:
        return self._parse_weighted_list(raw_values)

    def parse_accept_language(self, raw_values: list[str]) -> ParseHeaderResult:
        return self._parse_weighted_list(raw_values)

    def parse_authorization(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.AUTHORIZATION_INVALID, "authorization", "authorization must appear once")
        raw = raw_values[0].strip()
        if " " not in raw:
            return self._issue(HeaderErrorCode.AUTHORIZATION_INVALID, "authorization", "scheme and credentials required")
        scheme, credentials = raw.split(" ", 1)
        scheme_l = scheme.strip().lower()
        credentials = credentials.strip()
        if not credentials:
            return self._issue(HeaderErrorCode.AUTHORIZATION_INVALID, "authorization", "empty credentials")
        if scheme_l == "bearer":
            return ParseHeaderResult(True, AuthorizationInfo(AuthScheme.BEARER, credentials))
        if scheme_l == "basic":
            try:
                decoded = base64.b64decode(credentials, validate=True).decode("utf-8")
            except (binascii.Error, UnicodeError, ValueError):
                return self._issue(HeaderErrorCode.AUTHORIZATION_INVALID, "authorization", "invalid basic token")
            if ":" not in decoded:
                return self._issue(HeaderErrorCode.AUTHORIZATION_INVALID, "authorization", "basic format must be username:password")
            username, password = decoded.split(":", 1)
            return ParseHeaderResult(True, AuthorizationInfo(AuthScheme.BASIC, credentials, username, password))
        return ParseHeaderResult(True, AuthorizationInfo(AuthScheme.UNKNOWN, credentials))

    def parse_cookie(self, raw_values: list[str]) -> ParseHeaderResult:
        cookies: dict[str, str] = {}
        for raw in raw_values:
            for seg in raw.split(";"):
                item = seg.strip()
                if not item or "=" not in item:
                    continue
                key, value = item.split("=", 1)
                k = key.strip()
                v = value.strip()
                if not k:
                    continue
                cookies[k] = unquote(v) if self.decode_cookie else v
        return ParseHeaderResult(True, cookies)

    def parse_range(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "range must appear once")
        raw = raw_values[0].strip()
        if "=" not in raw:
            return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "range unit is required")
        unit, right = raw.split("=", 1)
        if unit.strip().lower() != "bytes":
            return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "only bytes range is supported")
        ranges: list[RangeSpec] = []
        for item in _split_quoted(right, ","):
            if "-" not in item:
                return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "invalid byte-range spec")
            start_str, end_str = item.split("-", 1)
            start_str = start_str.strip()
            end_str = end_str.strip()
            if start_str == "" and end_str == "":
                return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "invalid empty range")
            start = int(start_str) if start_str.isdigit() else None
            end = int(end_str) if end_str.isdigit() else None
            if start_str and start is None:
                return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "range start must be decimal")
            if end_str and end is None:
                return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "range end must be decimal")
            if start is not None and end is not None and start > end:
                return self._issue(HeaderErrorCode.RANGE_INVALID, "range", "range start exceeds end")
            ranges.append(RangeSpec(start, end))
        return ParseHeaderResult(True, ranges)

    def parse_if_range(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.IF_RANGE_INVALID, "if-range", "if-range must appear once")
        raw = raw_values[0].strip()
        if raw.startswith('"') or raw.startswith("W/"):
            return ParseHeaderResult(True, (raw, None))
        dt = _parse_http_date(raw)
        if dt is None:
            return self._issue(HeaderErrorCode.IF_RANGE_INVALID, "if-range", "invalid if-range date")
        return ParseHeaderResult(True, (None, dt))

    def _parse_etag_list(self, raw_values: list[str]) -> ParseHeaderResult:
        tags: list[str] = []
        for raw in raw_values:
            for item in _split_quoted(raw, ","):
                v = item.strip()
                if v:
                    tags.append(v)
        return ParseHeaderResult(True, tags)

    def parse_if_none_match(self, raw_values: list[str]) -> ParseHeaderResult:
        return self._parse_etag_list(raw_values)

    def parse_if_match(self, raw_values: list[str]) -> ParseHeaderResult:
        return self._parse_etag_list(raw_values)

    def parse_if_modified_since(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.DATE_INVALID, "if-modified-since", "must appear once")
        dt = _parse_http_date(raw_values[0])
        if dt is None:
            return self._issue(HeaderErrorCode.DATE_INVALID, "if-modified-since", "invalid http-date")
        return ParseHeaderResult(True, dt)

    def parse_if_unmodified_since(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.DATE_INVALID, "if-unmodified-since", "must appear once")
        dt = _parse_http_date(raw_values[0])
        if dt is None:
            return self._issue(HeaderErrorCode.DATE_INVALID, "if-unmodified-since", "invalid http-date")
        return ParseHeaderResult(True, dt)

    def parse_origin(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.HOST_INVALID, "origin", "origin must appear once")
        raw = raw_values[0].strip()
        if raw == "null":
            return ParseHeaderResult(True, "null")
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.netloc:
            return self._issue(HeaderErrorCode.HOST_INVALID, "origin", "origin must be scheme://host[:port] or null")
        return ParseHeaderResult(True, f"{parsed.scheme.lower()}://{parsed.netloc.lower()}")

    def parse_referer(self, raw_values: list[str]) -> ParseHeaderResult:
        if not raw_values:
            return ParseHeaderResult(True, None)
        return ParseHeaderResult(True, raw_values[0].strip())

    def parse_user_agent(self, raw_values: list[str]) -> ParseHeaderResult:
        if not raw_values:
            return ParseHeaderResult(True, None)
        return ParseHeaderResult(True, raw_values[0].strip())

    def parse_x_forwarded_for(self, raw_values: list[str]) -> ParseHeaderResult:
        ips: list[str] = []
        for raw in raw_values:
            for item in _split_quoted(raw, ","):
                value = item.strip()
                if value:
                    ips.append(value)
        return ParseHeaderResult(True, ips)

    def parse_forwarded(self, raw_values: list[str]) -> ParseHeaderResult:
        hops: list[ForwardedElement] = []
        for raw in raw_values:
            for element_text in _split_quoted(raw, ","):
                element = ForwardedElement()
                for seg in _split_quoted(element_text, ";"):
                    if "=" not in seg:
                        continue
                    k, v = seg.split("=", 1)
                    key = k.strip().lower()
                    value = _unquote(v.strip())
                    if key == "for":
                        element.for_value = value
                    elif key == "by":
                        element.by = value
                    elif key == "host":
                        element.host = value
                    elif key == "proto":
                        element.proto = value
                hops.append(element)
        return ParseHeaderResult(True, hops)

    def parse_date(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.DATE_INVALID, "date", "date must appear once")
        dt = _parse_http_date(raw_values[0])
        if dt is None:
            return self._issue(HeaderErrorCode.DATE_INVALID, "date", "invalid http-date")
        return ParseHeaderResult(True, dt)

    def parse_expires(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.DATE_INVALID, "expires", "expires must appear once")
        dt = _parse_http_date(raw_values[0])
        if dt is None:
            return self._issue(HeaderErrorCode.DATE_INVALID, "expires", "invalid http-date")
        return ParseHeaderResult(True, dt)

    def parse_retry_after(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return self._issue(HeaderErrorCode.DATE_INVALID, "retry-after", "retry-after must appear once")
        raw = raw_values[0].strip()
        if raw.isdigit():
            return ParseHeaderResult(True, (int(raw), None))
        dt = _parse_http_date(raw)
        if dt is None:
            return self._issue(HeaderErrorCode.DATE_INVALID, "retry-after", "retry-after must be seconds or http-date")
        return ParseHeaderResult(True, (None, dt))

    def parse_sec_fetch_site(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return ParseHeaderResult(True, None)
        mapping = {
            "same-origin": FetchSite.SAME_ORIGIN,
            "same-site": FetchSite.SAME_SITE,
            "cross-site": FetchSite.CROSS_SITE,
            "none": FetchSite.NONE,
        }
        v = raw_values[0].strip().lower()
        return ParseHeaderResult(True, mapping.get(v, FetchSite.UNKNOWN))

    def parse_sec_fetch_mode(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return ParseHeaderResult(True, None)
        mapping = {
            "navigate": FetchMode.NAVIGATE,
            "nested-navigate": FetchMode.NESTED_NAVIGATE,
            "no-cors": FetchMode.NO_CORS,
            "cors": FetchMode.CORS,
            "same-origin": FetchMode.SAME_ORIGIN,
            "websocket": FetchMode.WEBSOCKET,
        }
        v = raw_values[0].strip().lower()
        return ParseHeaderResult(True, mapping.get(v, FetchMode.UNKNOWN))

    def parse_sec_fetch_dest(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return ParseHeaderResult(True, None)
        return ParseHeaderResult(True, raw_values[0].strip().lower())

    def parse_sec_fetch_user(self, raw_values: list[str]) -> ParseHeaderResult:
        if len(raw_values) != 1:
            return ParseHeaderResult(True, None)
        v = raw_values[0].strip().lower()
        if v == "?1":
            return ParseHeaderResult(True, FetchUser.YES)
        return ParseHeaderResult(True, FetchUser.UNKNOWN)
