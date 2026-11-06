# -*- coding: utf-8 -*-
"""kiwi_ipp.py: 골드키위 '해금' 수분 도우미의 판정 엔진(Python 참조 구현)

학위논문(민성현, 전북대학교, 2027) 제2~4장의 식을 그대로 옮겼다.
- 일 기상 등급(제2장): 낮(08~19시) 강우 1 mm 이상 = 불량,
  최고기온 20°C 미만 또는 최대풍속 8 m/s 이상 = 경계,
  최고기온 25°C 미만 또는 최대풍속 6 m/s 이상 = 주의, 그 외 = 양호
- 만개일(제3장): chill-day 모형(Cesaraccio 등, 2004),
  모수 Tb 6.3°C, Rc 102.5, Rh 575(Kim 등, 2016a)
- IPP(제4장): IPP = P85(방법, 수분수 조건) x 기상 전달 성분
    벌 매개(BT, BTD): x min(1, E_win / E_v), E_v = 0.515
    인공수분(AP1, AP2): x min(1, 작업 가능일 / 3)
    BTD+AP: x (0.4 x 벌 성분 + 0.6 x 인공수분 성분)
  E_win = 만개 -4 ~ +9일의 등급별 유효 방화 평균
          (양호 1.00, 주의 0.59, 경계 0.38, 불량 0.31)
기상 자료: Open-Meteo 시간 예보·재분석(인증 키 불필요)
사용 예:
  python kiwi_ipp.py --lat 34.3959 --lon 126.7018 --year 2025 --place 완도
라이선스: MIT
웹 화면: https://karl7208.github.io/kiwi-pollination-dss1/advisor.html
"""
import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request

# 등급별 유효 방화(방화 빈도 x 체류 시간, 양호일 = 1)
E = {"Good": 1.00, "Caution": 0.59, "Alert": 0.38, "Poor": 0.31}
EV = 0.515  # 검증 하한: BTD 상품과 비율 75% 이상인 해의 최저 E_win(2020년)
P85 = {  # 수분 방법별 85 g 이상 과실 비율의 기대값(제4장 Table 4-6)
    "coinc": {"BT": 0.580, "BTD": 0.815, "AP1": 0.648,
              "AP2": 0.920, "BTD_AP": 0.900},  # 수분수 개화 일치
    "non": {"BT": 0.012, "BTD": 0.150, "AP1": 0.738,
            "AP2": None, "BTD_AP": None},      # 수분수 개화 불일치
}
TB, RC, RH = 6.3, 102.5, 575.0  # chill-day 모형 모수


def grade(rain, tmax, ws):
    """일 기상 등급: 예보 변수만 써서 위에서부터 판정한다."""
    if rain >= 1:
        return "Poor"
    if tmax < 20 or ws >= 8:
        return "Alert"
    if tmax < 25 or ws >= 6:
        return "Caution"
    return "Good"


def to_daily(h):
    """Open-Meteo 시간 자료를 일 자료로 바꾼다.
    과원 보정: 최고기온 -0.5°C, 최대풍속 = 1.34 x 일평균풍속 + 1.56"""
    by = {}
    rows = zip(h["time"], h["temperature_2m"],
               h["precipitation"], h["wind_speed_10m"])
    for t, temp, p, w in rows:
        d, hr = t[:10], int(t[11:13])
        o = by.setdefault(d, {"r": 0.0, "tx": -99.0, "ws": [], "n": 0})
        if w is not None:
            o["ws"].append(w)
        if 8 <= hr <= 19:
            if p is not None:
                o["r"] += p
            if temp is not None:
                o["tx"] = max(o["tx"], temp)
            o["n"] += 1
    out = {}
    for d, o in by.items():
        if o["n"] < 10 or not o["ws"]:
            continue
        tx = o["tx"] - 0.5
        wsx = 1.34 * sum(o["ws"]) / len(o["ws"]) + 1.56
        out[d] = dict(rain=round(o["r"], 1), tmax=round(tx, 1),
                      ws=round(wsx, 1), g=grade(o["r"], tx, wsx))
    return out


