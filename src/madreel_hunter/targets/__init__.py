"""Output targets: local files and outbound webhooks."""

from .jsonl import write_json, write_jsonl
from .webhook import post_webhook

__all__ = ["post_webhook", "write_json", "write_jsonl"]
