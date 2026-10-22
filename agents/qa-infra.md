# QA·운영
- 목적: 실제 환경에 근거한 스케줄러 제어 설계 및 회귀 검증 기준.
- 입력: launchd/automation 코드, 설치 스크립트, 테스트, 운영 문서.
- Phase 1 담당 파일: outputs/local-dashboard/phase-1/qa-infra.md.
- 조사 범위: 읽기 전용 스케줄러 상태 확인, 실행 환경, 테스트 범위, 로컬 제어 보안.
- 산출물: 근거 있는 상태, 지속적인 켜기·끄기 제안, 검증 행렬과 이후 파일 소유권.
- 완료 조건: 확인된 상태와 미확인 사항 구분, 실제 API 호출 없이 검증하는 방법 제시.
- 스케줄러 변경, 유료 생성, 업로드, 배포 금지. 제품 파일 수정은 Phase 2 승인 후 별도 배정한다.
- 루트 AGENTS.md의 승인·보고 규칙을 따른다.

## Phase 2 배정
- 사용자 승인: `진행. Phase 2 구현 시작해줘.`
- 작업방: autoMusic · QA·운영 · 로컬 대시보드 (`01a16479-02c4-7593-8ebb-a1a32c7c7996`).
- 확정 계약·소유권: outputs/local-dashboard/phase-2/plan.md. scheduler.py, run_automation.py, test_scheduler_control.py 담당.
- 완료 보고: outputs/local-dashboard/phase-2/qa-infra.md.
- 실제 스케줄러 변경은 테스트에 포함하지 않는다. Phase 2 승인으로 Phase 3를 시작하지 않는다.
