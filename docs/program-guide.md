# AutoMusic Program Guide

AutoMusic is a local automation pipeline for creating Brazilian phonk workout music videos.

The pipeline creates one short track per daily run, generates a matching background image, waits until 10 completed tracks exist, renders them into one longer MP4, uploads the MP4 to YouTube as a private video, and moves completed assets into the success archive.

## Current Capability

Implemented:

- Generate a daily music track with Google Gemini Lyria RealTime.
- Generate a matching 16:9 background image with the OpenAI image API.
- Store each track as a structured folder under `workspace/tracks/`.
- Select the oldest 10 completed tracks for a batch.
- Render a batch MP4 with `ffmpeg`.
- Upload the rendered MP4 to YouTube as `private`.
- Move successfully uploaded tracks and batches to `success/`.
- Run the full flow in `--dry-run` mode without external API calls.
- Vary music and image prompts per run using internal prompt variants.

Not yet implemented:

- Animated visual effects from the background image.
- Real GIF generation as a reusable output.
- Automatic scheduling.
- Live YouTube upload verification in this environment. Gemini and OpenAI daily generation has been verified once.

## Main Commands

Run from the implementation worktree:

```bash
cd /Users/dglee/workspace/autoMusic/.worktrees/automusic-pipeline
```

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run one daily dry-run:

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml --dry-run
```

Run one real daily generation:

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml
```

Run separated image generation with the same config when you want image variants from `configs/examples/music.yaml`:

```bash
python3 scripts/generate_image.py workspace/tracks/<track-id> --config configs/examples/music.yaml
```

Run batch upload dry-run after 10 tracks exist:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml --dry-run
```

Run real batch render, upload, and archive after 10 tracks exist:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml
```

## Environment Variables

Secrets are loaded from `.env` or the shell environment. They must not be committed.

Required for music generation:

```bash
GEMINI_API_KEY=
```

Required for image generation:

```bash
OPENAI_API_KEY=
```

Required for YouTube upload:

```bash
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=
```

Optional for Gmail notifications:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_TO_EMAIL=
SMTP_USE_TLS=true
```

Use `.env.example` as the template. Keep real values only in `.env`.

## Pipeline Flow

Daily generation:

```text
configs/examples/music.yaml
  -> scripts/run_daily.py
  -> Lyria music generation
  -> OpenAI background image generation
  -> workspace/tracks/<track-id>/
```

Batch upload:

```text
workspace/tracks/ with 10 imaged tracks
  -> scripts/run_batch_upload.py
  -> resume an unfinished batch first, if one exists
  -> build batch metadata
  -> render video.mp4 with ffmpeg
  -> upload to YouTube as private
  -> move completed folders to success/
```

Notification behavior:

- A live `run_daily.py` success sends a Gmail message after audio and image are both complete.
- Batch upload success sends a Gmail message after YouTube upload and archive movement complete.
- Batch upload failure sends a Gmail message when a batch already exists and a render, credential, upload, or archive step fails.
- Missing SMTP settings skip notification only; they do not fail the music or upload pipeline.

## Daily Automation On macOS

This machine is macOS, so use `launchd` instead of `systemd timer`. `cron` can work, but `launchd` is the native scheduler and handles user LaunchAgents and logs more predictably on macOS.

Install or update the daily noon job:

```bash
python3 scripts/install_launchd.py
```

What gets installed:

- LaunchAgent path: `~/Library/LaunchAgents/com.automusic.daily.plist`
- Schedule: every day at `12:00` local macOS time
- Command: `.venv/bin/python scripts/run_automation.py --project-root <project-root>`
- Logs: `logs/launchd.out.log` and `logs/launchd.err.log`

The automation command runs `run_daily.py` first. It then runs `run_batch_upload.py` only when an unfinished batch exists or at least 10 unbatched `imaged` tracks are ready.

Manual checks:

```bash
launchctl list | grep com.automusic.daily
launchctl start com.automusic.daily
tail -f logs/launchd.out.log logs/launchd.err.log
```

Disable the schedule:

```bash
launchctl unload ~/Library/LaunchAgents/com.automusic.daily.plist
```

## Folder Structure

Active work:

```text
workspace/
  tracks/
    <track-id>/
      audio.wav
      image.png
      track.json
  batches/
    <batch-id>/
      batch.json
      audio_concat.txt
      image_concat.txt
      video.mp4
```

Completed work:

```text
success/
  tracks/
    <track-id>/
      audio.wav
      image.png
      track.json
  batches/
    <batch-id>/
      batch.json
      video.mp4
