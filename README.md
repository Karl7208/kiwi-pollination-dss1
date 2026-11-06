# kiwi-pollination-dss1
Weather-driven pollination decision support for gold kiwifruit 'Haegeum'.

- `docs/advisor.html` — **수분 도우미 (2026 개정 IPP)**: 실시간 예보(Open-Meteo) 또는 지난 해 재분석 기상으로 만개 전후 14일의 일 기상 등급, 유효 방화(E_win), 검증 하한(0.52) 대비 판정, 수분 방법별 상품과(≥85 g) 기대율(IPP)을 계산하고 3단계 판단(수분수 → BTD 기본 → 기상에 따른 인공수분 병행)과 실행 문장을 제시합니다. 선택적으로 Claude API 키를 넣으면 계산 결과를 바탕으로 질문에 답합니다(판정은 바꾸지 않음).
- `docs/index.html`, `docs/national.html` — 연도별 아카이브 (1차 IPP, 종자 수 기준; 학위논문 2차 심사본의 IPP와 정의가 다름).

판정 규칙의 근거: 학위논문(전북대학교, 2026) 제2장(일 기상 등급, 등급별 방화 빈도·체류 시간)과 제4장(IPP, 검증 하한).

## Python 참조 구현 (`python/kiwi_ipp.py`)

학위논문 제2~4장의 판정 식(일 기상 등급, chill-day 만개일 예측, 개화 기간 유효 방화 E_win, IPP와 3단계 판정)을 표준 라이브러리만으로 구현한 코드입니다. 웹 화면(`docs/advisor.html`)과 같은 식을 씁니다.

```bash
python python/kiwi_ipp.py --lat 34.3959 --lon 126.7018 --year 2025 --place 완도
```
