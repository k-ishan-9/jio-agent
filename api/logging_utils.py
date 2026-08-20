"""
api/logging_utils.py — structured (JSON) logging setup and PII scrubbing.

Two independent concerns bundled together because they're both about what
ends up in the logs:
  1. JsonFormatter — every log line becomes a single JSON object instead of
     an unstructured string, so logs can be shipped to and queried in any
     log aggregator (CloudWatch, Datadog, ELK, ...) without a custom parser.
  2. scrub_pii — user questions are logged verbatim for debugging; if a user
     types a phone number, email, or Jio account/SIM number into the chat,
     that must not land in plaintext logs.
"""

import json
import logging
import re
import sys

# --- PII scrubbing -----------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?91[-\s]?)?\b[6-9]\d{9}\b")  # Indian mobile numbers
_LONG_DIGIT_RE = re.compile(r"\b\d{6,}\b")  # account numbers, OTPs, SIM/ICCID digits


def scrub_pii(text: str) -> str:
    """Mask emails, phone numbers, and long digit sequences (account/OTP-like)
    before a string is logged. Not a full PII-detection system — a
    pragmatic best-effort mask for the identifiers most likely to appear
    in a telecom support chat."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = _PHONE_RE.sub("[PHONE_REDACTED]", text)
    text = _LONG_DIGIT_RE.sub("[NUMBER_REDACTED]", text)
    return text


# --- JSON structured logging -------------------------------------------

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Allow callers to attach structured fields via logger.info(..., extra={"fields": {...}})
        extra_fields = getattr(record, "fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def setup_json_logging(level=logging.INFO):
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
