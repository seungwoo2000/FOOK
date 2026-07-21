# -*- coding: utf-8 -*-
"""
FOOK 데이터 스토어 (DB 버전)

동작 방식:
- 환경변수 DATABASE_URL이 설정되어 있으면 PostgreSQL(Neon)에서 데이터를 읽는다.
- DATABASE_URL이 없거나 연결에 실패하면 자동으로 CSV/엑셀 파일 읽기로 폴백한다
  (data_store_csv.py, 기존 v1~v4에서 쓰던 방식 그대로 보존됨).

이 파일이 내보내는 이름(ALL_MENUS, MENU_INGREDIENTS, INGREDIENT_POOL,
CATEGORY_INDEX, DIET_PATTERNS, MEALS, get_menu_nutrition(), find_menu_slot(),
get_all_menu_master_rows(), get_diet_365(), find_ingredient_match() 등)은
data_store_csv.py와 완전히 동일하다. main.py/engine.py는 이 파일이 CSV를
읽는지 DB를 읽는지 전혀 알 필요가 없다 — 어느 쪽이든 같은 인터페이스를 준다.
"""
import os
import re
import sys

NUTRIENT_COLS = ["Energy", "Protein", "Potassium", "Phosphorus", "Sodium"]
MEALS = ["morning", "lunch", "dinner"]
SLOT_LABELS = ["밥", "국", "메인반찬", "서브반찬", "김치·절임"]
UI_CATEGORY_ORDER = ["밥&면", "국", "메인 반찬", "밑반찬", "간식류"]

_DATABASE_URL = os.environ.get("DATABASE_URL")
USING_DB = False  # main.py의 /health 같은 진단 엔드포인트에서 참고할 수 있도록 노출


def _load_from_csv():
    """CSV/엑셀 기반 로딩으로 폴백. data_store_csv.py의 심볼을 이 모듈 네임스페이스로 그대로 가져온다."""
    global ALL_MENUS, MENU_INGREDIENTS, MENU_RECIPE, INGREDIENT_POOL, CATEGORY_INDEX
    global DIET_PATTERNS, SLOT_MENU_POOL, MENU_SLOT_INDEX
    global _MENU_NUTRITION, _MENU_UI_CATEGORY

    import data_store_csv as _csv

    ALL_MENUS = _csv.ALL_MENUS
    MENU_INGREDIENTS = _csv.MENU_INGREDIENTS
    MENU_RECIPE = _csv.MENU_RECIPE
    INGREDIENT_POOL = _csv.INGREDIENT_POOL
    CATEGORY_INDEX = _csv.CATEGORY_INDEX
    DIET_PATTERNS = _csv.DIET_PATTERNS
    SLOT_MENU_POOL = _csv.SLOT_MENU_POOL
    MENU_SLOT_INDEX = _csv.MENU_SLOT_INDEX

    # data_store_csv.py는 get_menu_nutrition()이 내부 _mv_map을 직접 참조하므로,
    # 이 모듈의 공통 get_menu_nutrition()/get_ui_category()가 쓸 수 있도록
    # 매 메뉴에 대해 한 번씩 호출해 _MENU_NUTRITION/_MENU_UI_CATEGORY를 채워둔다.
    _MENU_NUTRITION = {name: _csv.get_menu_nutrition(name) for name in ALL_MENUS}
    _MENU_UI_CATEGORY = {name: _csv.get_ui_category(name) for name in ALL_MENUS}


