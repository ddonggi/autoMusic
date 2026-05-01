import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.notify import (
    Notification,
    build_batch_failure_notification,
    build_batch_success_notification,
    build_daily_success_notification,
    send_gmail_notification,
)


class NotifyTests(unittest.TestCase):
    def test_build_batch_success_notification_includes_video_and_archive_path(self):
        message = build_batch_success_notification(
            batch={"batch_id": "batch-001", "youtube_video_id": "video-123"},
            archived_path=Path("success/batches/batch-001"),
        )

        self.assertIn("성공", message.subject)
        self.assertIn("batch-001", message.body)
        self.assertIn("video-123", message.body)
        self.assertIn("success/batches/batch-001", message.body)

    def test_build_batch_failure_notification_includes_stage_and_error(self):
        message = build_batch_failure_notification(
            batch_id="batch-001",
            stage="youtube_credentials",
            error=RuntimeError("missing youtube credentials"),
        )

        self.assertIn("실패", message.subject)
        self.assertIn("batch-001", message.body)
        self.assertIn("youtube_credentials", message.body)
        self.assertIn("missing youtube credentials", message.body)
        self.assertIn("다시 실행", message.body)

    def test_build_daily_success_notification_includes_track_details(self):
        message = build_daily_success_notification(
            track_dir=Path("workspace/tracks/track-001"),
            track={
                "track_id": "track-001",
                "duration_seconds": 180.0,
                "music_variant": "rave-metamorphosis",
                "image_variant": "cyberpunk-gym",
            },
        )

        self.assertIn("음악 생성 성공", message.subject)
        self.assertIn("track-001", message.body)
        self.assertIn("180.0", message.body)
        self.assertIn("rave-metamorphosis", message.body)
        self.assertIn("cyberpunk-gym", message.body)

    def test_send_gmail_notification_returns_false_when_config_missing(self):
        sent = send_gmail_notification(Notification("subject", "body"), env={})

        self.assertFalse(sent)

    def test_send_gmail_notification_sends_email_with_smtp_config(self):
        sent_messages = []

        class FakeSmtp:
            def __init__(self, host, port):
                self.host = host
                self.port = port

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def login(self, user, password):
                sent_messages.append(("login", user, password))

            def send_message(self, message):
                sent_messages.append(("send", message["From"], message["To"], message["Subject"], message.get_content()))

        sent = send_gmail_notification(
            Notification("subject", "body"),
            env={
                "GMAIL_SMTP_USER": "sender@gmail.com",
                "GMAIL_SMTP_APP_PASSWORD": "app-password",
                "NOTIFY_EMAIL_TO": "receiver@gmail.com",
            },
            smtp_factory=FakeSmtp,
        )

        self.assertTrue(sent)
        self.assertEqual(sent_messages[0], ("login", "sender@gmail.com", "app-password"))
        self.assertEqual(sent_messages[1][1:4], ("sender@gmail.com", "receiver@gmail.com", "subject"))
        self.assertIn("body", sent_messages[1][4])

    def test_send_gmail_notification_accepts_generic_smtp_tls_config(self):
        sent_messages = []

        class FakeSmtp:
            def __init__(self, host, port):
                sent_messages.append(("connect", host, port))

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def starttls(self):
                sent_messages.append(("starttls",))

            def login(self, user, password):
                sent_messages.append(("login", user, password))

            def send_message(self, message):
                sent_messages.append(("send", message["From"], message["To"], message["Subject"]))

        sent = send_gmail_notification(
            Notification("subject", "body"),
            env={
                "SMTP_HOST": "smtp.gmail.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "sender@gmail.com",
                "SMTP_PASSWORD": "app-password",
                "SMTP_FROM_EMAIL": "from@gmail.com",
                "SMTP_TO_EMAIL": "receiver@gmail.com",
                "SMTP_USE_TLS": "true",
            },
            smtp_factory=FakeSmtp,
            smtp_ssl_factory=lambda host, port: self.fail("SMTP_SSL should not be used"),
        )

        self.assertTrue(sent)
        self.assertEqual(sent_messages[0], ("connect", "smtp.gmail.com", 587))
        self.assertEqual(sent_messages[1], ("starttls",))
        self.assertEqual(sent_messages[2], ("login", "sender@gmail.com", "app-password"))
        self.assertEqual(sent_messages[3], ("send", "from@gmail.com", "receiver@gmail.com", "subject"))


if __name__ == "__main__":
    unittest.main()
