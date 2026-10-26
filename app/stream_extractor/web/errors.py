import re


SENSITIVE = re.compile(
    r"(token|sig|nauth|nauthsig|client_id)=[^&\s\"']+", re.IGNORECASE
)
URL = re.compile(r"https?://\S+")


def sanitize_error(message):
    clean = SENSITIVE.sub(r"\1=REDACTED", message)
    return URL.sub("[redactado]", clean)
