# FOOK 통합 분석 및 적용 내역

## 확인한 자료

- `FOOKK.zip`: 초기 FastAPI 백엔드, Neon/CSV 데이터 저장소, 규칙 기반 식단 생성·식재료 대체 엔진
- `FOOK_app(1).zip`: 수정된 React+Vite 프론트엔드
- `samples-...zip`: 수정 서버의 실제 API 응답 샘플
- `README(1).md`: 수정 서버 `server_FOOK.py` 인수인계 문서
- 기존 FOOK 프로토타입 v5-dataflow: 온보딩, 프로필, 검색, 분석, 조정, 레시피, PDF 흐름

## 분석 결론

1. 초기 백엔드에는 실제 동작하는 규칙 기반 생성·대체 알고리즘이 있습니다.
   - 365일 식단 패턴 샘플링
   - 메뉴 또는 식재료 앵커 삽입
   - 체중 기반 5대 영양소 판정
   - 동일 카테고리·형태·영양 벡터 기반 대체 후보 선택
   - 주재료·김치류·메뉴 정체성 보호 규칙

2. 수정 서버는 초기 버전보다 발전했습니다.
   - `/generate`, `/generate_day`, `/recipe`
   - `consumed`와 `meals_left`를 활용한 하루 영양 예산 방식
   - `changes`, `dish_ingredients`, `recipe_source`, `intake` 응답
   - TensorFlow 모델 로딩 정황이 있으나, 실제 `server_FOOK.py` 및 모델 파일은 전달된 ZIP에 없습니다.

3. 수정 프론트는 API 호출 예시로는 유용하지만, 기존 FOOK 앱 디자인·온보딩·PDF 흐름보다 단순합니다.

## 이번 통합본에 적용한 사항

- 기존 완성형 FOOK 모바일 UI를 기준으로 유지
- `/menus`, `/ingredients`, `/generate` API 연동
- `VITE_API_URL` 환경변수 적용
- 서버 연결 실패 시 내장 데이터로 안전하게 미리보기 진행
- 음식 검색 / 재료 검색 / 랜덤 추천 3가지 생성 모드
- API 응답의 `meal`, `nutrition`, `changes`를 화면에 반영
- 로딩 UI 유지 및 실제 요청 완료 후 결과 화면 이동
- 홈 아이콘과 로고 클릭 시 온보딩이 아니라 `/home`으로 이동
- 온보딩 버튼 구조 수정
  - 첫 화면: `다음`만 표시
  - 중간 화면: `이전` + `다음`
  - 마지막 화면: `맞춤 식단 시작하기` 단일 버튼
- 기존 프로필, 혈액투석 전용 처리, 복막투석 개발 중 안내, 영양 분석, 조정 비교, 레시피, A4 PDF 기능 유지
- 수정 서버 API 응답 샘플과 인수인계 문서를 프로젝트에 포함
- 초기 백엔드는 `backend-legacy/`에 참고용으로 포함

## 실행

```bash
cp .env.example .env
npm install
npm run dev
```

`.env`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

## 아직 필요한 파일

수정된 알고리즘을 실제로 실행하려면 팀원에게 아래를 받아야 합니다.

- `server_FOOK.py`
- 해당 서버가 import하는 Python 모듈 전체
- TensorFlow/Keras 모델 및 토크나이저 파일
- `requirements.txt` 또는 conda 환경 파일
- DB 스키마/마이그레이션
- `.env.example`

실제 `.env`, Neon 비밀번호, `OPENAI_API_KEY`는 공유 파일에 포함하지 않아야 합니다.
