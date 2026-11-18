# -*- coding: utf-8 -*-
"""
神姫バス「県立大工学部前 ⇔ 姫路駅（北口）」
リアルタイム接近情報 ＆ 時刻表統合 バックエンドAPIサーバー
"""

import datetime
import html.parser
import http.cookiejar
import json
import mimetypes
import os
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from timetable_data import (
    BUS_STOPS_META,
    ROUTE_STOPS_TO_STATION,
    ROUTE_STOPS_TO_UNIV,
    TIMETABLE_DB,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
JST = datetime.timezone(datetime.timedelta(hours=9))

STATION_CODE_MAP: Dict[str, str] = {
    "20000": "姫路駅（北口）",
    "20001": "大手前通り",
    "20032": "白鷺橋",
    "20157": "姫路城大手門前（西方面）",
    "20240": "県立大工学部前",
    "20062": "県立大環境人間学部",
    "19165": "書写西住宅",
    "28012": "緑台",
}


class _UnkohHTMLParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.csrf_token: Optional[str] = None
        self.results: List[Dict[str, Any]] = []
        self._current_card: Optional[Dict[str, Any]] = None
        self._card_depth: int = 0
        self._capture_target: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: (v or "") for k, v in attrs}
        cls = attr_dict.get("class", "")

        if tag == "input" and attr_dict.get("name") == "csrfmiddlewaretoken":
            self.csrf_token = attr_dict.get("value", "")

        if tag == "div" and "kensaku_result" in cls.split():
            self._current_card = {
                "dep_time": "",
                "arr_time": "",
                "route_no": "",
                "route_desc": "",
                "status_text": "",
                "stepwell": "",
            }
            self._card_depth = 1
            return

        if self._current_card is not None:
            if tag == "div":
                self._card_depth += 1
                stepwell_attr = attr_dict.get("stepwell_", "")
                if not stepwell_attr:
                    for token in cls.split():
                        if token.startswith("stepwell_"):
                            stepwell_attr = token
                            break
                if stepwell_attr and not self._current_card["stepwell"]:
                    self._current_card["stepwell"] = stepwell_attr

            if tag == "span":
                if "res_hatsu" in cls:
                    self._capture_target = "dep_time"
                elif "res_chaku" in cls:
                    self._capture_target = "arr_time"
                elif "res_no_content" in cls or "res_no" in cls:
                    self._capture_target = "route_no"
                elif "info_unkou" in cls:
                    self._capture_target = "status_text"
            elif tag == "p" and "right_pad" in cls:
                self._capture_target = "route_desc"

    def handle_data(self, data: str) -> None:
        if self._current_card is not None and self._capture_target:
            text = data.strip()
            if text:
                prev = self._current_card.get(self._capture_target, "")
                self._current_card[self._capture_target] = (prev + " " + text).strip() if prev else text

    def handle_endtag(self, tag: str) -> None:
        if self._capture_target and tag in ("span", "p"):
            self._capture_target = None
        if self._current_card is not None and tag == "div":
            self._card_depth -= 1
            if self._card_depth <= 0:
                if self._current_card.get("dep_time"):
                    self.results.append(self._current_card)
                self._current_card = None


