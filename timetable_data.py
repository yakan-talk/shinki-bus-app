# -*- coding: utf-8 -*-
"""
神姫バス 公式時刻表データ (2026年11月14日改正基準)
対象区間:
  1. 県立大工学部前 (神姫バス停留所名:「県立大工学部」tcode=20240, pcode=2)
     → 姫路駅（北口）(tcode=20000)
  2. 姫路駅（北口）(18番のりば tcode=20000, pcode=18)
     → 県立大工学部前 (「県立大工学部」tcode=20240)
"""

from typing import Dict, List, Any

BUS_STOPS_META: Dict[str, Dict[str, Any]] = {
    "kenritsudai_kogakubu": {
        "display_name": "県立大工学部前",
        "official_name": "県立大工学部",
        "tcode": "20240",
        "pcode": "2",
        "timetable_url": "https://navi.shinkibus.jp/jikoku/timetable?tcode=20240&pcode=2",
    },
    "himeji_station": {
        "display_name": "姫路駅（北口）",
        "official_name": "姫路駅（北口）",
        "tcode": "20000",
        "pcode": "18",
        "timetable_url": "https://navi.shinkibus.jp/jikoku/timetable?tcode=20000&pcode=18",
    },
}

# 往路（県立大工学部前 → 姫路駅北口）の走行停留所プロファイル（神姫バスNavi 41/42/43/45系統準拠）
# offset_min は「県立大工学部」発車時刻を 0 とした相対分数
ROUTE_STOPS_TO_STATION: List[Dict[str, Any]] = [
    {"name": "緑台 / 山崎 / バーズタウン（始発）", "offset_min": -10, "zone": "upstream"},
    {"name": "打越", "offset_min": -6, "zone": "upstream"},
    {"name": "六角", "offset_min": -5, "zone": "upstream"},
    {"name": "床坂菅生台", "offset_min": -3, "zone": "upstream"},
    {"name": "書写台１丁目", "offset_min": -1, "zone": "upstream"},
    {"name": "県立大工学部", "offset_min": 0, "zone": "boarding", "tcode": "20240"},
    {"name": "西坂・西坂口", "offset_min": 1, "zone": "enroute"},
    {"name": "東洋大学姫路高校", "offset_min": 2, "zone": "enroute"},
    {"name": "書写東坂・書写郵便局前", "offset_min": 4, "zone": "enroute"},
    {"name": "横関", "offset_min": 5, "zone": "enroute"},
    {"name": "御立（北口・御立・南口）", "offset_min": 6, "zone": "enroute"},
    {"name": "四軒屋・田寺", "offset_min": 8, "zone": "enroute"},
    {"name": "田寺南口・辻井", "offset_min": 11, "zone": "enroute"},
    {"name": "名古山北口・東辻井", "offset_min": 13, "zone": "enroute"},
    {"name": "岩端（北口・岩端・南口）", "offset_min": 16, "zone": "enroute"},
    {"name": "龍野町・船場元町", "offset_min": 19, "zone": "enroute"},
    {"name": "白鷺橋", "offset_min": 22, "zone": "enroute", "tcode": "20032"},
    {"name": "大手前通り", "offset_min": 24, "zone": "enroute", "tcode": "20001"},
    {"name": "姫路駅（北口）", "offset_min": 30, "zone": "terminal", "tcode": "20000"},
]

# 復路（姫路駅北口 18番のりば → 県立大工学部前）の走行停留所プロファイル（神姫バスNavi 41/42/43/45系統準拠）
ROUTE_STOPS_TO_UNIV: List[Dict[str, Any]] = [
    {"name": "姫路駅（北口 18番のりば）", "offset_min": 0, "zone": "boarding", "tcode": "20000"},
    {"name": "大手前通り", "offset_min": 2, "zone": "enroute", "tcode": "20001"},
    {"name": "姫路城大手門前（西方面）", "offset_min": 3, "zone": "enroute", "tcode": "20157"},
    {"name": "好古園前・市之橋・文学館前", "offset_min": 5, "zone": "enroute"},
    {"name": "岡町・岩端北口", "offset_min": 8, "zone": "enroute"},
    {"name": "東辻井・名古山北口", "offset_min": 10, "zone": "enroute"},
    {"name": "辻井（南口・辻井）", "offset_min": 12, "zone": "enroute"},
    {"name": "田寺（南口・田寺）", "offset_min": 14, "zone": "enroute"},
    {"name": "四軒屋・御立", "offset_min": 18, "zone": "enroute"},
    {"name": "横関", "offset_min": 20, "zone": "enroute"},
    {"name": "書写郵便局前・書写東坂", "offset_min": 22, "zone": "enroute"},
    {"name": "東洋大学姫路高校", "offset_min": 23, "zone": "enroute"},
    {"name": "西坂口・西坂", "offset_min": 25, "zone": "enroute"},
    {"name": "県立大工学部", "offset_min": 26, "zone": "arrival", "tcode": "20240"},
]


