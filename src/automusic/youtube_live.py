from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .state import load_json
from .youtube import build_video_body


def upload_video(batch_path: Path, config: dict[str, Any]) -> str:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    batch = load_json(batch_path / "batch.json")
    if batch.get("youtube_video_id"):
        return str(batch["youtube_video_id"])

    video_path = batch_path / batch["video_path"]
    if not video_path.exists():
        raise RuntimeError(f"Rendered video does not exist: {video_path}")

    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    youtube = build("youtube", "v3", credentials=credentials)
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=build_video_body(config),
        media_body=media,
    )
    response = request.execute()
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload response did not include a video id")
    return str(video_id)
