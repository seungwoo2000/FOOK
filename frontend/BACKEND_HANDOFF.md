# FOOK 프론트엔드 인수인계

투석 환자용 한끼 식단 생성 서비스. 백엔드는 FastAPI(`server_FOOK.py`), 프론트는 React+Vite.

---

## 1. 먼저 읽을 것

**API 명세서는 서버가 자동 생성합니다.** 서버가 켜져 있으면:

- `http://<서버주소>:8000/docs` — Swagger UI. 브라우저에서 바로 요청을 쏴볼 수 있음
- `http://<서버주소>:8000/openapi.json` — OpenAPI 스펙 원본 (타입 자동생성용)

이 문서는 Swagger에 안 나오는 것(필드의 의미, 함정)만 다룹니다.

---

## 2. 엔드포인트

| Method | 경로 | 용도 | 속도 |
|---|---|---|---|
| GET | `/health` | 서버 상태 확인 | 즉시 |
| GET | `/menus` | 메뉴명 전체 목록 (자동완성용) | 즉시 |
| GET | `/ingredients` | 재료명 전체 목록 (자동완성용) | 즉시 |
| POST | `/generate` | **한 끼 생성 (핵심 기능)** | 느림 ⚠️ |
| POST | `/generate_day` | 하루 3끼 생성 | 매우 느림 ⚠️ |
| POST | `/recipe` | 조리법 LLM 편집 | 느림 (LLM) |

### POST /generate

```jsonc
// 요청 — 전부 선택사항
{
  "menu": "제육고추장불고기",  // 메뉴 지정 (있으면 이 메뉴가 반드시 포함됨)
  "ingredient": "고등어",      // 재료 지정 (이 재료를 쓰는 메뉴가 선택됨)
  "weight": 60,                // 환자 체중(kg). 영양 목표치가 체중에 따라 달라짐
  "consumed": null,            // 오늘 이미 먹은 누적 영양 (아래 5번 참고)
  "meals_left": 3              // 이번 끼 포함 남은 끼니 수 (아침3 / 점심2 / 저녁1)
}
```

`menu`와 `ingredient` 둘 다 비우면 랜덤 생성입니다. 응답의 `mode` 필드로 어느 쪽이었는지 알 수 있습니다.

### POST /generate_day

```jsonc
{
  "weight": 60,
  "menus": ["제육고추장불고기", null, null],  // 끼니별 지정 (아침/점심/저녁), null이면 랜덤
  "ingredients": [null, "고등어", null]
}
```

**`consumed` 없이 `/generate`를 3번 부르는 것과 결과가 다릅니다.** 앞 끼에서 먹은 양을 빼고 남은 끼니 수로 나눠 다음 끼 목표를 잡기 때문입니다(남은 예산 방식). 같은 효과를 `/generate` + `consumed`로도 낼 수 있습니다 — 5번 참고.

### POST /recipe

`/generate` 응답에서 받은 값을 그대로 넘깁니다.

```jsonc
{
  "menu": "제육고추장불고기",              // dish_ingredients의 key
  "ingredients": [["돼지고기,앞다리", 80]], // dish_ingredients[menu] 그대로
  "source": "오징어볶음"                    // recipe_source[menu]가 있으면 넣고, 없으면 생략
}
```

---

## 3. 응답 필드 (⚠️ 여기가 중요)

`/generate` 응답 예시는 `samples/POST_generate__menu.json` 참고.