def _expand_to_station_entries(raw_hours: Dict[int, List[str]]) -> List[Dict[str, Any]]:
    """
    県立大工学部 (20240-2) → 姫路駅（北口）(20000) の時刻表定義を展開する
    """
    results: List[Dict[str, Any]] = []
    for hour in sorted(raw_hours.keys()):
        for token in raw_hours[hour]:
            prefix = "".join(c for c in token if not c.isdigit())
            minute = int("".join(c for c in token if c.isdigit()))
            time_str = f"{hour:02d}:{minute:02d}"

            if "直" in prefix:
                route_no = "直行"
                origin = "県立大工学部始発"
                ride_min = 22
            elif "姫" in prefix:
                route_no = "7"
                origin = "県立大工学部始発"
                ride_min = 28
            elif "緑" in prefix:
                route_no = "43"
                origin = "緑台発"
                ride_min = 27
            elif "バ" in prefix:
                route_no = "41"
                origin = "バーズタウン・荒木発"
                ride_min = 27
            elif "山" in prefix:
                route_no = "42"
                origin = "山崎発"
                ride_min = 27
            else:
                route_no = "45"
                origin = "書写西住宅発"
                ride_min = 27

            note = "休講日運休" if "▲" in prefix else ""
            arr_total = hour * 60 + minute + ride_min
            arr_h = (arr_total // 60) % 24
            arr_m = arr_total % 60

            results.append({
                "time": time_str,
                "arrival_time": f"{arr_h:02d}:{arr_m:02d}",
                "route_no": route_no,
                "destination": "姫路駅（北口）",
                "origin": origin,
                "fare": 420,
                "ride_minutes": ride_min,
                "note": note,
            })
    return results


# 県立大工学部 (20240, pcode=2) → 姫路駅(北口) 平日
TO_STATION_WEEKDAY_RAW: Dict[int, List[str]] = {
    6: ["38", "山50"],
    7: ["11", "21", "山31", "41", "山46", "51"],
    8: ["緑01", "06", "10", "山14", "バ18", "22", "緑26", "山37", "47"],
    9: ["03", "12", "山19", "31", "41", "54"],
    10: ["バ02", "05", "15", "緑30", "40", "バ50"],
    11: ["05", "緑10", "20", "35", "50"],
    12: ["バ00", "10", "緑20", "35", "バ50"],
    13: ["05", "直▲15", "緑20", "25", "35", "バ50"],
    14: ["姫00", "05", "緑20", "35", "山50"],
    15: ["05", "緑20", "直▲33", "35", "45", "バ50"],
    16: ["05", "緑20", "35", "55"],
    17: ["05", "10", "緑14", "直▲18", "25", "バ31", "40", "山52"],
    18: ["姫00", "緑12", "24", "36", "45", "バ54", "55", "58"],
    19: ["山01", "05", "10", "緑20", "32", "44", "姫57"],
    20: ["山11", "25", "45"],
    21: ["10", "緑20", "40"],
    22: ["10", "緑20", "40"],
    23: ["05", "30", "44"],
}

# 県立大工学部 (20240, pcode=2) → 姫路駅(北口) 土日祝
TO_STATION_WEEKEND_RAW: Dict[int, List[str]] = {
    7: ["山01", "16", "山31", "緑55"],
    8: ["05", "バ15", "25", "山35", "45", "55"],
    9: ["山05", "15", "25", "40"],
    10: ["00", "バ15", "30", "緑45"],
    11: ["05", "25", "緑45"],
    12: ["05", "バ15", "緑25", "35", "バ50"],
    13: ["05", "緑20", "35", "バ50"],
    14: ["05", "緑20", "35", "山50"],
    15: ["05", "緑20", "35", "バ50"],
    16: ["05", "緑20", "35", "バ50"],
    17: ["05", "緑20", "35", "山50"],
    18: ["05", "緑20", "35", "バ50"],
    19: ["05", "緑20", "35", "バ55"],
    20: ["16", "42"],
    21: ["07", "緑18", "35"],
    22: ["06", "49"],
}


def _expand_from_station_entries(
    otemon_raw: Dict[int, List[str]], direct_express: List[str]
) -> List[Dict[str, Any]]:
    """
    姫路駅（北口 18番のりば 20000-18）→ 県立大工学部方面の時刻表を生成する
    （姫路駅北口18番のりば発車時刻は姫路城大手門前の3分前＋平日直行便）
    """
    entries: List[Dict[str, Any]] = []

    for hour in sorted(otemon_raw.keys()):
        for item in otemon_raw[hour]:
            route_part, min_part = item.split(":")
            prefix = "".join(c for c in min_part if not c.isdigit())
            otemon_min = int("".join(c for c in min_part if c.isdigit()))

            # 姫路駅（北口）発は 3分前
            sta_total = hour * 60 + otemon_min - 3
            sta_h = sta_total // 60
            sta_m = sta_total % 60
            time_str = f"{sta_h:02d}:{sta_m:02d}"
            ride_min = 26

            if route_part == "45":
                route_no = "45"
                if "工" in prefix:
                    dest = "県立大工学部"
                elif "横" in prefix:
                    dest = "横関（県立大工学部経由）"
                else:
                    dest = "書写西住宅（県立大工学部経由）"
            elif route_part == "43":
                route_no = "43"
                dest = "緑台（県立大工学部経由）"
            else:
                if "山" in prefix or "◆" in prefix:
                    route_no = "42"
                    dest = "山崎（県立大工学部経由）"
                elif "古" in prefix:
                    route_no = "41"
                    dest = "古瀬畑（県立大工学部経由）"
                elif "荒" in prefix:
                    route_no = "41"
                    dest = "荒木（県立大工学部経由）"
                else:
                    route_no = "41"
                    dest = "バーズタウン（県立大工学部経由）"

            arr_total = sta_total + ride_min
            arr_h = (arr_total // 60) % 24
            arr_m = arr_total % 60

            entries.append({
                "_sort_key": sta_total,
                "time": time_str,
                "arrival_time": f"{arr_h:02d}:{arr_m:02d}",
                "route_no": route_no,
                "destination": dest,
                "origin": "姫路駅（北口 18番のりば）始発",
                "fare": 420,
                "ride_minutes": ride_min,
                "note": "",
            })

    for exp_time in direct_express:
        hh, mm = map(int, exp_time.split(":"))
        sta_total = hh * 60 + mm
        ride_min = 22
        arr_total = sta_total + ride_min
        entries.append({
            "_sort_key": sta_total,
            "time": f"{hh:02d}:{mm:02d}",
            "arrival_time": f"{(arr_total // 60) % 24:02d}:{arr_total % 60:02d}",
            "route_no": "直行",
            "destination": "県立大工学部（直行）",
            "origin": "姫路駅（北口 18番のりば）始発",
            "fare": 420,
            "ride_minutes": ride_min,
            "note": "休講日運休",
        })

    entries.sort(key=lambda x: x["_sort_key"])
    for e in entries:
        e.pop("_sort_key", None)
    return entries


# 姫路城大手門前基準（姫路駅北口は -3分）
_OTEMON_TO_UNIV_WEEKDAY: Dict[int, List[str]] = {
    7: ["45:工38", "45:48"],
    8: ["45:03", "45:18", "45:工33", "41:古48", "45:58"],
    9: ["43:08", "45:13", "45:23", "45:28", "43:33", "41:荒43", "45:58"],
    10: ["43:13", "45:28", "41:バ43", "45:58"],
    11: ["45:03", "43:13", "45:28", "41:荒43", "45:58"],
    12: ["43:13", "45:28", "41:荒43", "45:58"],
    13: ["43:13", "41:荒18", "45:28", "42:山43", "45:58"],
    14: ["43:13", "45:28", "41:荒43", "45:58"],
    15: ["43:13", "45:28", "42:山43", "45:58"],
    16: ["43:13", "45:28", "45:工43", "42:山48", "45:58"],
    17: ["43:13", "45:33", "41:荒48", "45:58"],
    18: ["43:13", "45:工28", "45:43", "42:◆48", "45:58"],
    19: ["43:18", "45:28", "41:バ48", "45:58"],
    20: ["43:18", "45:28", "42:山48", "45:58"],
    21: ["43:18", "45:33", "42:山48", "45:58"],
    22: ["43:18", "45:33", "41:荒48", "45:58"],
    23: ["45:工18", "42:山33", "45:48"],
    24: ["45:工03", "45:工18"],
}

_DIRECT_EXPRESS_WEEKDAY: List[str] = [
    "10:05", "10:10", "10:15", "10:20", "10:25", "10:30",
    "11:50", "12:00", "12:05", "13:45", "14:25", "17:40",
]

_OTEMON_TO_UNIV_WEEKEND: Dict[int, List[str]] = {
    8: ["45:08", "45:18", "43:28", "45:38", "45:48"],
    9: ["45:13", "43:23", "43:33", "45:53"],
    10: ["43:13", "45:28", "45:48", "41:バ58"],
    11: ["43:13", "45:28", "41:荒43", "45:58"],
    12: ["43:13", "45:28", "41:荒43", "45:58"],
    13: ["43:13", "45:28", "42:山43", "45:58"],
    14: ["43:13", "45:28", "41:荒43", "45:58"],
    15: ["43:13", "45:28", "42:山43", "45:58"],
    16: ["43:13", "45:28", "42:山43", "45:58"],
    17: ["43:13", "45:28", "41:荒43", "45:58"],
    18: ["43:18", "45:28", "41:荒48", "45:58"],
    19: ["43:18", "45:33", "41:バ48"],
    20: ["45:03", "43:18", "45:33", "42:山48"],
    21: ["45:03", "43:18", "45:33", "42:山48"],
    22: ["45:18", "43:33", "45:48"],
    23: ["45:工18", "42:山38", "45:横58"],
}

TIMETABLE_DB: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "to_station": {
        "weekday": _expand_to_station_entries(TO_STATION_WEEKDAY_RAW),
        "weekend": _expand_to_station_entries(TO_STATION_WEEKEND_RAW),
    },
    "to_univ": {
        "weekday": _expand_from_station_entries(_OTEMON_TO_UNIV_WEEKDAY, _DIRECT_EXPRESS_WEEKDAY),
        "weekend": _expand_from_station_entries(_OTEMON_TO_UNIV_WEEKEND, []),
    },
}
