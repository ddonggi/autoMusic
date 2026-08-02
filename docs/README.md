# AutoMusic 문서 홈

GitHub에서 보기 좋은 위키형 문서 인덱스입니다. 운영 절차는 [프로그램 가이드](program-guide.md)를 기준으로 관리합니다.

## 문서 목록

| 문서 | 설명 |
| --- | --- |
| [프로그램 가이드](program-guide.md) | 전체 구조, 수동 음악 생성, 배치 자동화, YouTube 업로드, 재시도 |
| [보안 및 커밋 안전 가이드](security.md) | API 키, OAuth 토큰, SMTP 비밀번호, 생성물 커밋 방지 |

## 문서 구조

```mermaid
flowchart TD
    A[README.md] --> B[docs/README.md 문서 홈]
    B --> C[program-guide.md 프로그램 가이드]
    B --> D[security.md 보안 가이드]
    C --> E[설치/환경변수]
    C --> F[수동 음악 생성]
    C --> G[배치 자동화]
    C --> H[실패 재시도]
    D --> I[커밋 금지 파일]
    D --> J[비밀값 스캔]
```

## 운영자가 자주 보는 항목

- 매일 자동 실행 설치: [프로그램 가이드 - macOS 매일 정오 자동 실행](program-guide.md#macos-매일-정오-자동-실행)
- 실패 후 재시도: [프로그램 가이드 - 실패와 재시도](program-guide.md#실패와-재시도)
- Gmail 알림 조건: [프로그램 가이드 - Gmail 알림](program-guide.md#gmail-알림)
- 커밋 전 보안 점검: [보안 및 커밋 안전 가이드](security.md)
