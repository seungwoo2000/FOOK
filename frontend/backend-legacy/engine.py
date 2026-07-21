# -*- coding: utf-8 -*-
"""
FOOK 판정 & 대체 엔진
1) 한 끼 5대 영양소 판정 (체중 기반 기준선)
2) 초과 시 재료 단위 대체 탐색 (같은 카테고리 내 인/단백질/칼륨/나트륨이 낮은 후보로 치환)
   -> 실제 KLUE-BERT+KNN 모델이 붙기 전까지의 대체 로직. 조리과정 텍스트 기반 문맥 임베딩
      대신, '카테고리 일치 + 영양소 벡터 근접도'로 후보를 스코어링한다.
"""
import random
import data_store as ds

# ---------------------------------------------------------------------------
# 체중 + 투석유형 기반 한 끼 영양 기준선
#  - 단백질: 혈액투석 1.1~1.4 g/kg/day (표준체중), 복막투석 1.2~1.5 g/kg/day
#    (복막투석은 투석액을 통한 단백질 손실이 하루 10~15g 추가로 발생해 혈액투석보다 더 필요)
#  - 나트륨: 혈액투석 2,000mg/day 이내로 엄격 제한, 복막투석은 비교적 여유(약 3,000mg/day)
#  - 칼륨:   혈액투석 2,000mg/day 미만, 복막투석은 3,000~4,000mg/day까지 가능
#            (복막투석이 칼륨 제거 효율이 더 높기 때문)
#  - 인:     투석유형과 무관하게 800~1,000mg/day 미만 (단백질 섭취와 함께 증가하므로 공통 관리)
#  - 열량:   체중 x 30~35 kcal/day 공통
# 근거: 대한신장학회/삼성서울병원 혈액투석·복막투석 식이 가이드
# ---------------------------------------------------------------------------
DIALYSIS_TYPES = {"hemodialysis", "peritoneal"}  # 혈액투석 / 복막투석

_DIALYSIS_PROFILE = {
    "hemodialysis": {"protein_range": (1.1, 1.4), "potassium_daily": 2000, "sodium_daily": 2000},
    "peritoneal": {"protein_range": (1.2, 1.5), "potassium_daily": 3500, "sodium_daily": 3000},
}


def get_targets(weight: float, dialysis_type: str = "hemodialysis"):
    profile = _DIALYSIS_PROFILE.get(dialysis_type, _DIALYSIS_PROFILE["hemodialysis"])
    p_lo, p_hi = profile["protein_range"]
    per_day_protein = (p_lo * weight, p_hi * weight)
    per_day_energy = (28 * weight, 32 * weight)
    return {
        "energy": (round(per_day_energy[0] / 3), round(per_day_energy[1] / 3)),
        "protein": (round(per_day_protein[0] / 3, 1), round(per_day_protein[1] / 3, 1)),
        "potassium": round(profile["potassium_daily"] / 3),
        "phosphorus": round(900 / 3),
        "sodium": round(profile["sodium_daily"] / 3),
    }


RANGE_KEYS = {"energy", "protein"}  # 범위형 판정 (하한~상한)
CAP_KEYS = {"potassium", "phosphorus", "sodium"}  # 상한형 판정


def judge_nutrient(key, value, target):
    if key in RANGE_KEYS:
        lo, hi = target
        return lo <= value <= hi
    return value <= target


def nutrient_direction(key, value, target):
    """'over'(초과, 낮춰야 함) / 'under'(부족, 높여야 함) / 'ok' 반환."""
    if key in RANGE_KEYS:
        lo, hi = target
        if value > hi:
            return "over"
        if value < lo:
            return "under"
        return "ok"
    return "over" if value > target else "ok"


# ---------------------------------------------------------------------------
# 한 끼 메뉴 조합 생성 (밥/국/메인/서브/김치) - diet 패턴에서 샘플링
# ---------------------------------------------------------------------------
def generate_meal(anchor_menu: str = None, anchor_ingredient: str = None, rng: random.Random = None):
    rng = rng or random
    day = rng.choice(ds.DIET_PATTERNS)
    meal_key = rng.choice(ds.MEALS)
    meal = [m for m in day[meal_key] if isinstance(m, str)]

    anchor = None
    if anchor_menu and anchor_menu in ds.MENU_INGREDIENTS:
        anchor = anchor_menu
        slot = ds.find_menu_slot(anchor_menu)
        if slot is not None and slot < len(meal):
            meal[slot] = anchor_menu
        elif anchor_menu not in meal:
            meal.append(anchor_menu)
    elif anchor_ingredient:
        # 재료가 포함된 메뉴 중 하나를 anchor로 선택
        candidates = [
            m for m, ings in ds.MENU_INGREDIENTS.items()
            if any(anchor_ingredient in ing["name"] for ing in ings)
        ]
        if candidates:
            anchor = rng.choice(candidates)
            slot = ds.find_menu_slot(anchor)
            if slot is not None and slot < len(meal):
                meal[slot] = anchor
            elif anchor not in meal:
                meal.append(anchor)

    # meal 안의 메뉴 중 메뉴마스터에 없는 것 제거 (조리법/재료 없음)
    meal = [m for m in meal if m in ds.MENU_INGREDIENTS]
    return meal, anchor


