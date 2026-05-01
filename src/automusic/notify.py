from __future__ import annotations

import os
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Notification:
    subject: str
    body: str


def build_batch_success_notification(batch: dict, archived_path: Path) -> Notification:
    batch_id = str(batch.get("batch_id", "unknown-batch"))
    video_id = str(batch.get("youtube_video_id", "unknown-video"))
    return Notification(
        subject=f"[AutoMusic] 배치 업로드 성공: {batch_id}",
        body=(
            "배치 업로드와 보관이 완료되었습니다.\n\n"
            f"Batch ID: {batch_id}\n"
            f"YouTube Video ID: {video_id}\n"
            f"Archive Path: {archived_path}\n"
        ),
    )


def build_batch_failure_notification(batch_id: str, stage: str, error: BaseException) -> Notification:
    return Notification(
        subject=f"[AutoMusic] 배치 업로드 실패: {batch_id}",
        body=(
            "배치 업로드 파이프라인이 실패했습니다.\n\n"
            f"Batch ID: {batch_id}\n"
            f"Failed Stage: {stage}\n"
            f"Error: {error}\n\n"
            "문제를 해결한 뒤 같은 명령을 다시 실행하면 기존 배치부터 재시도합니다.\n"
        ),
    )


def build_daily_success_notification(track_dir: Path, track: dict) -> Notification:
    track_id = str(track.get("track_id") or track_dir.name)
    return Notification(
        subject=f"[AutoMusic] 음악 생성 성공: {track_id}",
        body=(
            "일일 음악과 배경 이미지 생성이 완료되었습니다.\n\n"
            f"Track ID: {track_id}\n"
            f"Track Path: {track_dir}\n"
            f"Duration Seconds: {track.get('duration_seconds')}\n"
            f"Music Variant: {track.get('music_variant')}\n"
            f"Image Variant: {track.get('image_variant')}\n"
        ),
    )


def send_gmail_notification(
    notification: Notification,
    *,
    env: Mapping[str, str] | None = None,
    smtp_factory=smtplib.SMTP_SSL,
) -> bool:
    env = os.environ if env is None else env
    user = env.get("GMAIL_SMTP_USER")
    password = env.get("GMAIL_SMTP_APP_PASSWORD")
    recipient = env.get("NOTIFY_EMAIL_TO")
    if not user or not password or not recipient:
        return False

    message = EmailMessage()
    message["From"] = user
    message["To"] = recipient
    message["Subject"] = notification.subject
    message.set_content(notification.body)

    with smtp_factory("smtp.gmail.com", 465) as smtp:
        smtp.login(user, password)
        smtp.send_message(message)
    return True


def send_notification_safely(notification: Notification) -> bool:
    try:
        sent = send_gmail_notification(notification)
        if not sent:
            print("Notification skipped: Gmail SMTP environment is incomplete.", file=sys.stderr)
        return sent
    except Exception as exc:  # pragma: no cover - defensive logging for live SMTP failures.
        print(f"Notification skipped after SMTP failure: {exc}", file=sys.stderr)
        return False
