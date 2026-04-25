# Security and Commit Safety

This project must not commit API keys, OAuth tokens, generated media, or local runtime state.

## Secrets

Keep these values in `.env` or your shell environment only:

- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Commit only `.env.example`, which contains empty placeholders.

## Files That Must Stay Local

Do not commit:

- `.env` or `.env.*` files, except `.env.example`
- Google OAuth client secret files such as `client_secret*.json`
- OAuth token files such as `token*.json` or `youtube_token*.json`
- service account credential JSON files
- generated audio, images, GIFs, and videos
- pipeline working folders such as `workspace/`, `success/`, `data/`, and `outputs/`

## Config Pattern

Runtime configs may reference environment variable names, but must not contain real secret values.

Good:

```yaml
youtube:
  client_id_env: YOUTUBE_CLIENT_ID
  client_secret_env: YOUTUBE_CLIENT_SECRET
  refresh_token_env: YOUTUBE_REFRESH_TOKEN
```

Bad:

```yaml
youtube:
  client_secret: real-secret-value
  refresh_token: real-refresh-token
```

## Pre-Commit Manual Check

Before committing, run:

```bash
git status --short --untracked-files=all
git diff --cached --stat
git grep --cached -n -i -E "(api[_-]?key|secret|refresh[_-]?token|access[_-]?token|client[_-]?secret|authorization:|bearer )" -- .
```

If the scan reports only placeholders, documentation examples, or variable names, it is safe to review and commit.
