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
            "일일 음악 생성이 완료되었습니다. 배경 이미지는 배치 생성 시 생성됩니다.\n\n"
            f"Track ID: {track_id}\n"
            f"Track Path: {track_dir}\n"
            f"Duration Seconds: {track.get('duration_seconds')}\n"
            f"Title: {track.get('title')}\n"
            f"Music Variant: {track.get('music_variant')}\n"
        ),
    )


def build_daily_failure_notification(
    *,
    stage: str,
    error: BaseException,
    track_dir: Path | None = None,
) -> Notification:
    track_path = str(track_dir) if track_dir is not None else "not created"
    return Notification(
        subject=f"[AutoMusic] 음악 생성 실패: {stage}",
        body=(
            "일일 음악 생성 파이프라인이 실패했습니다.\n\n"
            f"Failed Stage: {stage}\n"
            f"Track Path: {track_path}\n"
            f"Error: {error}\n\n"
            "문제를 해결한 뒤 수동 실행하거나 다음 스케줄 실행에서 다시 시도합니다.\n"
        ),
    )


def send_gmail_notification(
    notification: Notification,
    *,
    env: Mapping[str, str] | None = None,
    smtp_factory=None,
    smtp_ssl_factory=None,
) -> bool:
    env = os.environ if env is None else env
    config = _load_smtp_config(env)
    if config is None:
        return False
    custom_smtp_factory = smtp_factory is not None
    smtp_factory = smtp_factory or smtplib.SMTP
    smtp_ssl_factory = smtp_ssl_factory or (smtp_factory if custom_smtp_factory else smtplib.SMTP_SSL)

    message = EmailMessage()
    message["From"] = config["from_email"]
    message["To"] = config["to_email"]
    message["Subject"] = notification.subject
    message.set_content(notification.body)

    factory = smtp_factory if config["use_tls"] else smtp_ssl_factory
    with factory(config["host"], config["port"]) as smtp:
        if config["use_tls"]:
            smtp.starttls()
        smtp.login(config["username"], config["password"])
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


def _load_smtp_config(env: Mapping[str, str]) -> dict[str, object] | None:
    username = env.get("SMTP_USERNAME") or env.get("GMAIL_SMTP_USER")
    password = env.get("SMTP_PASSWORD") or env.get("GMAIL_SMTP_APP_PASSWORD")
    to_email = env.get("SMTP_TO_EMAIL") or env.get("NOTIFY_EMAIL_TO")
    if not username or not password or not to_email:
        return None

    use_tls = _env_bool(env.get("SMTP_USE_TLS"))
    return {
        "host": env.get("SMTP_HOST") or "smtp.gmail.com",
        "port": int(env.get("SMTP_PORT") or (587 if use_tls else 465)),
        "username": username,
        "password": password,
        "from_email": env.get("SMTP_FROM_EMAIL") or username,
        "to_email": to_email,
        "use_tls": use_tls,
    }


def _env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}