def chill(tx, tn):
    """하루의 저온 적산(Cd, 음수)과 고온 적산(Ca); 제3장 Table 3-1의 다섯 경우."""
    tm, rng = (tx + tn) / 2, max(tx - tn, 1e-6)
    a = (tx - TB) ** 2 / (2 * rng)
    b = tx * tx / (2 * rng)
    if tn >= TB:               # 경우 1: 하루 종일 Tb 이상
        return 0.0, tm - TB
    if tn >= 0 and tx > TB:    # 경우 2: Tb가 하루 기온 범위 안
        return -((tm - tn) - a), a
    if tn >= 0:                # 경우 3: 하루 종일 Tb 이하
        return -(tm - tn), 0.0
    if 0 < tx <= TB:           # 경우 4: 서리 밤, 낮도 Tb 이하
        return -b, 0.0
    if tx > TB:                # 경우 5: 서리 밤, 낮은 Tb 이상
        return -(b - a), a
    return 0.0, 0.0


def predict_bloom(days, year):
    """days: {'YYYY-MM-DD': (Tmax, Tmin)}.
    전년 10월 1일부터 Cd 누적이 -Rc에 이르면 휴면 해제,
    이후 Ca 누적이 Rh에 이르는 날을 만개일로 반환한다."""
    d, end = dt.date(year - 1, 10, 1), dt.date(year, 7, 31)
    sc = sa = 0.0
    rel = None
    while d <= end:
        v = days.get(d.isoformat())
        if v:
            cd, ca = chill(*v)
            if rel is None:
                sc += cd
                if sc <= -RC:
                    rel = d
            else:
                sa += ca
                if sa >= RH:
                    return rel, d
        d += dt.timedelta(days=1)
    return rel, None


def ipp(cond, ew, work_days):
    """IPP = 화분 공급 성분(P85) x 기상 전달 성분(식 4-1~4-3)."""
    fe = min(1.0, ew / EV)
    fa = min(1.0, work_days / 3)
    r = {}
    for k, v in P85[cond].items():
        if v is None:
            r[k] = None
        elif k in ("BT", "BTD"):
            r[k] = v * fe
        elif k in ("AP1", "AP2"):
            r[k] = v * fa
        else:
            r[k] = v * (0.4 * fe + 0.6 * fa)
    return r


def diagnose(daily, full_bloom, pollinizer="both"):
    """만개 -4 ~ +9일(14일)의 등급으로 E_win과 IPP를 구하고 3단계로 판정한다.
    pollinizer: both('옥천'+'해선') | haeseon('해선'만) | first(고접 첫해) | none"""
    known = []
    for i in range(-4, 10):
        d = full_bloom + dt.timedelta(days=i)
        if d.isoformat() in daily:
            known.append((d, i, daily[d.isoformat()]))
    if not known:
        raise ValueError("개화 기간의 기상 자료가 없습니다.")
    ew = sum(E[x["g"]] for _, _, x in known) / len(known)
    cnt = {g: sum(x["g"] == g for _, _, x in known) for g in E}
    work = [(d, i) for d, i, x in known
            if x["rain"] < 1 and x["ws"] < 8 and x["tmax"] >= 15]
    cond = "coinc" if pollinizer == "both" else "non"
    val = ipp(cond, ew, len(work))
    if pollinizer != "both":      # 1단계: 화분 공급
        step, verdict = 1, "인공수분을 기본으로 하세요(수분수 개화 불일치)"
    elif ew < EV:                 # 3단계: 기상 전달
        step, verdict = 3, "BTD에 인공수분을 더하세요"
    else:                         # 2단계: 방법
        step, verdict = 2, "BTD만으로 충분합니다"
    near = sorted(work, key=lambda x: abs(x[1] - 1))[:3]  # 만개 직후 우선
    return dict(
        full_bloom=full_bloom, n=len(known), E_win=round(ew, 3), grades=cnt,
        IPP={k: None if v is None else round(v, 3) for k, v in val.items()},
        step=step, verdict=verdict, ap_days=sorted(d for d, _ in near),
        rain_days=[d for d, _, x in known if x["g"] == "Poor"])