def _load_from_db():
    """PostgreSQL(Neon)에서 참조 데이터를 읽어 CSV 버전과 동일한 자료구조로 채운다."""
    global ALL_MENUS, MENU_INGREDIENTS, MENU_RECIPE, INGREDIENT_POOL, CATEGORY_INDEX
    global DIET_PATTERNS, SLOT_MENU_POOL, MENU_SLOT_INDEX
    global _MENU_NUTRITION, _MENU_UI_CATEGORY

    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(_DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1) 재료 (카테고리 조인)
            cur.execute("""
                SELECT i.name, ic.name AS category, i.energy, i.protein,
                       i.potassium, i.phosphorus, i.sodium
                FROM ingredients i
                JOIN ingredient_categories ic ON ic.id = i.category_id
            """)
            INGREDIENT_POOL = {}
            CATEGORY_INDEX = {}
            for r in cur.fetchall():
                INGREDIENT_POOL[r["name"]] = {
                    "category": r["category"],
                    "Energy": float(r["energy"]), "Protein": float(r["protein"]),
                    "Potassium": float(r["potassium"]), "Phosphorus": float(r["phosphorus"]),
                    "Sodium": float(r["sodium"]),
                }
                CATEGORY_INDEX.setdefault(r["category"], []).append(r["name"])

            # 2) 메뉴 (카테고리 조인)
            cur.execute("""
                SELECT m.id, m.name, mc.name AS ui_category, m.energy, m.protein,
                       m.potassium, m.phosphorus, m.sodium, m.recipe_steps
                FROM menus m
                JOIN menu_categories mc ON mc.id = m.category_id
            """)
            menu_rows = cur.fetchall()
            ALL_MENUS = sorted(r["name"] for r in menu_rows)
            _MENU_NUTRITION = {
                r["name"]: {
                    "energy": float(r["energy"]), "protein": float(r["protein"]),
                    "potassium": float(r["potassium"]), "phosphorus": float(r["phosphorus"]),
                    "sodium": float(r["sodium"]),
                }
                for r in menu_rows
            }
            _MENU_UI_CATEGORY = {r["name"]: r["ui_category"] for r in menu_rows}
            MENU_RECIPE = {r["name"]: (r["recipe_steps"] or "") for r in menu_rows}
            _menu_id_to_name = {r["id"]: r["name"] for r in menu_rows}

            # 3) 메뉴별 재료 구성
            cur.execute("""
                SELECT mi.menu_id, mi.ingredient_name_raw, mi.amount_g
                FROM menu_ingredients mi
                ORDER BY mi.menu_id, mi.sort_order
            """)
            MENU_INGREDIENTS = {name: [] for name in ALL_MENUS}
            for r in cur.fetchall():
                menu_name = _menu_id_to_name.get(r["menu_id"])
                if menu_name:
                    MENU_INGREDIENTS[menu_name].append(
                        {"name": r["ingredient_name_raw"], "amount": float(r["amount_g"])}
                    )

            # 4) 365일 식단 패턴
            cur.execute("""
                SELECT day_number, meal_type, slot_index, menu_id
                FROM diet_calendar
                ORDER BY day_number, meal_type, slot_index
            """)
            _by_day = {}
            for r in cur.fetchall():
                d = _by_day.setdefault(r["day_number"], {"morning": [None]*5, "lunch": [None]*5, "dinner": [None]*5})
                name = _menu_id_to_name.get(r["menu_id"])
                d[r["meal_type"]][r["slot_index"]] = name

            max_day = max(_by_day.keys()) if _by_day else 0
            DIET_PATTERNS = []
            for d in range(1, max_day + 1):
                day = _by_day.get(d, {"morning": [None]*5, "lunch": [None]*5, "dinner": [None]*5})
                DIET_PATTERNS.append(day)

            # 5) 슬롯 통계 -> MENU_SLOT_INDEX (menu_slot_stats에서 최다 등장 슬롯 사용)
            cur.execute("""
                SELECT m.name, mss.slot_index, mss.occurrence_count
                FROM menu_slot_stats mss
                JOIN menus m ON m.id = mss.menu_id
                ORDER BY m.name, mss.occurrence_count DESC
            """)
            MENU_SLOT_INDEX = {}
            for r in cur.fetchall():
                MENU_SLOT_INDEX.setdefault(r["name"], r["slot_index"])  # 첫 번째(=최다) 것만 채택

            SLOT_MENU_POOL = {m: {i: set() for i in range(5)} for m in MEALS}
            for day in DIET_PATTERNS:
                for meal in MEALS:
                    for i, name in enumerate(day[meal]):
                        if name:
                            SLOT_MENU_POOL[meal][i].add(name)
    finally:
        conn.close()