| 필드 | 설명 |
|---|---|
| `meal` | 최종 메뉴명 배열. **화면에 보여줄 식단** |
| `nutrition` | 이 한끼의 영양소 실제값 |
| `targets` | 영양소 목표치 |
| `passed` | 5대 영양소 전부 충족했는지 (true/false) |
| `note` | 사용자 안내문. 비어있을 수 있음 |
| `warning` | 경고문. 비어있을 수 있음 |
| `changes` | 시스템이 원본 대비 바꾼 내역 (사람이 읽는 문장 배열, 최대 10개) |
| `dish_ingredients` | `{메뉴명: [[재료명, 그램], ...]}`. `/recipe` 호출에 그대로 사용 |
| `snacks` | 간식 메뉴명 배열 |
| `recipe_source` | `{표시명: 원본명}`. `/recipe`의 `source`에 사용 |
| `anchor` | 생성의 기준이 된 메뉴 (디버그용) |
| `mode` | `"menu"` / `"ingredient"` / `"random"` |
| `intake` | 이 끼의 실제 섭취량. **다음 끼 요청 때 되돌려 보내는 값** (아래 5번 참고) |

### 함정 1 — 나트륨이 두 개입니다

```jsonc
"nutrition": {
  "sodium": 345,        // 조미료(첨가염)만. ← 합격/불합격 판정 대상. 화면에 이걸 쓰세요
  "sodium_total": 545   // 자연재료 포함 총량. 참고용
}
```

`targets.sodium`과 비교해야 하는 값은 `sodium`입니다. `sodium_total`을 비교하면 멀쩡한 식단이 전부 불합격으로 표시됩니다.

### 함정 2 — targets는 타입이 섞여 있습니다

```jsonc
"targets": {
  "energy":     [600, 700],   // 배열 = 하한~상한 (범위 안에 들어야 통과)
  "protein":    [22.0, 24.0], // 배열 = 하한~상한
  "potassium":  1000,         // 숫자 = 상한만 (이하여야 통과)
  "phosphorus": 333,          // 숫자 = 상한만
  "sodium":     393           // 숫자 = 상한만
}
```

열량·단백질은 **모자라도 불합격**이고, 칼륨·인·나트륨은 **넘으면 불합격**입니다. 판정 로직은 `FOOK_app/src/App.jsx`의 `NutrientRow`에 이미 구현되어 있으니 참고하세요.

### /generate_day 응답

`samples/POST_generate_day.json` 참고. 구조는 다릅니다:

```jsonc
{
  "meals": [ /* /generate 응답과 똑같은 객체 3개 (아침/점심/저녁) */ ],
  "day_nutrition": { "energy": 1939, "protein": 68.6, "potassium": 2270,
                     "phosphorus": 878, "sodium": 1142, "sodium_total": 1617 },
  "day_targets":   { "energy": [1800, 2100], "protein": [66.0, 72.0],
                     "potassium": 3000, "phosphorus": 1000, "sodium": 1179 },
  "day_passed": true
}
```

`meals[i]`는 `/generate` 응답과 동일한 스키마라 한끼 카드 컴포넌트를 그대로 재사용할 수 있습니다. `day_nutrition`/`day_targets`도 위 함정 1·2가 똑같이 적용됩니다.

### 함정 3 — 간식은 조리법이 없습니다

`snacks`에 들어있는 메뉴는 `dish_ingredients`에 없고, `/recipe`를 호출하면 안 됩니다(시판 빵·떡이라 조리법이 무의미). 화면에서 "조리법 보기" 버튼을 숨기세요.

---

## 4. 서버 실행 방법

```bash
conda activate foodbert
set TF_USE_LEGACY_KERAS=1
cd /d E:\final
python -m uvicorn server_FOOK:app --host 0.0.0.0 --port 8000
```

- `--host 0.0.0.0`이어야 다른 PC에서 접속됩니다 (`127.0.0.1`이면 서버 PC에서만 접속 가능)
- CORS는 모든 origin에 열려 있어 프론트에서 추가 설정 불필요
- **첫 실행 시 TF 모델 로딩에 수십 초** 걸립니다. 그동안 요청이 안 받아집니다
- `/recipe`는 `OPENAI_API_KEY` 환경변수가 있어야 동작합니다. 없으면 응답에 `error` 필드가 담겨 옵니다

---

## 5. 하루를 이어서 만들기 (intake / consumed)

하루 식단을 만드는 방법이 **두 가지**입니다. 화면 설계에 따라 고르세요.

