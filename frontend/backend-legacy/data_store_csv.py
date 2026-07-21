# -*- coding: utf-8 -*-
"""
FOOK 데이터 스토어
- 메뉴마스터(재료/조리과정), 메뉴영양(5대 영양소), 재료풀(대체후보), 식단패턴(밥/국/메인/서브/김치)
을 로드하고 메모리에 인덱싱한다.
"""
import re
import pandas as pd

NUTRIENT_COLS = ["Energy", "Protein", "Potassium", "Phosphorus", "Sodium"]

# ---------------------------------------------------------------------------
# 1) 메뉴마스터 (메뉴명 -> [(재료명, 재료량)], 조리과정)
# ---------------------------------------------------------------------------
_xl = pd.ExcelFile("FOOK_menu_master.xlsx")
_mm = _xl.parse("메뉴마스터")
_mm["메뉴명"] = _mm["메뉴명"].ffill()
_mm["조리과정"] = _mm.groupby("메뉴명")["조리과정"].transform(lambda s: s.ffill())

_mv = _xl.parse("메뉴영양")  # 메뉴명, 열량, 단백질, 칼륨, 인, 나트륨
_mv_map = {
    row["메뉴명"]: {
        "energy": float(row["열량"]),
        "protein": float(row["단백질"]),
        "potassium": float(row["칼륨"]),
        "phosphorus": float(row["인"]),
        "sodium": float(row["나트륨"]),
    }
    for _, row in _mv.iterrows()
}

MENU_INGREDIENTS = {}  # 메뉴명 -> [{"name":..,"amount":..}, ...]
MENU_RECIPE = {}  # 메뉴명 -> 조리과정 텍스트
for menu_name, grp in _mm.groupby("메뉴명"):
    ings = []
    for _, r in grp.iterrows():
        if pd.notna(r["재료명"]) and pd.notna(r["재료량"]):
            ings.append({"name": str(r["재료명"]).strip(), "amount": float(r["재료량"])})
    MENU_INGREDIENTS[menu_name] = ings
    recipe_text = grp["조리과정"].iloc[0]
    MENU_RECIPE[menu_name] = str(recipe_text).strip() if pd.notna(recipe_text) else ""

ALL_MENUS = sorted(MENU_INGREDIENTS.keys())

# ---------------------------------------------------------------------------
# 2) 재료풀 (재료명 -> 카테고리 + 5대 영양소, 100g 기준)
# ---------------------------------------------------------------------------
_ing = pd.read_csv("FOOK_ingredients_kor.csv", encoding="utf-8-sig")
_ing = _ing.rename(columns={_ing.columns[0]: "name"})

INGREDIENT_POOL = {}  # name -> {"category":.., "Energy":.., ...} (100g 기준값)
CATEGORY_INDEX = {}  # category -> [name, ...]
for _, r in _ing.iterrows():
    name = str(r["name"]).strip()
    cat = str(r["Category"]).strip()
    INGREDIENT_POOL[name] = {
        "category": cat,
        "Energy": float(r["Energy"]),
        "Protein": float(r["Protein"]),
        "Potassium": float(r["Potassium"]),
        "Phosphorus": float(r["Phosphorus"]),
        "Sodium": float(r["Sodium"]),
    }
    CATEGORY_INDEX.setdefault(cat, []).append(name)

_ING_NAMES = list(INGREDIENT_POOL.keys())


def _normalize(s: str) -> str:
    """비교용 정규화: 쉼표 이하 수식어 제거, 공백 제거"""
    base = s.split(",")[0]
    return re.sub(r"\s+", "", base)


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
    # 부분 포함 매칭 (가장 이름이 짧은 후보 우선)
    candidates = [n for n in _ING_NAMES if norm and (norm in _normalize(n) or _normalize(n) in norm)]
    if candidates:
        candidates.sort(key=len)
        return candidates[0]
    return None


