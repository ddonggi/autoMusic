# 백엔드
- 목적: 프롬프트 미리보기와 실제 생성의 일치, 안전한 결과 조회.
- 입력: config/categories/prompts/music/web_app/web_jobs 및 관련 테스트.
- Phase 1 담당 파일: outputs/local-dashboard/phase-1/backend.md.
- 조사 범위: 설정 상속, 변형 선택, 프롬프트 전달, 비동기 작업, 결과 저장과 다운로드.
- 산출물: 근거 파일을 포함한 현황, API 계약 제안, 데이터 흐름, 이후 구현 파일 소유권.
- 완료 조건: 미리보기 이후 재추첨 방지, 중복 실행, 재시작, 경로 검증을 포함하고 사실·추정·확인 필요 구분.
- 제품 파일 수정은 Phase 2 승인 후 별도 배정한다. 루트 AGENTS.md의 승인·보고 규칙을 따른다.

## Phase 2 배정
- 사용자 승인: `진행. Phase 2 구현 시작해줘.`
- 작업방: autoMusic · 백엔드 · 로컬 대시보드 (`01a16478-f722-7751-9cd0-6be145c44d45`).
- 확정 계약·소유권: outputs/local-dashboard/phase-2/plan.md. 다른 팀의 library.py와 scheduler.py는 연결만 한다.
- 완료 보고: outputs/local-dashboard/phase-2/backend.md.
- Phase 2 승인으로 Phase 3를 시작하지 않는다.
