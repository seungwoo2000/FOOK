# FOOK 회원 기능 통합 메모

## 포함된 화면
- 회원가입, 로그인
- 프로필 입력 및 수정 진입
- 내 정보 대시보드
- 식단 기록
- 즐겨찾기
- PDF 보관함
- 장바구니 체크리스트
- 빈 화면, 오류 문구, 로그인 유도 흐름
- 화면 진입 및 버튼 상호작용 애니메이션

현재 프론트는 백엔드 인증 API가 없어도 UX를 확인할 수 있도록 localStorage 데모 저장소를 사용합니다. 운영 전에는 같은 화면을 유지하고 `/auth`, `/me`, `/meal-records`, `/favorites`, `/documents`, `/shopping-lists` API로 저장 계층을 교체해야 합니다.

## 권장 API
- POST `/auth/signup`
- POST `/auth/login`
- POST `/auth/refresh`
- POST `/auth/logout`
- GET/PATCH `/me/profile`
- GET/POST/DELETE `/meal-records`
- GET/POST/DELETE `/favorites`
- GET/POST/DELETE `/documents`
- GET/POST/PATCH/DELETE `/shopping-lists/{id}/items`

## 파일 저장
PDF 바이너리는 PostgreSQL에 직접 넣지 말고 S3, Cloudflare R2 또는 Supabase Storage에 업로드한 뒤 `user_documents.storage_key`만 저장하는 구조를 권장합니다.

## 보안
- 비밀번호는 Argon2id 또는 bcrypt 해시만 저장
- 액세스 토큰은 짧게, 리프레시 토큰은 해시 후 DB 저장
- 사용자 데이터 조회에는 항상 인증된 `user_id` 조건 적용
- Neon 연결 문자열은 서버 `.env`에만 보관