# ---------------------------------------------------------------------------
# 3) 식단 패턴 (365일 x 아침/점심/저녁 x [밥,국,메인,서브,김치])
# ---------------------------------------------------------------------------
_diet = pd.read_csv("FOOK_diet_1_12_kor.csv", encoding="cp949", index_col=0)
SLOT_LABELS = ["밥", "국", "메인반찬", "서브반찬", "김치·절임"]
MEALS = ["morning", "lunch", "dinner"]

DIET_PATTERNS = []  # [{"morning":[m1..m5], "lunch":[...], "dinner":[...]}, ...]
for _, row in _diet.iterrows():
    day = {}
    for meal in MEALS:
        day[meal] = [row[f"{meal}_{i}"] for i in range(1, 6)]
    DIET_PATTERNS.append(day)

# 슬롯별(카테고리별) 메뉴 후보 풀 (밥류 후보, 국류 후보 ...) - 랜덤/치환용
SLOT_MENU_POOL = {m: {i: set() for i in range(5)} for m in MEALS}
for day in DIET_PATTERNS:
    for meal in MEALS:
        for i, name in enumerate(day[meal]):
            if pd.notna(name):
                SLOT_MENU_POOL[meal][i].add(name)

# 메뉴명이 어느 슬롯(밥/국/메인/서브/김치)에 주로 등장하는지 인덱스
MENU_SLOT_INDEX = {}  # menu_name -> slot_idx (0~4)
for meal in MEALS:
    for slot_idx, names in SLOT_MENU_POOL[meal].items():
        for n in names:
            MENU_SLOT_INDEX.setdefault(n, slot_idx)


def get_menu_nutrition(menu_name: str):
    """메뉴 1인분 기준 5대 영양소 딕셔너리 반환 (메뉴영양 시트 기준)."""
    return _mv_map.get(menu_name)


def find_menu_slot(menu_name: str):
    return MENU_SLOT_INDEX.get(menu_name)


# ---------------------------------------------------------------------------
# 4) 프론트(UI) 카테고리 매핑: 슬롯(밥/국/메인/서브/김치) -> 5대 UI 카테고리
#    프론트는 ["밥&면", "국", "메인 반찬", "밑반찬", "간식류"] 5개로 메뉴를 분류해 보여준다.
#    슬롯3(서브반찬)과 슬롯4(김치·절임)는 모두 "밑반찬"으로 합친다. "간식류"는
#    현재 데이터에 해당 항목이 없어 비어 있다(추후 별도 간식 데이터 연동 시 채워짐).
# ---------------------------------------------------------------------------
UI_CATEGORY_ORDER = ["밥&면", "국", "메인 반찬", "밑반찬", "간식류"]
_SLOT_TO_UI_CATEGORY = {0: "밥&면", 1: "국", 2: "메인 반찬", 3: "밑반찬", 4: "밑반찬"}


def get_ui_category(menu_name: str) -> str:
    slot = find_menu_slot(menu_name)
    return _SLOT_TO_UI_CATEGORY.get(slot, "메인 반찬")  # 슬롯 정보 없으면 기본값


def get_menu_master_row(menu_name: str):
    """프론트가 기대하는 [name, category, energy, protein, potassium, phosphorus, sodium] 포맷."""
    n = get_menu_nutrition(menu_name)
    if not n:
        return None
    return [
        menu_name,
        get_ui_category(menu_name),
        n["energy"], n["protein"], n["potassium"], n["phosphorus"], n["sodium"],
    ]


def get_all_menu_master_rows():
    """ALL_MENUS 전체를 프론트 MENU_MASTER 배열 포맷으로 변환."""
    rows = []
    for name in ALL_MENUS:
        row = get_menu_master_row(name)
        if row:
            rows.append(row)
    return rows


def get_diet_365():
    """DIET_PATTERNS를 프론트 DIET_365 포맷([[morning[], lunch[], dinner[]], ...])으로 변환.
    None(결측) 슬롯은 제거해 프론트에서 다루기 쉽게 한다."""
    result = []
    for day in DIET_PATTERNS:
        row = []
        for meal in MEALS:
            names = [n for n in day[meal] if isinstance(n, str)]
            row.append(names)
        result.append(row)
    return result
