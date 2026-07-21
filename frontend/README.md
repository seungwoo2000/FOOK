# FOOK v5 데이터 연동 프로토타입

## 실행
```powershell
npm install
npm run dev
```

## 반영 데이터
- FOOK_menu_master.xlsx: 824개 메뉴의 재료, 조리과정, 영양정보
- FOOK_diet_1_12_kor.csv: 365일 × 아침·점심·저녁 식단 조합
- FOOK_ingredients_kor.csv: 497개 식재료 영양정보

## 앱 흐름
온보딩 → 체험/프로필 → 음식·재료 검색 → 실제 식단 선택 → 식단 생성 → 영양 분석 → 식단 조정 → 조정 결과 → 최종 식단 → 레시피/PDF

식단 조정 값은 현재 알고리즘 연동 전의 시연용 규칙입니다. 원본 영양정보와 레시피/재료는 업로드 데이터에서 읽습니다.
