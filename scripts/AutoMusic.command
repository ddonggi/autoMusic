#!/bin/zsh

PROJECT_ROOT="/Users/dglee/workspace/autoMusic"
PYTHON="$PROJECT_ROOT/.worktrees/automusic-pipeline/.venv/bin/python"

cd "$PROJECT_ROOT" || exit 1
if [[ ! -x "$PYTHON" ]]; then
  printf 'Python 환경을 찾을 수 없습니다: %s\n' "$PYTHON"
  read '?Enter를 누르면 종료합니다.'
  exit 1
fi

printf '\nAutoMusic: http://127.0.0.1:8100\n'
printf '서버 시작 메시지가 나오면 위 주소를 브라우저에서 여세요.\n'
printf '종료: 이 창에서 Control+C. 진행 중인 음악 생성이 없는지 먼저 확인하세요.\n'
printf '다른 포트에서 이미 실행 중이라면 기존 서버를 먼저 종료하세요.\n\n'
"$PYTHON" scripts/run_web.py --host 127.0.0.1 --port 8100
result=$?
if (( result != 0 )); then
  printf '\n서버가 종료되었습니다. 위 오류를 확인하세요.\n'
  read '?Enter를 누르면 창을 닫을 수 있습니다.'
fi
exit "$result"
