# AutoMusic 프로그램 가이드

AutoMusic은 브라질리언 폰크 스타일의 운동용 음악 영상을 자동으로 만들기 위한 로컬 파이프라인입니다.

이 파이프라인은 하루 실행마다 짧은 음악 트랙 1개를 만들고, 그 분위기에 맞는 배경 이미지를 생성합니다. 완성된 트랙이 10개 쌓이면 하나의 긴 MP4 영상으로 렌더링하고, YouTube에 `private` 상태로 업로드한 뒤 성공한 산출물을 `success/` 폴더로 이동합니다.

## 현재 가능한 기능

구현됨:

- Google Gemini Lyria RealTime으로 하루 음악 트랙 1개 생성
- OpenAI 이미지 API로 16:9 배경 이미지 1장 생성
- 각 트랙을 `workspace/tracks/` 아래 구조화된 폴더로 저장
- 완료된 트랙 중 가장 오래된 10개를 선택해 배치 생성
- `ffmpeg`로 배치 MP4 렌더링
- YouTube에 `private` 영상으로 업로드
- 업로드 성공한 트랙과 배치를 `success/`로 이동
- 외부 API를 호출하지 않는 `--dry-run` 모드 지원
- 매 실행마다 내부 variant를 선택해 음악/이미지 프롬프트 다양화

아직 미구현:

- 배경 이미지에 줌, 팬, 글로우, 그레인 같은 애니메이션 효과 적용
- 재사용 가능한 실제 GIF 산출물 생성
- 매일 자동 실행 스케줄링
- 실제 YouTube 업로드 검증. Gemini와 OpenAI를 이용한 하루 생성은 1회 실제 검증됨

## 실행 위치

현재 구현은 worktree 브랜치에 있습니다. 실행할 때는 아래 위치로 이동해야 합니다.

```bash
cd /Users/dglee/workspace/autoMusic/.worktrees/automusic-pipeline
```

현재 루트 `/Users/dglee/workspace/autoMusic`는 main 브랜치이고, 구현 파일이 아직 병합되지 않았습니다.

## 설치

의존성을 설치합니다.

```bash
python3 -m pip install -r requirements.txt
```

가상환경을 쓰는 경우:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## 환경변수

API 키와 OAuth 값은 `.env` 또는 셸 환경변수에서 읽습니다. 실제 값은 절대 커밋하면 안 됩니다.

음악 생성에 필요:

```bash
GEMINI_API_KEY=
```

이미지 생성에 필요:

```bash
OPENAI_API_KEY=
```

YouTube 업로드에 필요:

```bash
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=
```

`.env.example`을 복사해 `.env`를 만들고 실제 값을 넣으면 됩니다. `.env`는 `.gitignore`에 의해 커밋되지 않습니다.

## 가장 먼저 해볼 실행

외부 API를 호출하지 않는 dry-run부터 실행하는 것이 안전합니다.

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml --dry-run
```

이 명령은 테스트용 트랙 폴더를 만듭니다.

생성 예:

```text
workspace/tracks/<track-id>/
  audio.wav
  image.png
  track.json
```

이때 `audio.wav`와 `image.png`는 실제 API 결과물이 아니라 테스트용 파일입니다.

## 실제 하루 생성 실행

`.env`에 `GEMINI_API_KEY`와 `OPENAI_API_KEY`가 준비되어 있으면 실제 API를 호출할 수 있습니다.

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml
```

음악과 이미지를 단계별로 나눠 실행할 때도 이미지 variant가 설정 파일을 따르게 하려면 같은 음악 설정 파일을 넘깁니다.

```bash
python3 scripts/generate_image.py workspace/tracks/<track-id> --config configs/examples/music.yaml
```

실제 실행 결과:

- Lyria로 약 3분 음악 생성
- OpenAI 이미지 API로 배경 이미지 생성
- `workspace/tracks/<track-id>/audio.wav` 저장
- `workspace/tracks/<track-id>/image.png` 저장
- `workspace/tracks/<track-id>/track.json` 저장

주의:

- 실제 실행은 API 비용이 발생할 수 있습니다.
- 현재 환경에서 Gemini 음악 생성과 OpenAI 이미지 생성은 1회 실제 검증했습니다.

## 10곡 배치 업로드 실행

`workspace/tracks/` 아래에 `imaged` 상태의 트랙이 10개 이상 있어야 합니다.

dry-run 배치 실행:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml --dry-run
```

실제 배치 실행:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml
```

실제 배치 실행 결과:

- 가장 오래된 완료 트랙 10개 선택
- `workspace/batches/<batch-id>/batch.json` 생성
- `ffmpeg`로 `video.mp4` 렌더링
- YouTube에 `private`로 업로드
- 성공 시 트랙과 배치를 `success/`로 이동

## 전체 파이프라인 흐름

하루 생성:

```text
configs/examples/music.yaml
  -> scripts/run_daily.py
  -> Lyria 음악 생성
  -> OpenAI 배경 이미지 생성
  -> workspace/tracks/<track-id>/
```

10곡 배치 업로드:

```text
workspace/tracks/ 안의 imaged 트랙 10개
  -> scripts/run_batch_upload.py
  -> 배치 메타데이터 생성
  -> ffmpeg로 video.mp4 렌더링
  -> YouTube private 업로드
  -> success/로 이동
```

## 폴더 구조

작업 중인 산출물:

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

업로드 성공 후 보관되는 산출물:

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

`workspace/`는 아직 처리 대기 중이거나 진행 중인 작업입니다.  
`success/`는 YouTube 업로드까지 성공한 완료 자산입니다.

## 트랙 상태

각 트랙에는 `track.json`이 있습니다.

일반적인 상태 흐름:

```text
generated -> imaged -> batched -> uploaded -> archived
```

주요 필드:

- `track_id`: 트랙 폴더 이름으로 쓰이는 ID
- `status`: 현재 상태
- `music_prompt`: 음악 생성에 사용한 최종 프롬프트
- `image_prompt`: 이미지 생성에 사용한 최종 프롬프트
- `duration_seconds`: 실제 오디오 길이
- `audio_path`: 보통 `audio.wav`
- `image_path`: 보통 `image.png`
- `batch_id`: 배치에 포함된 뒤 기록되는 배치 ID
- `created_at`: 생성 시각

## 배치 상태

각 배치에는 `batch.json`이 있습니다.

일반적인 상태 흐름:

```text
assembled -> rendered -> uploaded -> archived
```

주요 필드:

- `batch_id`: 배치 폴더 이름으로 쓰이는 ID
- `status`: 현재 상태
- `track_ids`: 이 배치에 포함된 10개 트랙 ID
- `video_path`: 렌더링된 MP4 경로, 보통 `video.mp4`
- `youtube_video_id`: YouTube 업로드 성공 후 기록되는 영상 ID
- `archive_pending`: 업로드는 됐지만 `success/` 이동이 끝나지 않았을 때 true
- `created_at`: 배치 생성 시각

한 번 `batch.json`이 만들어지면 포함된 10개 트랙 목록은 자동으로 바뀌지 않습니다. 남은 트랙은 다음 배치 대상이 됩니다.

## 프롬프트 구조

음악 프롬프트는 `configs/examples/music.yaml`의 구조화된 필드로 만듭니다.

사용 필드:

- `genre`
- `bpm_min`
- `bpm_max`
- `mood`
- `instruments`
- `texture`
- `vocals`
- `negative_rules`
- `prompt_variants`

기본 방향은 운동용 브라질리언 폰크입니다.

```text
Brazilian phonk, aggressive workout energy, distorted 808 bass,
driving cowbell lead, punchy drums, gritty street-gym texture.
```

설정 파일에는 고에너지 phonk 참고곡에서 착안한 내부 variant가 들어갑니다. 실제 API 프롬프트에는 참고곡 제목을 직접 넣지 않습니다. 대신 빠른 baile-funk 퍼커션, 공격적인 카우벨 리드, 어두운 distorted 808, rave synth pressure, 느슨한 syncopated groove, avant-garde tension 같은 안전한 설명으로 변환합니다.

