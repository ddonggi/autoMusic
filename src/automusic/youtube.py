from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .state import load_json, save_json


def build_video_body(config: dict[str, Any]) -> dict[str, Any]:
    privacy_status = config.get("privacy_status", "private")
    return {
        "snippet": {
            "title": config.get("title_template", "Brazilian Phonk Workout Mix"),
            "description": config.get("description_template", ""),
            "tags": config.get("tags", []),
            "categoryId": str(config.get("category_id", "10")),
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": bool(config.get("made_for_kids", False)),
        },
    }


def should_skip_upload(batch: dict[str, Any]) -> bool:
    return bool(batch.get("youtube_video_id"))


def update_batch_after_upload(batch_json_path: Path, video_id: str) -> None:
    batch = load_json(batch_json_path)
    batch["status"] = "uploaded"
    batch["youtube_video_id"] = video_id
    batch["archive_pending"] = True
    save_json(batch_json_path, batch)


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode()
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode())
    if "access_token" not in payload:
        raise RuntimeError("Google OAuth response did not include access_token")
    return str(payload["access_token"])


def upload_video_placeholder(batch_path: Path) -> str:
    raise NotImplementedError(
        "Live YouTube upload requires google-api-python-client integration and OAuth credentials."
    )