def sum_nutrition(meal):
    total = {k: 0.0 for k in ["energy", "protein", "potassium", "phosphorus", "sodium"]}
    for m in meal:
        n = ds.get_menu_nutrition(m)
        if n:
            for k in total:
                total[k] += n[k]
    return {k: round(v, 1) for k, v in total.items()}


NUTRIENT_LABEL = {
    "energy": "열량", "protein": "단백질", "potassium": "칼륨",
    "phosphorus": "인", "sodium": "나트륨",
}
# 재료 영양DB 컬럼명 매핑
COL_MAP = {
    "energy": "Energy", "protein": "Protein", "potassium": "Potassium",
    "phosphorus": "Phosphorus", "sodium": "Sodium",
}


def ingredient_vector(name):
    info = ds.INGREDIENT_POOL.get(name)
    if not info:
        return None
    return info


def score_candidate(cand_info, target_keys):
    """대체 후보 스코어: 문제 영양소(target_keys) 총합이 낮을수록 우선."""
    return sum(cand_info[COL_MAP[k]] for k in target_keys)


def _same_food_group(orig_name: str, cand_name: str) -> bool:
    """조리상태 차이만 나는 동일 식재료(예: 쌀 생것 vs 밥)를 걸러내기 위한 느슨한 필터.
    같은 '기본명'(콤마 앞 첫 토큰)을 공유하면 동일 식품군으로 보고 대체 후보에서 제외."""
    base_o = orig_name.split(",")[0].strip()
    base_c = cand_name.split(",")[0].strip()
    return base_o == base_c


def _form_tag(name: str) -> str:
    """재료명의 형태 태그 추출: 생것/가공품(육수,액젓,통조림 등)/기타 조미료 등으로 대략 분류.
    같은 형태 태그를 가진 재료끼리만 대체하여 '오징어(생것) -> 멸치육수' 같은
    주재료-조미료 간 부적절한 대체를 막는다."""
    n = name
    if any(w in n for w in ["육수", "액젓", "젓갈", "장", "식초", "소스", "가루", "기름", "설탕", "물엿"]):
        return "seasoning"
    if any(w in n for w in ["과자", "강정", "스낵", "빵", "쿠키", "파이"]):
        return "snack"
    if any(w in n for w in ["통조림", "냉동", "말린것", "튀김", "반건조"]):
        return "processed"
    return "fresh"


_WATER_LIKE = {"생수", "물", "육수", "정수"}


_SYNONYMS = {
    "돈육": "돼지고기", "돈": "돼지고기", "우육": "소고기", "계육": "닭고기",
    "난": "달걀", "육": "고기",
}


def _expand_synonyms(text: str) -> str:
    for k, v in _SYNONYMS.items():
        if k in text:
            text = text + v  # 동의어를 이어붙여 포함 매칭이 되도록
    return text


def _is_core_ingredient(menu_name: str, ing_name: str, amt: float, menu_ings: list) -> bool:
    """핵심 식재료 판정. 다음 중 하나라도 해당하면 대체 대상에서 제외한다.
    1) 김치/깍두기/장아찌/젓갈 등 절임·발효 식품군 (형태 자체가 요리 정체성)
    2) 해당 메뉴 내에서 중량이 가장 큰 재료 (물/육수류 제외) - 그 요리의 주재료로 간주
    3) 재료명(동의어 포함)이 요리명 문자열에 포함되는 경우 (예: '돈육김치찌개'의 '돼지고기')
    """
    base = ing_name.split(",")[0].strip()
    if base in ("김치", "깍두기", "장아찌", "젓갈"):
        return True
    solid_ings = [i for i in menu_ings if i["name"].split(",")[0].strip() not in _WATER_LIKE]
    if solid_ings and base not in _WATER_LIKE:
        max_amt = max(i["amount"] for i in solid_ings)
        if amt >= max_amt:  # 이 메뉴에서(물 제외) 가장 양이 많은(=주) 재료
            return True
    expanded_menu = _expand_synonyms(menu_name)
    if len(base) >= 2 and base in expanded_menu:
        return True
    return False


_GRAIN_BASES = {"멥쌀", "찹쌀", "보리", "현미", "잡곡", "흑미", "귀리"}


def _grain_compatible(orig_name: str, cand_name: str) -> bool:
    """곡류 카테고리 내에서는 '밥/죽류'끼리만 대체하도록 제한
    (예: 백미밥의 쌀이 국수·과자류로 바뀌는 것을 방지)."""
    orig_base = orig_name.split(",")[0].strip()
    if orig_base not in _GRAIN_BASES:
        return True  # 곡류가 아니면 이 규칙 미적용
    cand_base = cand_name.split(",")[0].strip()
    return cand_base in _GRAIN_BASES