### 방법 A — `/generate_day` 한 방에

3끼를 한 번에 받습니다. "하루 식단표를 보여준다"는 화면에 적합. 대신 **매우 느립니다**(생성 3회).

### 방법 B — `/generate`를 3번, `intake`를 이어붙이기 ← 실사용에 가까움

"아침 먼저 받고, 먹고 나서 점심 요청" 같은 실제 사용 흐름에 맞습니다.

```js
// 1끼: 아침
const b = await post('/generate', { weight: 60, meals_left: 3 })

// 응답의 intake를 저장 (키가 E/protein/K/P/Na/Na_season — nutrition과 키 이름이 다름!)
let consumed = { ...b.intake }

// 2끼: 점심 — 누적을 넘기고 남은 끼니 수를 줄임
const l = await post('/generate', { weight: 60, consumed, meals_left: 2 })
for (const k in consumed) consumed[k] += l.intake[k]

// 3끼: 저녁
const d = await post('/generate', { weight: 60, consumed, meals_left: 1 })
```

이렇게 하면 **앞 끼에서 남긴 예산이 다음 끼 목표에 반영됩니다.** 실제 샘플에서 아침이 칼륨을 614mg만 썼더니 점심 상한이 1000 → 1193mg로 늘어났습니다. (`samples/POST_generate__meal1_breakfast.json`, `POST_generate__meal2_lunch_with_consumed.json` 비교)

⚠️ **`consumed`를 안 넘기면 매 끼가 "오늘 첫 끼"로 계산됩니다.** 3끼를 따로 요청하면 하루 총량이 목표를 초과할 수 있습니다.

⚠️ **`intake`와 `nutrition`은 키 이름이 다릅니다.** 화면 표시는 `nutrition`(`energy`/`potassium`/…), 서버로 되돌려 보낼 때는 `intake`(`E`/`K`/…)를 **가공하지 말고 그대로** 쓰세요.

키를 잘못 보내면 서버가 **422로 거절**하고 무엇이 잘못됐는지 알려줍니다. 조용히 0으로 처리되지 않으니, 이 에러가 뜨면 메시지대로 고치면 됩니다:

```jsonc
// nutrition을 잘못 보냈을 때
{
  "detail": "consumed에 ['E', 'K', 'P', 'Na', 'Na_season'] 키가 없습니다. 표시용 'nutrition'이 아니라 응답의 'intake'를 그대로 보내세요. 필요한 키: ['E', 'protein', 'K', 'P', 'Na', 'Na_season']"
}
```

---

## 6. 프론트에서 반드시 처리할 것

**로딩 UI가 필수입니다.** `/generate`는 조건을 만족하는 조합을 최대 48번 다시 뽑기 때문에 응답이 느립니다. `/generate_day`는 그걸 3번 합니다. 스피너 없이 만들면 앱이 멈춘 것처럼 보입니다.

- fetch에 timeout을 짧게 걸지 마세요
- 생성 버튼은 요청 중 disable 처리
- `/generate_day`는 진행 표시를 별도로 고려하세요

---

## 7. 파일

- `samples/` — 실제 API 응답 샘플 JSON. 백엔드 없이 화면 잡을 때 사용
  - `POST_generate__menu` / `__ingredient` / `__random` — 한 끼 생성 3가지 모드
  - `POST_generate__meal1_breakfast` + `__meal2_lunch_with_consumed` — `consumed` 이어붙이기 (5번)
  - `POST_generate_day` — 하루 3끼 한 번에
  - `GET_menus` / `GET_ingredients` / `GET_health`
- `FOOK_app/` — 기존 React+Vite 프로젝트. 위 API 호출이 이미 구현되어 있음
  - `src/App.jsx` — 메인 화면, API 호출, 영양소 판정 로직
  - `src/App.css` — 스타일
  - API 주소는 `App.jsx` 상단 `const API = '...'` 한 줄
  - `npm install` 후 `npm run dev`
