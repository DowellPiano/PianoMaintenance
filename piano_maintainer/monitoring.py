import re


UUID_PATTERN = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
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
        request["url"] = UUID_PATTERN.sub("<redacted-uuid>", request["url"])

    headers = request.get("headers")
    if headers:
        request["headers"] = {
            key: value
            for key, value in headers.items()
            if key.lower() not in SENSITIVE_HEADERS
        }

    return event