def find_substitute(ingredient_name, over_keys, top_k=5):
    """
    같은 카테고리 + 같은 형태(생것/가공품/조미료) 내에서, 초과된 영양소(over_keys)
    합산치가 더 낮은 대체 후보를 찾는다.
    Returns: (matched_original_name, [(cand_name, cand_info, delta_desc), ...])
    """
    matched = ds.find_ingredient_match(ingredient_name)
    if not matched:
        return None, []
    orig = ds.INGREDIENT_POOL[matched]
    cat = orig["category"]
    pool = ds.CATEGORY_INDEX.get(cat, [])
    orig_form = _form_tag(matched)

    orig_score = score_candidate(orig, over_keys)
    scored = []
    for cand in pool:
        if cand == matched or _same_food_group(matched, cand):
            continue
        if _form_tag(cand) != orig_form:
            continue
        if not _grain_compatible(matched, cand):
            continue
        info = ds.INGREDIENT_POOL[cand]
        cand_score = score_candidate(info, over_keys)
        if cand_score < orig_score:
            scored.append((cand, info, cand_score))
    scored.sort(key=lambda x: x[2])
    return matched, scored[:top_k]


def apply_substitution(meal, over_keys, anchor=None, max_swaps=4):
    """
    초과된 영양소 목록(over_keys)에 대해, meal 내 재료를 문제 기여도가 큰 순으로 정렬해
    상위 max_swaps개까지 대체를 시도한다.
    - 모든 메뉴의 핵심 식재료(요리명에 포함된 재료, 예: '애호박볶음'의 '애호박')는
      요리 정체성을 지키기 위해 대체 대상에서 제외한다.
    Returns: swap_log (list of dict), dish_ingredients: {메뉴명: [(재료명, 조정량g), ...]}
    """
    # 1) 후보 재료 수집 + 기여도 계산 (핵심/주 식재료는 항상 보호)
    entries = []  # (contribution, menu, ing_name, amt, matched)
    for menu in meal:
        menu_ings = ds.MENU_INGREDIENTS.get(menu, [])
        for ing in menu_ings:
            name, amt = ing["name"], ing["amount"]
            if _is_core_ingredient(menu, name, amt, menu_ings):
                continue  # 요리 정체성 보호 (주재료, 김치류, 요리명 포함 재료)
            matched = ds.find_ingredient_match(name)
            if not matched:
                continue
            info = ds.INGREDIENT_POOL[matched]
            contribution = sum(info[COL_MAP[k]] * amt / 100 for k in over_keys)
            entries.append((contribution, menu, name, amt, matched))

    entries.sort(key=lambda x: -x[0])  # 기여도 큰 순

    swap_log = []
    swapped_keys = set()  # (menu, matched) 중복 대체 방지
    for contribution, menu, name, amt, matched in entries:
        if len(swap_log) >= max_swaps:
            break
        if contribution < 10:  # 기여도 미미한 재료는 건드리지 않음
            continue
        _, candidates = find_substitute(name, over_keys)
        if not candidates:
            continue
        best_name, best_info, _ = candidates[0]
        orig_info = ds.INGREDIENT_POOL[matched]
        swap_log.append({
            "dish": menu,
            "from": matched,
            "to": best_name,
            "category": orig_info["category"],
            "reason_keys": over_keys,
            "from_values": {k: orig_info[COL_MAP[k]] for k in over_keys},
            "to_values": {k: best_info[COL_MAP[k]] for k in over_keys},
            "amount": amt,
        })
        swapped_keys.add((menu, matched))

    # 2) dish_ingredients 구성 (대체 반영)
    swap_map = {(s["dish"], s["from"]): s["to"] for s in swap_log}
    dish_ingredients = {}
    for menu in meal:
        new_ings = []
        for ing in ds.MENU_INGREDIENTS.get(menu, []):
            matched = ds.find_ingredient_match(ing["name"]) or ing["name"]
            use_name = swap_map.get((menu, matched), ing["name"])
            new_ings.append((use_name, round(ing["amount"])))
        dish_ingredients[menu] = new_ings

    return swap_log, dish_ingredients


def recompute_nutrition_after_swap(meal, swap_log):
    """대체 후 메뉴별 영양소 재계산 (100g 기준값 기반 근사 재계산)."""
    total = {k: 0.0 for k in ["energy", "protein", "potassium", "phosphorus", "sodium"]}
    swap_map = {(s["dish"], s["from"]): s["to"] for s in swap_log}

    for menu in meal:
        ings = ds.MENU_INGREDIENTS.get(menu, [])
        for ing in ings:
            name = ing["name"]
            amt = ing["amount"]
            matched = ds.find_ingredient_match(name)
            key = (menu, matched)
            use_name = swap_map.get(key, matched)
            info = ds.INGREDIENT_POOL.get(use_name)
            if info:
                for k, col in COL_MAP.items():
                    total[k] += info[col] * amt / 100
    return {k: round(v, 1) for k, v in total.items()}