class ShinkiNaviLiveClient:
    BASE_URL = "https://navi.shinkibus.jp"
    USER_AGENT = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )

    def __init__(self, timeout: float = 3.0) -> None:
        self.timeout = timeout
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def fetch_live_direction(
        self, direction: str, now_dt: datetime.datetime
    ) -> Dict[str, Any]:
        if direction == "to_station":
            from_code, from_name = "20240", "県立大工学部"
            to_code, to_name = "20000", "姫路駅（北口）"
        else:
            from_code, from_name = "20000", "姫路駅（北口）"
            to_code, to_name = "20240", "県立大工学部"

        try:
            req_top = urllib.request.Request(
                f"{self.BASE_URL}/",
                headers={"User-Agent": self.USER_AGENT},
            )
            with self.opener.open(req_top, timeout=self.timeout) as resp:
                top_html = resp.read().decode("utf-8", errors="ignore")

            parser_top = _UnkohHTMLParser()
            parser_top.feed(top_html)
            csrf_token = parser_top.csrf_token
            if not csrf_token:
                m = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', top_html)
                csrf_token = m.group(1) if m else ""

            if not csrf_token:
                return {"ok": False, "source": "timetable_fallback", "live_items_by_time": {}}

            form_data = {
                "csrfmiddlewaretoken": csrf_token,
                "from_busstop": from_code,
                "from_busstop_name": from_name,
                "que_start_text": from_name,
                "to_busstop": to_code,
                "to_busstop_name": to_name,
                "que_end_text": to_name,
                "genjikoku_isset": "yes",
                "date_year": str(now_dt.year),
                "date_month": str(now_dt.month),
                "date_day": str(now_dt.day),
                "date_hour": str(now_dt.hour),
                "date_minute": str(now_dt.minute),
                "this_time_is": "start",
            }
            encoded_form = urllib.parse.urlencode(form_data).encode("utf-8")
            req_unkoh = urllib.request.Request(
                f"{self.BASE_URL}/unkoh/",
                data=encoded_form,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Referer": f"{self.BASE_URL}/",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with self.opener.open(req_unkoh, timeout=self.timeout) as resp:
                unkoh_html = resp.read().decode("utf-8", errors="ignore")

            parser_unkoh = _UnkohHTMLParser()
            parser_unkoh.feed(unkoh_html)

            live_by_time: Dict[str, Dict[str, Any]] = {}
            proxy_params: List[Tuple[str, str, str, str, str, str]] = []

            for card in parser_unkoh.results:
                dep_m = re.search(r"(\d{1,2}:\d{2})", card.get("dep_time", ""))
                if not dep_m:
                    continue
                hhmm = dep_m.group(1)
                if len(hhmm) == 4:
                    hhmm = "0" + hhmm

                status_text = card.get("status_text", "") or "定刻運行"
                delay_min = 0
                delay_m = re.search(r"(\d+)\s*分遅れ", status_text)
                if delay_m:
                    delay_min = int(delay_m.group(1))
                elif "少し遅れ" in status_text:
                    delay_min = 1

                stepwell = card.get("stepwell", "")
                parts = stepwell.split("_")
                if len(parts) >= 6 and parts[0] == "stepwell":
                    proxy_params.append((hhmm, parts[1], parts[2], parts[3], parts[4], parts[5]))

                live_by_time[hhmm] = {
                    "dep_time": hhmm,
                    "status_text": status_text,
                    "delay_minutes": delay_min,
                    "is_running": "運行前" not in status_text,
                    "gps_station_cd": None,
                    "gps_station_name": None,
                }

            if proxy_params:
                xs = ",".join(p[1] for p in proxy_params)
                ys = ",".join(p[2] for p in proxy_params)
                zs = ",".join(p[3] for p in proxy_params)
                ts = ",".join(p[4] for p in proxy_params)
                us = ",".join(p[5] for p in proxy_params)
                proxy_url = (
                    f"{self.BASE_URL}/bus_proxy/?"
                    f"x={urllib.parse.quote(xs)}&y={urllib.parse.quote(ys)}"
                    f"&z={urllib.parse.quote(zs)}&t={urllib.parse.quote(ts)}&u={urllib.parse.quote(us)}"
                )
                req_proxy = urllib.request.Request(
                    proxy_url,
                    headers={"User-Agent": self.USER_AGENT, "Referer": f"{self.BASE_URL}/unkoh/"},
                )
                with self.opener.open(req_proxy, timeout=self.timeout) as resp:
                    proxy_json = json.loads(resp.read().decode("utf-8", errors="ignore"))

                if isinstance(proxy_json, list):
                    for idx, item in enumerate(proxy_json):
                        if idx >= len(proxy_params) or not isinstance(item, dict):
                            continue
                        hhmm = proxy_params[idx][0]
                        if hhmm not in live_by_time:
                            continue
                        unkyu = item.get("unkyu_info", "")
                        delay_val = int(item.get("delay_time", 0) or 0)
                        last_cd = str(item.get("last_station_cd", "") or "")
                        live_by_time[hhmm]["delay_minutes"] = max(live_by_time[hhmm]["delay_minutes"], delay_val)
                        live_by_time[hhmm]["is_running"] = (unkyu == "運行")
                        if last_cd:
                            live_by_time[hhmm]["gps_station_cd"] = last_cd
                            live_by_time[hhmm]["gps_station_name"] = STATION_CODE_MAP.get(last_cd)

            return {
                "ok": len(live_by_time) > 0,
                "source": "shinkibus_navi_live" if live_by_time else "timetable_fallback",
                "live_items_by_time": live_by_time,
            }
        except Exception:
            return {
                "ok": False,
                "source": "timetable_fallback",
                "live_items_by_time": {},
            }


def _build_track_stops(direction: str, origin_label: str, route_no: str = "") -> List[Dict[str, Any]]:
    """路線図バー上に表示する主要停留所（％位置・ラベル・乗車停留所フラグ）を返す"""
    if direction == "to_univ":
        return [
            {"label": "姫路駅(北口)", "percent": 0, "is_boarding": True},
            {"label": "大手門前", "percent": 25, "is_boarding": False},
            {"label": "辻井", "percent": 50, "is_boarding": False},
            {"label": "横関", "percent": 75, "is_boarding": False},
            {"label": "県立大工学部", "percent": 100, "is_boarding": False},
        ]

    if "県立大工学部始発" in origin_label:
        if route_no == "直行":
            return [
                {"label": "県立大工学部", "percent": 0, "is_boarding": True},
                {"label": "直行（ノンストップ）", "percent": 50, "is_boarding": False},
                {"label": "姫路駅(北口)", "percent": 100, "is_boarding": False},
            ]
        return [
            {"label": "県立大工学部", "percent": 0, "is_boarding": True},
            {"label": "横関", "percent": 28, "is_boarding": False},
            {"label": "辻井", "percent": 55, "is_boarding": False},
            {"label": "白鷺橋", "percent": 78, "is_boarding": False},
            {"label": "姫路駅(北口)", "percent": 100, "is_boarding": False},
        ]

    if "書写西住宅" in origin_label:
        return [
            {"label": "書写西住宅", "percent": 0, "is_boarding": False},
            {"label": "書写台1丁目", "percent": 24, "is_boarding": False},
            {"label": "県立大工学部", "percent": 48, "is_boarding": True},
            {"label": "横関", "percent": 74, "is_boarding": False},
            {"label": "姫路駅(北口)", "percent": 100, "is_boarding": False},
        ]

    origin_short = origin_label.replace("発", "").replace("・荒木", "")
    return [
        {"label": origin_short, "percent": 0, "is_boarding": False},
        {"label": "打越", "percent": 24, "is_boarding": False},
        {"label": "六角", "percent": 44, "is_boarding": False},
        {"label": "床坂菅生台", "percent": 62, "is_boarding": False},
        {"label": "県立大工学部", "percent": 80, "is_boarding": True},
        {"label": "姫路駅(北口)", "percent": 100, "is_boarding": False},
    ]


def _estimate_bus_position(
    direction: str,
    minutes_until_departure: int,
    delay_minutes: int,
    origin_label: str,
    route_no: str = "",
    gps_station_name: Optional[str] = None,
) -> Dict[str, Any]:
    stops = ROUTE_STOPS_TO_STATION if direction == "to_station" else ROUTE_STOPS_TO_UNIV
    boarding_idx = next((i for i, s in enumerate(stops) if s.get("zone") == "boarding"), 0)
    track_stops = _build_track_stops(direction, origin_label, route_no)
    boarding_pct = next((s["percent"] for s in track_stops if s.get("is_boarding")), 80)

    if gps_station_name:
        return {
            "headline": f"「{gps_station_name}」付近を走行中",
            "subtext": f"乗車バス停まで あと約{max(0, minutes_until_departure)}分",
            "progress_percent": min(max(0, boarding_pct - 4), max(8, int(boarding_pct - minutes_until_departure * 5))),
            "track_stops": track_stops,
        }

    # 姫路駅（北口 18番のりば）始発 または 県立大工学部始発の場合
    if direction == "to_univ" or "県立大工学部始発" in origin_label:
        boarding_name = "姫路駅（北口 18番のりば）" if direction == "to_univ" else "県立大工学部"
        if minutes_until_departure > 5:
            return {
                "headline": f"{boarding_name}（始発）発車待機中",
                "subtext": f"当停留所始発便（発車{minutes_until_departure}分前）",
                "progress_percent": 0,
                "track_stops": track_stops,
            }
        else:
            return {
                "headline": f"{boarding_name} のりば着車・乗車案内中",
                "subtext": "まもなく当停留所から発車します",
                "progress_percent": 2,
                "track_stops": track_stops,
            }

    # 45系統（書写西住宅発）は 3分前発車、41/42/43系統は 10分前発車
    if "書写西住宅" in origin_label:
        earliest_offset = -3
        upstream_stops = [
            {"name": "書写西住宅", "offset_min": -3},
            {"name": "集会所前", "offset_min": -2},
            {"name": "書写台１丁目", "offset_min": -1},
            {"name": "県立大工学部", "offset_min": 0},
        ]
    else:
        earliest_offset = -10
        upstream_stops = [
            {"name": origin_label.replace("発", ""), "offset_min": -10},
            {"name": "打越", "offset_min": -6},
            {"name": "六角", "offset_min": -5},
            {"name": "床坂菅生台", "offset_min": -3},
            {"name": "県立大工学部", "offset_min": 0},
        ]

    rel_min = -minutes_until_departure
    if rel_min < earliest_offset:
        wait_to_start = abs(rel_min - earliest_offset)
        origin_clean = origin_label.replace("発", "")
        return {
            "headline": f"{origin_clean}（始発）にて発車待機中",
            "subtext": f"約{wait_to_start}分後に始発停留所を発車予定",
            "progress_percent": 0,
            "track_stops": track_stops,
        }

    if rel_min >= -1:
        prev_stop = upstream_stops[-2]["name"]
        return {
            "headline": "まもなく「県立大工学部」に到着します",
            "subtext": f"1つ前の「{prev_stop}」を通過済み",
            "progress_percent": max(4, boarding_pct - 4),
            "track_stops": track_stops,
        }

    current_stop = upstream_stops[0]
    next_stop = upstream_stops[1]
    current_idx = 0
    for idx in range(len(upstream_stops) - 1):
        s_curr = upstream_stops[idx]
        s_next = upstream_stops[idx + 1]
        if s_curr["offset_min"] <= rel_min <= s_next["offset_min"]:
            current_stop = s_curr
            next_stop = s_next
            current_idx = idx
            break

    stops_away = max(1, (len(upstream_stops) - 1) - current_idx)
    span = abs(earliest_offset)
    prog = max(4, min(boarding_pct - 4, int(((rel_min - earliest_offset) / max(1, span)) * boarding_pct)))
    c_name = current_stop["name"]
    n_name = next_stop["name"]
    delay_badge = f"（遅れ+{delay_minutes}分反映）" if delay_minutes > 0 else "（定刻走行中）"

    return {
        "headline": f"「{c_name}」〜「{n_name}」付近を走行中",
        "subtext": f"県立大工学部まで あと{stops_away}区間・約{minutes_until_departure}分 {delay_badge}",
        "progress_percent": prog,
        "track_stops": track_stops,
    }


def build_bus_status_payload(
    direction: str = "to_station",
    override_time: Optional[str] = None,
    override_day_type: Optional[str] = None,
) -> Dict[str, Any]:
    now_dt = datetime.datetime.now(JST)

    if override_time and re.match(r"^\d{1,2}:\d{2}$", override_time):
        hh, mm = map(int, override_time.split(":"))
        now_dt = now_dt.replace(hour=hh % 24, minute=mm % 60, second=0)

    if override_day_type in ("weekday", "weekend"):
        day_type = override_day_type
    else:
        day_type = "weekend" if now_dt.weekday() >= 5 else "weekday"

    direction_key = "to_univ" if direction == "to_univ" else "to_station"
    schedule_list = TIMETABLE_DB[direction_key][day_type]

    live_client = ShinkiNaviLiveClient(timeout=2.8)
    live_res = live_client.fetch_live_direction(direction_key, now_dt)
    live_map = live_res.get("live_items_by_time", {})

    now_minutes = now_dt.hour * 60 + now_dt.minute
    enriched_upcoming: List[Dict[str, Any]] = []

    for item in schedule_list:
        t_parts = list(map(int, item["time"].split(":")))
        sched_min = t_parts[0] * 60 + t_parts[1]

        live_info = live_map.get(item["time"])
        if live_info:
            delay_min = int(live_info.get("delay_minutes", 0))
            status_text = live_info.get("status_text", "定刻運行")
            gps_station = live_info.get("gps_station_name")
        else:
            delay_min = 0
            status_text = "定刻運行" if sched_min - now_minutes <= 15 else "運行予定"
            gps_station = None

        expected_min = sched_min + delay_min
        minutes_until = expected_min - now_minutes
        if minutes_until < 0:
            continue

        exp_h = (expected_min // 60) % 24
        exp_m = expected_min % 60
        expected_time_str = f"{exp_h:02d}:{exp_m:02d}"

        arr_parts = list(map(int, item["arrival_time"].split(":")))
        arr_min = arr_parts[0] * 60 + arr_parts[1] + delay_min
        expected_arrival_str = f"{(arr_min // 60) % 24:02d}:{arr_min % 60:02d}"

        pos_info = _estimate_bus_position(
            direction=direction_key,
            minutes_until_departure=minutes_until,
            delay_minutes=delay_min,
            origin_label=item.get("origin", ""),
            route_no=item.get("route_no", ""),
            gps_station_name=gps_station,
        )

        enriched_upcoming.append({
            **item,
            "scheduled_time": item["time"],
            "expected_time": expected_time_str,
            "expected_arrival_time": expected_arrival_str,
            "minutes_until": minutes_until,
            "delay_minutes": delay_min,
            "status_text": status_text,
            "location": pos_info,
        })

    is_tomorrow = False
    if not enriched_upcoming and schedule_list:
        is_tomorrow = True
        for item in schedule_list[:5]:
            t_parts = list(map(int, item["time"].split(":")))
            sched_min = (t_parts[0] + 24) * 60 + t_parts[1]
            minutes_until = sched_min - now_minutes
            enriched_upcoming.append({
                **item,
                "scheduled_time": item["time"],
                "expected_time": item["time"],
                "expected_arrival_time": item["arrival_time"],
                "minutes_until": minutes_until,
                "delay_minutes": 0,
                "status_text": "翌朝始発予定",
                "location": {
                    "headline": "本日の運行終了（翌朝始発待機）",
                    "subtext": f"翌朝 {item['time']} 発の始発便です",
                    "progress_percent": 0,
                },
            })

    if direction_key == "to_station":
        header_info = {
            "direction": "to_station",
            "title": "県立大工学部前 → 姫路駅（北口）",
            "from_stop": "県立大工学部前（のりば2）",
            "to_stop": "姫路駅（北口）",
            "timetable_url": BUS_STOPS_META["kenritsudai_kogakubu"]["timetable_url"],
        }
    else:
        header_info = {
            "direction": "to_univ",
            "title": "姫路駅（北口） → 県立大工学部前",
            "from_stop": "姫路駅（北口 18番のりば）",
            "to_stop": "県立大工学部前",
            "timetable_url": BUS_STOPS_META["himeji_station"]["timetable_url"],
        }

    return {
        "updated_at": now_dt.strftime("%H:%M:%S"),
        "day_type": day_type,
        "day_type_label": "土日祝ダイヤ" if day_type == "weekend" else "平日ダイヤ",
        "is_tomorrow": is_tomorrow,
        "data_source": {
            "mode": live_res.get("source", "timetable_fallback"),
            "label": "神姫バスNavi 連携中" if live_res.get("ok") else "時刻表・位置推定モード",
            "live_connected": bool(live_res.get("ok")),
        },
        "header": header_info,
        "next_bus": enriched_upcoming[0] if enriched_upcoming else None,
        "upcoming_buses": enriched_upcoming[:5],
    }


def build_full_timetable_payload(direction: str = "to_station") -> Dict[str, Any]:
    direction_key = "to_univ" if direction == "to_univ" else "to_station"
    return {
        "direction": direction_key,
        "weekday": TIMETABLE_DB[direction_key]["weekday"],
        "weekend": TIMETABLE_DB[direction_key]["weekend"],
    }


class ShinkiBusHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[ShinkiBusApp] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _serve_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File Not Found")
            return
        ctype, _ = mimetypes.guess_type(str(file_path))
        if not ctype:
            ctype = "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        raw = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/bus-status":
            direction = qs.get("direction", ["to_station"])[0]
            if direction == "to_castle":
                direction = "to_station"
            override_time = qs.get("time", [None])[0]
            override_day = qs.get("day_type", [None])[0]
            try:
                payload = build_bus_status_payload(
                    direction=direction,
                    override_time=override_time,
                    override_day_type=override_day,
                )
                self._send_json(payload, 200)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return

        if path == "/api/timetable":
            direction = qs.get("direction", ["to_station"])[0]
            if direction == "to_castle":
                direction = "to_station"
            self._send_json(build_full_timetable_payload(direction=direction), 200)
            return

        if path in ("/", "/index.html"):
            self._serve_file(STATIC_DIR / "index.html")
            return

        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            target = (STATIC_DIR / rel).resolve()
            if str(target).startswith(str(STATIC_DIR)):
                self._serve_file(target)
                return

        candidate = (STATIC_DIR / path.lstrip("/")).resolve()
        if str(candidate).startswith(str(STATIC_DIR)) and candidate.is_file():
            self._serve_file(candidate)
            return

        self.send_error(404, "Not Found")


def run_server(host: str = "127.0.0.1", port: int = 8050) -> None:
    server = ThreadingHTTPServer((host, port), ShinkiBusHTTPRequestHandler)
    print(f"Server started at http://{host}:{port}/")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    host_addr = os.environ.get("HOST", "0.0.0.0")
    port_num = int(os.environ.get("PORT", "8050"))
    run_server(host=host_addr, port=port_num)
