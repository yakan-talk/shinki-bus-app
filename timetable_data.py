# -*- coding: utf-8 -*-
"""
神姫バス 公式時刻表データ (https://navi.shinkibus.jp/jikoku/timetable 準拠)
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

# 往路（県立大工学部 → 姫路駅(北口)）25停留所（神姫バスNavi 41/42/43/45系統 実停留所順）
INBOUND_TO_STATION_STOPS: List[Dict[str, Any]] = [
    {"name": "県立大工学部", "offset_min": 0},
    {"name": "西坂", "offset_min": 1},
    {"name": "西坂口", "offset_min": 1},
    {"name": "東洋大姫路高校", "offset_min": 2},
    {"name": "書写東坂", "offset_min": 3},
    {"name": "書写郵便局前", "offset_min": 4},
    {"name": "横関", "offset_min": 5},
    {"name": "御立北口", "offset_min": 6},
    {"name": "御立", "offset_min": 6},
    {"name": "御立南口", "offset_min": 7},
    {"name": "四軒屋", "offset_min": 8},
    {"name": "田寺", "offset_min": 9},
    {"name": "田寺南口", "offset_min": 10},
    {"name": "辻井", "offset_min": 11},
    {"name": "辻井南口", "offset_min": 12},
    {"name": "名古山北口", "offset_min": 13},
    {"name": "東辻井", "offset_min": 14},
    {"name": "岩端北口", "offset_min": 16},
    {"name": "岩端", "offset_min": 17},
    {"name": "岩端南口", "offset_min": 18},
    {"name": "龍野町", "offset_min": 19},
    {"name": "船場元町", "offset_min": 21},
    {"name": "白鷺橋", "offset_min": 22},
    {"name": "大手前通り", "offset_min": 24},
    {"name": "姫路駅(北口)", "offset_min": 27},
]

# 復路（姫路駅(北口) 18番のりば → 県立大工学部）24停留所（神姫バスNavi 41/42/43/45系統 実停留所順）
OUTBOUND_TO_UNIV_STOPS: List[Dict[str, Any]] = [
    {"name": "姫路駅(北口)", "offset_min": 0},
    {"name": "大手前通り", "offset_min": 2},
    {"name": "姫路城大手門前", "offset_min": 3},
    {"name": "好古園前", "offset_min": 4},
    {"name": "市之橋・文学館前", "offset_min": 5},
    {"name": "岡町", "offset_min": 7},
    {"name": "岩端北口", "offset_min": 8},
    {"name": "東辻井", "offset_min": 9},
    {"name": "名古山北口", "offset_min": 10},
    {"name": "辻井南口", "offset_min": 11},
    {"name": "辻井", "offset_min": 12},
    {"name": "田寺南口", "offset_min": 13},
    {"name": "田寺", "offset_min": 14},
    {"name": "四軒屋", "offset_min": 16},
    {"name": "御立南口", "offset_min": 17},
    {"name": "御立", "offset_min": 18},
    {"name": "御立北口", "offset_min": 19},
    {"name": "横関", "offset_min": 20},
    {"name": "書写郵便局前", "offset_min": 21},
    {"name": "書写東坂", "offset_min": 22},
    {"name": "東洋大姫路高校", "offset_min": 23},
    {"name": "西坂口", "offset_min": 24},
    {"name": "西坂", "offset_min": 25},
    {"name": "県立大工学部", "offset_min": 26},
]

ROUTE_STOPS_TO_STATION = INBOUND_TO_STATION_STOPS
ROUTE_STOPS_TO_UNIV = OUTBOUND_TO_UNIV_STOPS


def expand_to_station_entries(raw_hours: Dict[int, List[str]]) -> List[Dict[str, Any]]:
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


# 県立大工学部 (20240, pcode=2) → 姫路駅(北口) 公式平日ダイヤ
TO_STATION_WEEKDAY_RAW: Dict[int, List[str]] = {
    5: ["38", "山50"],
    6: ["11", "21", "山31", "41", "山46", "51"],
    7: ["緑01", "06", "10", "山14", "バ18", "22", "緑26", "山37", "47"],
    8: ["03", "12", "山19", "31", "41", "54"],
    9: ["バ02", "05", "15", "緑30", "40", "バ50"],
    10: ["05", "緑10", "20", "35", "50"],
    11: ["バ00", "10", "緑20", "35", "バ50"],
    12: ["05", "直▲15", "緑20", "25", "35", "バ50"],
    13: ["姫00", "05", "緑20", "35", "山50"],
    14: ["05", "緑20", "直▲33", "35", "45", "バ50"],
    15: ["05", "緑20", "35", "55"],
    16: ["05", "10", "緑14", "直▲18", "25", "バ31", "40", "山52"],
    17: ["姫00", "緑12", "24", "36", "45", "バ54", "55", "58"],
    18: ["山01", "05", "10", "緑20", "32", "44", "姫57"],
    19: ["山11", "25", "45"],
    20: ["10", "緑20", "40"],
    21: ["10", "緑20", "40"],
    22: ["05", "30", "44"],
}

# 県立大工学部 (20240, pcode=2) → 姫路駅(北口) 公式土日祝ダイヤ
TO_STATION_WEEKEND_RAW: Dict[int, List[str]] = {
    6: ["山01", "16", "山31", "緑55"],
    7: ["05", "バ15", "25", "山35", "45", "55"],
    8: ["山05", "15", "25", "40"],
    9: ["00", "バ15", "30", "緑45"],
    10: ["05", "25", "緑45"],
    11: ["05", "バ15", "緑25", "35", "バ50"],
    12: ["05", "緑20", "35", "バ50"],
    13: ["05", "緑20", "35", "山50"],
    14: ["05", "緑20", "35", "バ50"],
    15: ["05", "緑20", "35", "バ50"],
    16: ["05", "緑20", "35", "山50"],
    17: ["05", "緑20", "35", "バ50"],
    18: ["05", "緑20", "35", "バ55"],
    19: ["16", "42"],
    20: ["07", "緑18", "35"],
    21: ["06", "49"],
}


def expand_from_station_entries(
    by_route_hours: Dict[str, Dict[int, List[str]]]
) -> List[Dict[str, Any]]:
    """
    姫路駅（北口 18番のりば 20000-18）→ 県立大工学部方面の公式時刻表を展開する
    """
    entries: List[Dict[str, Any]] = []
    for route_key, hours_dict in by_route_hours.items():
        for hour, tokens in hours_dict.items():
            for token in tokens:
                prefix = "".join(c for c in token if not c.isdigit())
                minute = int("".join(c for c in token if c.isdigit()))
                sta_total = hour * 60 + minute
                time_str = f"{hour:02d}:{minute:02d}"

                if route_key == "直行":
                    route_no = "直行"
                    dest = "県立大工学部（直行）"
                    ride_min = 22
                    note = "休講日運休" if "▲" in prefix else ""
                elif route_key == "45":
                    route_no = "45"
                    ride_min = 26
                    note = ""
                    if "工" in prefix:
                        dest = "県立大工学部"
                    elif "横" in prefix:
                        dest = "横関（県立大工学部経由）"
                    else:
                        dest = "書写西住宅（県立大工学部経由）"
                elif route_key == "43":
                    route_no = "43"
                    dest = "緑台（県立大工学部経由）"
                    ride_min = 26
                    note = ""
                else:
                    ride_min = 26
                    note = ""
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
                entries.append({
                    "_sort_key": sta_total,
                    "time": time_str,
                    "arrival_time": f"{(arr_total // 60) % 24:02d}:{arr_total % 60:02d}",
                    "route_no": route_no,
                    "destination": dest,
                    "origin": "姫路駅（北口 18番のりば）始発",
                    "fare": 420,
                    "ride_minutes": ride_min,
                    "note": note,
                })

    entries.sort(key=lambda x: (x["_sort_key"], x["route_no"]))
    for e in entries:
        e.pop("_sort_key", None)
    return entries


# 姫路駅（北口 18番のりば 20000-18）公式平日ダイヤ
FROM_STATION_WEEKDAY_RAW: Dict[str, Dict[int, List[str]]] = {
    "45": {
        6: ["工35", "45"],
        7: ["00", "15", "工30", "55"],
        8: ["10", "20", "25", "55"],
        9: ["25", "55"],
        10: ["00", "25", "55"],
        11: ["25", "55"],
        12: ["25", "55"],
        13: ["25", "55"],
        14: ["25", "55"],
        15: ["25", "工40", "55"],
        16: ["30", "55"],
        17: ["工25", "40", "55"],
        18: ["25", "55"],
        19: ["25", "55"],
        20: ["30", "55"],
        21: ["30", "55"],
        22: ["工15", "45"],
        23: ["工00", "15"],
    },
    "43": {
        8: ["05", "30"],
        9: ["10"],
        10: ["10"],
        11: ["10"],
        12: ["10"],
        13: ["10"],
        14: ["10"],
        15: ["10"],
        16: ["10"],
        17: ["10"],
        18: ["15"],
        19: ["15"],
        20: ["15"],
        21: ["15"],
    },
    "41_42": {
        7: ["古45"],
        8: ["荒40"],
        9: ["バ40"],
        10: ["荒40"],
        11: ["荒40"],
        12: ["荒15", "山40"],
        13: ["荒40"],
        14: ["山40"],
        15: ["山45"],
        16: ["荒45"],
        17: ["◆45"],
        18: ["バ45"],
        19: ["山45"],
        20: ["山45"],
        21: ["荒45"],
        22: ["山30"],
    },
    "直行": {
        8: ["▲05", "▲10", "▲15", "▲20", "▲25", "▲30"],
        9: ["▲50"],
        10: ["▲00", "▲05"],
        11: ["▲45"],
        12: ["▲25"],
        15: ["▲40"],
    },
}

# 姫路駅（北口 18番のりば 20000-18）公式土日祝ダイヤ
FROM_STATION_WEEKEND_RAW: Dict[str, Dict[int, List[str]]] = {
    "45": {
        7: ["05", "15", "35", "45"],
        8: ["10", "50"],
        9: ["25", "45"],
        10: ["25", "55"],
        11: ["25", "55"],
        12: ["25", "55"],
        13: ["25", "55"],
        14: ["25", "55"],
        15: ["25", "55"],
        16: ["25", "55"],
        17: ["25", "55"],
        18: ["30"],
        19: ["00", "30"],
        20: ["00", "30"],
        21: ["15", "45"],
        22: ["工15", "横55"],
    },
    "43": {
        7: ["25"],
        8: ["20", "30"],
        9: ["10"],
        10: ["10"],
        11: ["10"],
        12: ["10"],
        13: ["10"],
        14: ["10"],
        15: ["10"],
        16: ["10"],
        17: ["15"],
        18: ["15"],
        19: ["15"],
        20: ["15"],
        21: ["30"],
    },
    "41_42": {
        9: ["バ55"],
        10: ["荒40"],
        11: ["荒40"],
        12: ["山40"],
        13: ["荒40"],
        14: ["山40"],
        15: ["山40"],
        16: ["荒40"],
        17: ["荒45"],
        18: ["バ45"],
        19: ["山45"],
        20: ["山45"],
        22: ["山35"],
    },
}

TIMETABLE_DB: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "to_station": {
        "weekday": expand_to_station_entries(TO_STATION_WEEKDAY_RAW),
        "weekend": expand_to_station_entries(TO_STATION_WEEKEND_RAW),
    },
    "to_univ": {
        "weekday": expand_from_station_entries(FROM_STATION_WEEKDAY_RAW),
        "weekend": expand_from_station_entries(FROM_STATION_WEEKEND_RAW),
    },
}
