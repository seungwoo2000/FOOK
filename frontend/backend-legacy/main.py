# -*- coding: utf-8 -*-
import os
import random
from typing import Optional, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import data_store as ds
import engine as eg

app = FastAPI(title="FOOK API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

NUTRIENTS = ["energy", "protein", "potassium", "phosphorus", "sodium"]


# ---------------------------------------------------------------------------
# GET /health — 서버가 지금 DB(Neon)를 읽고 있는지 CSV 파일을 읽고 있는지 확인용
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "data_source": "postgresql" if ds.USING_DB else "csv",
        "menu_count": len(ds.ALL_MENUS),
        "ingredient_count": len(ds.INGREDIENT_POOL),
    }


# ---------------------------------------------------------------------------
# GET /menu-master, /diet-365 — 새 모바일 UI가 앱 시작 시 통째로 캐싱하는 데이터
# (기존 Supabase loadMenuMaster/loadDiet365를 대체)
# ---------------------------------------------------------------------------
@app.get("/menu-master")
def menu_master():
    """[[name, category, energy, protein, potassium, phosphorus, sodium], ...]"""
    return {"menu_master": ds.get_all_menu_master_rows()}


@app.get("/diet-365")
def diet_365():
    """[[morning[], lunch[], dinner[]], ...] (365일)"""
    return {"diet_365": ds.get_diet_365()}