```

`workspace/` means pending or in-progress. `success/` means the YouTube upload succeeded and the assets were archived.

## Track State

Each track has a `track.json` file.

Typical state flow:

```text
generated -> imaged -> batched -> uploaded -> archived
```

Important fields:

- `track_id`: folder-safe track identifier.
- `status`: current track status.
- `music_prompt`: final prompt sent to music generation.
- `image_prompt`: final prompt used for image generation.
- `duration_seconds`: measured audio duration.
- `audio_path`: usually `audio.wav`.
- `image_path`: usually `image.png`.
- `batch_id`: batch identifier after the track is selected.
- `created_at`: creation timestamp.

## Batch State

Each batch has a `batch.json` file.

Typical state flow:

```text
assembled -> rendered -> uploaded -> archived
```

Important fields:

- `batch_id`: folder-safe batch identifier.
- `status`: current batch status.
- `track_ids`: the 10 tracks included in this batch.
- `video_path`: rendered MP4 path, usually `video.mp4`.
- `youtube_video_id`: set only after YouTube upload succeeds.
- `archive_pending`: true after upload until archive movement completes.
- `created_at`: batch creation timestamp.

Once `batch.json` is created, the selected track list is stable. Extra tracks remain in `workspace/tracks/` for the next batch.

## Prompts

Music prompts are built from structured config fields:

- `genre`
- `bpm_min`
- `bpm_max`
- `mood`
- `instruments`
- `texture`
- `vocals`
- `negative_rules`
- `prompt_variants`

The default style is Brazilian phonk for gym and workout use:

```text
Brazilian phonk, aggressive workout energy, distorted 808 bass,
driving cowbell lead, punchy drums, gritty street-gym texture.
```

The config also includes internal variants inspired by high-energy phonk listening references. Reference song titles are not sent to the API. They are translated into safe descriptors such as accelerated baile-funk percussion, aggressive cowbell lead, dark distorted 808, rave synth pressure, loose syncopated groove, and avant-garde tension.

Image prompts are derived from the music metadata, but they are not a direct copy of the music prompt. The image prompt turns the sound into visual direction. Current image variants include cyberpunk gym, bodybuilder shadow, and phonk album-cover styles. All image prompts include 16:9 framing, no text, no logos, no watermark, and no real artist reference.

Each new `track.json` records:

- `music_variant`
- `image_variant`

## Rendering

Rendering uses `ffmpeg`.

The current renderer:

- Concatenates the 10 audio files.
- Builds an image concat file using each track image and its duration.
- Produces `video.mp4`.

Current limitation:

- The visual track uses still images matched to durations.
- Animated zoom, pan, glow, grain, or GIF-style motion is not implemented yet.

## YouTube Upload

Uploads use the YouTube Data API with OAuth refresh-token credentials.

Default upload behavior:

- `privacyStatus`: `private`
- `categoryId`: `10` for music
- `made_for_kids`: false

If `youtube_video_id` already exists in `batch.json`, upload logic treats the batch as already uploaded and avoids duplicate upload behavior where supported.

## Failure and Retry

Daily generation failure:

- If music generation fails, no complete track should be used for batching.
- If image generation fails after music succeeds, rerun image generation for that track.

Batch build failure:

- If fewer than 10 `imaged` tracks exist, batch creation stops.

Render failure:

- The batch remains in `workspace/batches/`.
- Fix the issue and rerun rendering or `run_batch_upload.py`.
- The next `run_batch_upload.py` run resumes the existing batch before creating a new one.

Upload failure:

- The rendered batch remains in `workspace/batches/`.
- Retry upload after fixing credentials or API issues.
- Tracks already selected for the batch remain `batched`, so day 11 creates a new `imaged` track but does not replace the failed 10-track batch.

Archive failure:

- The batch should retain `youtube_video_id`.
- `archive_pending` indicates that the upload succeeded but movement to `success/` still needs to complete.
- The next `run_batch_upload.py` run skips upload and retries archive first.

## Cost Points

Costs may occur when running without `--dry-run`:

- Gemini/Lyria music generation API usage.
- OpenAI image generation API usage.
- YouTube API quota usage.

`--dry-run` does not call external APIs and should not create API charges.

## Safety Rules

Do not commit:

- `.env`
- OAuth token JSON files
- Google client secret JSON files
- generated audio, images, GIFs, or videos
- `workspace/`
- `success/`

Before committing, run:

```bash
git status --short --untracked-files=all
git diff --cached --stat
git grep --cached -n -i -E "(api[_-]?key|secret|refresh[_-]?token|access[_-]?token|client[_-]?secret|authorization:|bearer )" -- .
```

Only placeholder names and documentation examples should appear in the scan.

## Verification

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

Run syntax compilation:

```bash
python3 -m compileall -q src scripts tests
```

Run daily dry-run:

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml --dry-run
```

To verify batch dry-run, create 10 dry-run tracks and then run:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml --dry-run
```