def narrative(R, place="과원"):
    """판정 결과를 농가용 문장으로 바꾼다."""
    g, I = R["grades"], R["IPP"]
    L = [f"{place}, '해금' 만개일 {R['full_bloom']:%m/%d} 기준 "
         f"만개 4일 전~9일 후 {R['n']}일을 진단했습니다.",
         f"등급: 양호 {g['Good']}일, 주의 {g['Caution']}일, "
         f"경계 {g['Alert']}일, 불량 {g['Poor']}일. "
         f"유효 방화 E_win = {R['E_win']:.2f} (검증 하한 {EV:.2f}).",
         f"판정(단계 {R['step']}): {R['verdict']}."]
    if I["BTD_AP"] is not None:
        L.append(f"상품과(85 g 이상) 기대율: BTD {I['BTD']:.0%}, "
                 f"BTD+AP {I['BTD_AP']:.0%}.")
    else:
        L.append(f"상품과(85 g 이상) 기대율: BTD {I['BTD']:.0%}, "
                 f"인공수분(AP1) {I['AP1']:.0%}.")
    if R["step"] != 2 and R["ap_days"]:
        days = ", ".join(f"{d:%m/%d}" for d in R["ap_days"])
        L.append(f"인공수분 권장일: {days} (비 없음, 8 m/s 미만, 15°C 이상).")
    if R["rain_days"]:
        days = ", ".join(f"{d:%m/%d}" for d in R["rain_days"])
        L.append(f"비 온 날({days})에는 부착기를 떼어 화분이 젖지 않게 하세요.")
    return "\n".join(L)


# ── Open-Meteo 자료 받기 ──
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"


def _get(url, **q):
    full = url + "?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(full, timeout=30) as r:
        return json.load(r)


def fetch_hourly(lat, lon, start=None, end=None):
    """start가 있으면 재분석(과거), 없으면 최근 14일 + 16일 예보."""
    q = dict(latitude=lat, longitude=lon, timezone="Asia/Seoul",
             hourly="temperature_2m,precipitation,wind_speed_10m",
             wind_speed_unit="ms")
    if start:
        return _get(ARCHIVE, start_date=start, end_date=end, **q)["hourly"]
    return _get(FORECAST, past_days=14, forecast_days=16, **q)["hourly"]


def fetch_tmax_tmin(lat, lon, start, end):
    j = _get(ARCHIVE, latitude=lat, longitude=lon, timezone="Asia/Seoul",
             daily="temperature_2m_max,temperature_2m_min",
             start_date=start, end_date=end)["daily"]
    rows = zip(j["time"], j["temperature_2m_max"], j["temperature_2m_min"])
    return {t: (a, b) for t, a, b in rows if a is not None and b is not None}


def main():
    ap = argparse.ArgumentParser(description="골드키위 '해금' 수분 도우미")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--year", type=int, default=dt.date.today().year)
    ap.add_argument("--pollinizer", default="both",
                    choices=["both", "haeseon", "first", "none"])
    ap.add_argument("--full-bloom", help="관측 만개일 YYYY-MM-DD(없으면 예측)")
    ap.add_argument("--place", default="과원")
    a = ap.parse_args()
    past = a.year < dt.date.today().year
    if a.full_bloom:
        fb = dt.date.fromisoformat(a.full_bloom)
    else:
        last = dt.date.today() - dt.timedelta(days=6)
        end = f"{a.year}-07-31" if past else last.isoformat()
        tt = fetch_tmax_tmin(a.lat, a.lon, f"{a.year - 1}-10-01", end)
        _, fb = predict_bloom(tt, a.year)
        if fb is None:
            raise SystemExit("기온 자료가 부족합니다. --full-bloom 을 입력하세요.")
    if past:
        s = (fb - dt.timedelta(days=4)).isoformat()
        e = (fb + dt.timedelta(days=9)).isoformat()
        hourly = fetch_hourly(a.lat, a.lon, s, e)
    else:
        hourly = fetch_hourly(a.lat, a.lon)
    R = diagnose(to_daily(hourly), fb, a.pollinizer)
    print(narrative(R, a.place))


if __name__ == "__main__":
    main()