# ---------------------------------------------------------------------------
# GET /recipe/{menu_name} — 재료+조리법 조회 (기존 getRecipeByName 대체)
# ---------------------------------------------------------------------------
@app.get("/recipe/{menu_name}")
def get_recipe(menu_name: str):
    ings = ds.MENU_INGREDIENTS.get(menu_name, [])
    steps_text = ds.MENU_RECIPE.get(menu_name, "")
    # 조리과정 텍스트(①②③...)를 줄 단위 배열로 분리
    steps = [s.strip() for s in steps_text.split("\n") if s.strip()] if steps_text else []
    return {
        "ingredients": [[i["name"], round(i["amount"])] for i in ings],
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# POST /substitute — 실제 재료 대체 알고리즘 실행 (SubstitutionPanel의 "재료 대체 알고리즘 실행" 버튼)
# 프론트의 runJudgementPipeline이 나트륨 절반 조정 + 단백질 비례 축소까지 마친 뒤에도
# 칼륨/인/나트륨이 초과 상태로 남으면 이 엔드포인트를 호출한다.
# ---------------------------------------------------------------------------
class SubstituteRequest(BaseModel):
    items: List[str]          # 이 끼니를 구성하는 메뉴명 목록
    over_keys: List[str]      # 초과된 영양소 키 (potassium/phosphorus/sodium 중 일부)


@app.post("/substitute")
def substitute(req: SubstituteRequest):
    valid_over_keys = [k for k in req.over_keys if k in eg.CAP_KEYS]
    if not valid_over_keys:
        return {"swap_log": [], "changes": [], "dish_ingredients": {}}

    meal = [m for m in req.items if m in ds.MENU_INGREDIENTS]
    swap_log, dish_ingredients = eg.apply_substitution(meal, valid_over_keys, max_swaps=4)

    changes = []
    for s in swap_log:
        keys_txt = ", ".join(eg.NUTRIENT_LABEL[k] for k in s["reason_keys"])
        changes.append(
            f"{s['dish']}: '{s['from']}' → '{s['to']}' 로 대체 ({keys_txt} 저감, {s['category']} 카테고리 내 대체)"
        )

    return {
        "swap_log": swap_log,
        "changes": changes,
        "dish_ingredients": dish_ingredients,
    }


# ---------------------------------------------------------------------------
# GET /menus, /ingredients  - 자동완성용 목록
# ---------------------------------------------------------------------------
@app.get("/menus")
def list_menus():
    return {"menus": ds.ALL_MENUS}


@app.get("/ingredients")
def list_ingredients():
    return {"ingredients": sorted(ds.INGREDIENT_POOL.keys())}


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    weight: float
    menu: Optional[str] = None
    ingredient: Optional[str] = None


@app.post("/generate")
def generate(req: GenerateRequest):
    rng = random.Random()
    targets = eg.get_targets(req.weight)

    # 1) 한 끼 조합 생성 (밥/국/메인/서브/김치, anchor 반영)
    meal, anchor = eg.generate_meal(anchor_menu=req.menu, anchor_ingredient=req.ingredient, rng=rng)
    if not meal:
        # 폴백: anchor 없이 재시도
        meal, anchor = eg.generate_meal(rng=rng)

    nutrition_before = eg.sum_nutrition(meal)

    # 2) 판정 -> 방향(초과/부족/정상) 계산
    directions = {k: eg.nutrient_direction(k, nutrition_before[k], targets[k]) for k in NUTRIENTS}
    # 재료 대체로 다룰 수 있는 것은 상한형 영양소(칼륨/인/나트륨)뿐이다.
    # 단백질/열량은 RANGE형이라 "낮추는 대체"가 결핍을 유발할 수 있으므로 대체 대상에서 제외한다.
    over_keys = [k for k in eg.CAP_KEYS if directions[k] == "over"]

    # 3) 초과 시 대체 시도
    swap_log = []
    dish_ingredients = {}
    nutrition_after = nutrition_before
    if over_keys:
        swap_log, dish_ingredients = eg.apply_substitution(meal, over_keys, anchor=anchor, max_swaps=4)
        if swap_log:
            nutrition_after = eg.recompute_nutrition_after_swap(meal, swap_log)
    if not dish_ingredients:
        # 대체가 없었어도 원본 재료 그대로 프론트에 제공
        for m in meal:
            ings = ds.MENU_INGREDIENTS.get(m, [])
            dish_ingredients[m] = [(i["name"], round(i["amount"])) for i in ings]

    final_directions = {k: eg.nutrient_direction(k, nutrition_after[k], targets[k]) for k in NUTRIENTS}
    passed = all(v == "ok" for v in final_directions.values())

    changes = []
    for s in swap_log:
        keys_txt = ", ".join(eg.NUTRIENT_LABEL[k] for k in s["reason_keys"])
        changes.append(
            f"{s['dish']}: '{s['from']}' → '{s['to']}' 로 대체 ({keys_txt} 저감, {s['category']} 카테고리 내 대체)"
        )

    warning = None
    under_keys = [k for k, d in final_directions.items() if d == "under"]
    if under_keys:
        labels = ", ".join(eg.NUTRIENT_LABEL[k] for k in under_keys)
        warning = f"{labels} 섭취량이 권장 하한보다 낮습니다. 반찬 양을 조금 늘려보세요."

    return {
        "meal": meal,
        "anchor": anchor,
        "nutrition": nutrition_after,
        "nutrition_before": nutrition_before,
        "targets": {
            k: (list(targets[k]) if isinstance(targets[k], tuple) else targets[k])
            for k in NUTRIENTS
        },
        "directions_before": directions,
        "directions_after": final_directions,
        "passed": passed,
        "swap_log": swap_log,
        "dish_ingredients": dish_ingredients,
        "changes": changes,
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# POST /recipe - 대체된 재료를 반영한 조리법 텍스트 재구성 (LLM 없이 규칙 기반 치환)
# ---------------------------------------------------------------------------
class RecipeRequest(BaseModel):
    menu: str
    ingredients: List[List]  # [[재료명, 양], ...] (대체 반영본)


@app.post("/recipe")
def recipe(req: RecipeRequest):
    base_recipe = ds.MENU_RECIPE.get(req.menu)
    if not base_recipe:
        return {"steps": None, "error": "해당 메뉴의 기본 조리법을 찾을 수 없습니다."}

    original_ings = ds.MENU_INGREDIENTS.get(req.menu, [])
    orig_names = {i["name"] for i in original_ings}
    new_names = {n for n, _ in req.ingredients}
    swapped_names = new_names - orig_names

    steps = base_recipe
    note = ""
    if swapped_names:
        note = (
            f"\n\n[투석 맞춤 안내] 아래 재료가 신장 부담을 낮추기 위해 대체되었습니다: "
            + ", ".join(sorted(swapped_names))
            + ". 조리 순서와 방법은 기존과 동일하게 진행하세요."
        )
    return {"steps": steps + note, "error": None}
