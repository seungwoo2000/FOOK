# FOOK Total Integrated v9

Neon PostgreSQL 전용 통합본입니다. 기존 Excel/CSV/TensorFlow 의존성을 제거했습니다.

## 최초 1회
1. Neon SQL Editor에서 `backend/sql/001_full_schema.sql` 실행
2. `backend/.env.example`을 `backend/.env`로 복사하고 DATABASE_URL 입력
3. 백엔드 설치 및 실행
4. 프론트엔드 설치 및 실행

## 백엔드
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn server_FOOK:app --reload --port 8000
```
확인: http://127.0.0.1:8000/health, http://127.0.0.1:8000/docs

## 프론트엔드
```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```
확인: http://localhost:5173

## 포함 기능
- Neon 메뉴/재료/365일 식단 조회
- 회원가입, 로그인, 로그아웃, DB 세션
- 사용자 프로필 DB 저장
- 식단 기록, 즐겨찾기, PDF 메타데이터, 장바구니 API
- 모바일 화면 전환 및 애니메이션
- PDF 생성

참조 데이터 테이블 `menus`, `menu_ingredients`, `diet_calendar`는 기존 Neon DB에 있어야 합니다.
