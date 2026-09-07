import re


UUID_PATTERN = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
PASSWORD_RESET_PATTERN = re.compile(
    r"(?i)(/password-reset/)[^/?#]+/[^/?#]+"
)
SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "referer",
    "x-api-key",
}


def make_sentry_traces_sampler(sample_rate):
    def traces_sampler(sampling_context):
        environ = sampling_context.get("wsgi_environ") or {}
        if environ.get("PATH_INFO") == "/healthz/":
            return 0.0
        return sample_rate

    return traces_sampler


def sanitize_sentry_event(event, hint):
    event.pop("user", None)
    request = event.get("request")
    if not request:
        return event

    request.pop("data", None)
    request.pop("cookies", None)
    request.pop("query_string", None)

    if request.get("url"):
        sanitized_url = UUID_PATTERN.sub("<redacted-uuid>", request["url"])
        request["url"] = PASSWORD_RESET_PATTERN.sub(
            r"\1<redacted-user>/<redacted-token>",
            sanitized_url,
        )

    headers = request.get("headers")
    if headers:
        request["headers"] = {
            key: value
            for key, value in headers.items()
            if key.lower() not in SENSITIVE_HEADERS
        }

    return event