이미지 프롬프트는 음악 프롬프트를 그대로 복사하지 않습니다. 음악 메타데이터를 바탕으로 시각 지시문을 만듭니다. 현재 이미지 variant는 사이버펑크 체육관, 보디빌더 실루엣, phonk 앨범커버 계열입니다. 모든 이미지 프롬프트에는 16:9, 텍스트 없음, 로고 없음, 워터마크 없음, 실존 아티스트 참조 없음 규칙이 들어갑니다.

새로 생성되는 `track.json`에는 아래 값이 기록됩니다.

- `music_variant`
- `image_variant`

## 렌더링

렌더링은 `ffmpeg`를 사용합니다.

현재 렌더러가 하는 일:

- 10개 오디오 파일을 순서대로 이어붙임
- 각 트랙 이미지와 해당 오디오 길이를 맞춰 이미지 concat 파일 생성
- 최종 `video.mp4` 생성

현재 한계:

- 시각 트랙은 정지 이미지를 길이에 맞춰 이어붙이는 방식입니다.
- 줌, 팬, 글로우, 그레인, GIF 느낌의 움직임은 아직 구현되지 않았습니다.

## YouTube 업로드

YouTube Data API와 OAuth refresh token을 사용합니다.

기본 업로드 설정:

- `privacyStatus`: `private`
- `categoryId`: `10`
- `made_for_kids`: false

`batch.json`에 이미 `youtube_video_id`가 있으면 중복 업로드를 피하는 방향으로 동작합니다.

## 실패와 재시도

하루 생성 실패:

- 음악 생성이 실패하면 배치에 사용할 완성 트랙으로 보지 않습니다.
- 음악은 성공했지만 이미지 생성이 실패하면 해당 트랙에 대해 이미지 생성만 다시 실행할 수 있습니다.

배치 생성 실패:

- `imaged` 상태 트랙이 10개 미만이면 배치 생성을 멈춥니다.

렌더링 실패:

- 배치 폴더는 `workspace/batches/`에 남습니다.
- 문제를 해결한 뒤 렌더링 또는 `run_batch_upload.py`를 다시 실행합니다.

업로드 실패:

- 렌더링된 배치는 `workspace/batches/`에 남습니다.
- 인증값이나 API 문제를 고친 뒤 업로드를 다시 시도합니다.

아카이브 실패:

- 업로드가 성공했다면 `youtube_video_id`는 유지되어야 합니다.
- `archive_pending=true`는 업로드는 끝났지만 `success/` 이동이 남았다는 뜻입니다.

## 비용 발생 지점

`--dry-run` 없이 실행하면 비용이 발생할 수 있습니다.

- Gemini/Lyria 음악 생성 API 사용량
- OpenAI 이미지 생성 API 사용량
- YouTube API quota 사용량

`--dry-run`은 외부 API를 호출하지 않으므로 API 비용이 발생하지 않아야 합니다.

## 보안 규칙

커밋하면 안 되는 것:

- `.env`
- OAuth token JSON 파일
- Google client secret JSON 파일
- 생성된 오디오, 이미지, GIF, 영상 파일
- `workspace/`
- `success/`

커밋 전 확인:

```bash
git status --short --untracked-files=all
git diff --cached --stat
git grep --cached -n -i -E "(api[_-]?key|secret|refresh[_-]?token|access[_-]?token|client[_-]?secret|authorization:|bearer )" -- .
```

스캔 결과에는 placeholder 이름이나 문서 예시만 나와야 합니다. 실제 키나 토큰 값이 나오면 커밋하면 안 됩니다.

## 검증 명령

테스트 실행:

```bash
python3 -m unittest discover -s tests -v
```

문법 컴파일:

```bash
python3 -m compileall -q src scripts tests
```

하루 생성 dry-run:

```bash
python3 scripts/run_daily.py --config configs/examples/music.yaml --dry-run
```

배치 dry-run:

```bash
python3 scripts/run_batch_upload.py --config configs/examples/upload.yaml --dry-run
```
