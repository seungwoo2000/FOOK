from __future__ import annotations
import os
from contextlib import contextmanager
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL이 없습니다. backend/.env에 Neon 연결 문자열을 설정하세요.')
if DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

@contextmanager
def db():
    with engine.begin() as conn:
        yield conn