_ING_NAMES = []
_NORM_INDEX = {}


def _normalize(s: str) -> str:
    base = s.split(",")[0]
    return re.sub(r"\s+", "", base)


def _build_ingredient_index():
    """INGREDIENT_POOL이 채워진 뒤 재료명 매칭용 보조 인덱스를 만든다 (DB/CSV 공통)."""
    global _ING_NAMES, _NORM_INDEX
    _ING_NAMES = list(INGREDIENT_POOL.keys())
    _NORM_INDEX = {}
    for name in _ING_NAMES:
        _NORM_INDEX.setdefault(_normalize(name), []).append(name)


def find_ingredient_match(raw_name: str):
    """메뉴마스터의 재료명을 영양DB(재료풀) 항목에 매칭. 완전일치 -> 정규화일치 -> 부분포함 순."""
    raw_name = raw_name.strip()
    if raw_name in INGREDIENT_POOL:
        return raw_name
    norm = _normalize(raw_name)
    if norm in _NORM_INDEX:
        return _NORM_INDEX[norm][0]
    candidates = [n for n in _ING_NAMES if norm and (norm in _normalize(n) or _normalize(n) in norm)]
    if candidates:
        candidates.sort(key=len)
        return candidates[0]
    return None


def get_menu_nutrition(menu_name: str):
    return _MENU_NUTRITION.get(menu_name)


def find_menu_slot(menu_name: str):
    return MENU_SLOT_INDEX.get(menu_name)


_SLOT_TO_UI_CATEGORY = {0: "밥&면", 1: "국", 2: "메인 반찬", 3: "밑반찬", 4: "밑반찬"}


def get_ui_category(menu_name: str) -> str:
    if _MENU_UI_CATEGORY and menu_name in _MENU_UI_CATEGORY:
        return _MENU_UI_CATEGORY[menu_name]
    slot = find_menu_slot(menu_name)
    return _SLOT_TO_UI_CATEGORY.get(slot, "메인 반찬")


def get_menu_master_row(menu_name: str):
    n = get_menu_nutrition(menu_name)
    if not n:
        return None
    return [menu_name, get_ui_category(menu_name), n["energy"], n["protein"], n["potassium"], n["phosphorus"], n["sodium"]]


def get_all_menu_master_rows():
    rows = []
    for name in ALL_MENUS:
        row = get_menu_master_row(name)
        if row:
            rows.append(row)
    return rows


def get_diet_365():
    result = []
    for day in DIET_PATTERNS:
        row = []
        for meal in MEALS:
            names = [n for n in day[meal] if isinstance(n, str)]
            row.append(names)
        result.append(row)
    return result


# ---------------------------------------------------------------------------
# 초기화: DATABASE_URL이 있으면 DB에서, 없거나 실패하면 CSV에서 로드
# ---------------------------------------------------------------------------
_MENU_NUTRITION = {}
_MENU_UI_CATEGORY = {}

if _DATABASE_URL:
    try:
        print("[data_store] DATABASE_URL 감지 — PostgreSQL(Neon)에서 데이터를 불러옵니다.", file=sys.stderr)
        _load_from_db()
        USING_DB = True
        print(f"[data_store] DB 로드 완료: 메뉴 {len(ALL_MENUS)}개, 재료 {len(INGREDIENT_POOL)}개", file=sys.stderr)
    except Exception as e:
        print(f"[data_store] DB 연결 실패({e}) — CSV 파일로 폴백합니다.", file=sys.stderr)
        _load_from_csv()
        USING_DB = False
else:
    print("[data_store] DATABASE_URL 미설정 — CSV 파일에서 데이터를 불러옵니다.", file=sys.stderr)
    _load_from_csv()
    USING_DB = False

_build_ingredient_index()
