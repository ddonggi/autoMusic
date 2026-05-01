# AutoMusic

AutoMusic generates daily Brazilian phonk workout tracks, creates matching background images, batches 10 tracks into one MP4, uploads it to YouTube as private, and archives successful outputs.

Music and image prompts are variant-based. Each run keeps the phonk genre but chooses a safe internal style variant instead of naming or imitating reference songs.

## Setup

Install runtime dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Create `.env` locally from `.env.example` and fill in real values:

```bash
GEMINI_API_KEY=
OPENAI_API_KEY=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_TO_EMAIL=
SMTP_USE_TLS=true
```

Do not commit `.env`, token files, generated media, `workspace/`, or `success/`.

SMTP settings are optional. If set, live daily generation sends a completion email, and batch upload sends success or failure emails.

## Dry Run

Generate one fake music track and image without external API calls:

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml --dry-run
```

After 10 imaged tracks exist under `workspace/tracks/`, test batch/upload/archive flow without external API calls:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml --dry-run
```

## Live Run

Generate one real music track and OpenAI background image:

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml
```

When 10 tracks are ready, render, upload privately to YouTube, and archive:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml
```

## Separate Steps

The pipeline can also be run step by step:

```bash
python3 scripts/generate_music.py --config configs/examples/music.yaml
python3 scripts/generate_image.py workspace/tracks/<track-id> --config configs/examples/music.yaml
python3 scripts/build_batch.py
python3 scripts/render_video.py workspace/batches/<batch-id>
python3 scripts/upload_youtube.py workspace/batches/<batch-id> --config configs/examples/upload.yaml
```

## Verify

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

Run a staged secret scan before committing:

```bash
git grep --cached -n -i -E "(api[_-]?key|secret|refresh[_-]?token|access[_-]?token|client[_-]?secret|authorization:|bearer )" -- .
```
