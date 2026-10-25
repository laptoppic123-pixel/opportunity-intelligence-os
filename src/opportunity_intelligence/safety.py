import hashlib
import html
from html.parser import HTMLParser
import ipaddress
import json
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def redact(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if not isinstance(v, bool)
            and v is not None
            and re.search(r"secret|api.?key|authorization|password|access.?token", k, re.I)
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"(?i)(?:Bearer\s+|sb_secret_|sk-or-v1-|sk-)[A-Za-z0-9_.-]+", "[REDACTED]", value)
    value = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s,;&]+", r"\1=[REDACTED]", value)
    return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email removed]", value)


def clean(text, limit=700):
    p = TextOnly()
    p.feed(str(text or ""))
    value = unicodedata.normalize("NFKC", html.unescape(" ".join(p.parts)))
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return redact(re.sub(r"\s+", " ", value).strip())[:limit]


def public_url(url):
    p = urlsplit(str(url))
    if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
        raise ValueError("Only public HTTP(S) URLs without embedded credentials are allowed.")
    host = p.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal")):
        raise ValueError("Private host rejected.")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Private address rejected.")
    except ValueError as exc:
        if "rejected" in str(exc):
            raise
    if p.port not in {None, 80, 443}:
        raise ValueError("Nonstandard port rejected.")
    return url


def normalize_url(url):
    public_url(url)
    p = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", urlencode(sorted(query)), "")
    )


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def spreadsheet_text(value):
    value = redact(str(value))
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def source_message(records):
    """JSON encodes untrusted content as data. It never becomes system instructions."""
    return json.dumps({"untrusted_source_records": records}, ensure_ascii=True)
