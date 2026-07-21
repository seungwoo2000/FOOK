# FOOK Backend v9

Excel/CSV/TensorFlow 파일 없이 Neon PostgreSQL만 사용합니다.

1. Neon SQL Editor에서 `sql/001_full_schema.sql` 실행
2. `.env.example`을 `.env`로 복사하고 `DATABASE_URL` 입력
3. `python -m venv .venv`
4. Windows: `.\.venv\Scripts\Activate.ps1`
5. `pip install -r requirements.txt`
6. `python -m uvicorn server_FOOK:app --reload --port 8000`
7. `http://127.0.0.1:8000/health`, `/docs` 확인

기존 참조 테이블 `menus`, `menu_ingredients`, `diet_calendar`가 필요합니다.
