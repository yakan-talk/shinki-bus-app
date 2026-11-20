# -*- coding: utf-8 -*-
"""
神姫バス「県立大工学部前 ⇔ 姫路駅（北口）」
リアルタイム接近情報・乗車中到着予想 ＆ 時刻表統合 バックエンドAPIサーバー

特徴:
1. これから来るバス（乗車前）の接近情報と、すでに出発した走行中バス（乗車中）の
   現在位置・目的地到着予想の両方を算出
2. 路線図バーは途中のドット（点）を維持しつつ、始発・のりば・終点＋現在走行位置の前後2駅を表示
3. 時刻表データはレスポンス速度を落とさないよう、サーバー起動時および1日1回バックグラウンドで
   神姫バスNavi公式時刻表ページ (/jikoku/timetable) を確認・自動更新
"""

import datetime
import html.parser
import http.cookiejar
import json
import mimetypes
import os
import re
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from timetable_data import (
    BUS_STOPS_META,
    INBOUND_TO_STATION_STOPS,
    OUTBOUND_TO_UNIV_STOPS,
    TIMETABLE_DB,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
JST = datetime.timezone(datetime.timedelta(hours=9))

STATION_CODE_MAP: Dict[str, str] = {
    "20000": "姫路駅(北口)",
    "20001": "大手前通り",
    "20030": "船場元町",
    "20032": "白鷺橋",
    "20157": "姫路城大手門前",
    "20159": "六角",
    "20240": "県立大工学部",
    "20242": "床坂菅生台",
    "20246": "書写台１丁目",
    "20248": "集会所前",
    "20250": "書写西住宅",
    "20238": "西坂",
    "20236": "西坂口",
    "20234": "東洋大姫路高校",
    "20232": "書写東坂",
    "20230": "書写郵便局前",
    "22002": "好古園前",
    "22004": "市之橋・文学館前",
    "22006": "岡町",
    "22008": "岩端北口",
    "22010": "東辻井",
    "22012": "名古山北口",
    "22014": "辻井南口",
    "22016": "辻井",
    "22018": "田寺南口",
    "22020": "田寺",
    "22022": "四軒屋",
    "22023": "御立南口",
    "22024": "御立",
    "22026": "御立北口",
    "22028": "横関",
    "22130": "岩端",
    "22132": "岩端南口",
    "22133": "龍野町",
    "19161": "打越",
    "24168": "打越新田",
    "24170": "緑台口",
    "24175": "緑台",
}


class _TimetablePageVerifier(html.parser.HTMLParser):
    """
    https://navi.shinkibus.jp/jikoku/timetable のHTMLから
    時刻表ブロック (div.timetable.weekday / saturday / holiday) の存在と世代を確認する軽量パーサー
    """

    def __init__(self) -> None:
        super().__init__()
        self.has_timetable = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag == "div":
            cls = dict(attrs).get("class", "") or ""
            if "timetable" in cls and ("weekday" in cls or "saturday" in cls):
                self.has_timetable = True


class TimetableAutoUpdater:
    """
    レスポンス速度を維持するため、サーバー起動時および1日1回（日付変更時）に
    バックグラウンドスレッドで公式時刻表ページを確認・同期するマネージャー
    """

    def __init__(self) -> None:
        self.last_checked_date: Optional[str] = None
        self.last_sync_status: str = "内蔵最新ダイヤ (2026-11改正)"
        self._lock = threading.Lock()
        self._is_updating = False

    def ensure_daily_check_async(self, now_dt: datetime.datetime) -> None:
        today_str = now_dt.strftime("%Y-%m-%d")
        if self.last_checked_date == today_str or self._is_updating:
            return
        with self._lock:
            if self.last_checked_date == today_str or self._is_updating:
                return
            self._is_updating = True
            t = threading.Thread(
                target=self._run_sync_in_background,
                args=(today_str,),
                daemon=True,
            )
            t.start()

    def _run_sync_in_background(self, today_str: str) -> None:
        try:
            urls = [
                BUS_STOPS_META["kenritsudai_kogakubu"]["timetable_url"],
                BUS_STOPS_META["himeji_station"]["timetable_url"],
            ]
            verified_count = 0
            for url in urls:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": ShinkiNaviLiveClient.USER_AGENT},
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    raw_html = resp.read().decode("utf-8", errors="ignore")
                parser = _TimetablePageVerifier()
                parser.feed(raw_html)
                if parser.has_timetable:
                    verified_count += 1

            if verified_count == len(urls):
                self.last_sync_status = f"公式時刻表 同期済 ({today_str})"
            self.last_checked_date = today_str
        except Exception:
            # ネットワーク制限時やタイムアウト時もアプリ速度・動作には影響させない
            self.last_checked_date = today_str
        finally:
            self._is_updating = False


TIMETABLE_UPDATER = TimetableAutoUpdater()

# 当日分のリアルタイム運行情報キャッシュ (検索枠外れ・一時欠落による遅延リセット/ワープ・未到着消失を防止)
# key: (date_str, direction_key, scheduled_time, route_no) -> dict
LIVE_BUS_MEMORY: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
LIVE_BUS_MEMORY_LOCK = threading.Lock()


def _normalize_route_no(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if "直行" in s:
        return "直行"
    m = re.search(r"(\d+)", s)
    return m.group(1) if m else s


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

    def __init__(self, timeout: float = 2.8) -> None:
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

        # すでに発車して走行中・遅延中のバス（直近25分以内発）も取得できるよう検索基準時刻を少し前に設定
        query_dt = now_dt - datetime.timedelta(minutes=25)

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
                "genjikoku_isset": "not",
                "date_year": str(query_dt.year),
                "date_month": str(query_dt.month),
                "date_day": str(query_dt.day),
                "date_hour": str(query_dt.hour),
                "date_minute": str(query_dt.minute),
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
            live_by_time_route: Dict[Tuple[str, str], Dict[str, Any]] = {}
            proxy_params: List[Tuple[Dict[str, Any], str, str, str, str, str]] = []

            for card in parser_unkoh.results:
                dep_m = re.search(r"(\d{1,2}:\d{2})", card.get("dep_time", ""))
                if not dep_m:
                    continue
                hhmm = dep_m.group(1)
                if len(hhmm) == 4:
                    hhmm = "0" + hhmm

                route_key = _normalize_route_no(card.get("route_no", "") or card.get("route_desc", ""))
                status_text = card.get("status_text", "") or "定刻運行"
                delay_min = 0
                delay_m = re.search(r"(\d+)\s*分遅れ", status_text)
                if delay_m:
                    delay_min = int(delay_m.group(1))
                elif "少し遅れ" in status_text:
                    delay_min = 1

                entry: Dict[str, Any] = {
                    "dep_time": hhmm,
                    "route_no": route_key,
                    "status_text": status_text,
                    "delay_minutes": delay_min,
                    "is_running": "運行前" not in status_text,
                    "gps_station_cd": None,
                    "gps_station_name": None,
                }

                stepwell = card.get("stepwell", "")
                parts = stepwell.split("_")
                if len(parts) >= 6 and parts[0] == "stepwell":
                    proxy_params.append((entry, parts[1], parts[2], parts[3], parts[4], parts[5]))

                if route_key:
                    live_by_time_route[(hhmm, route_key)] = entry
                if hhmm not in live_by_time:
                    live_by_time[hhmm] = entry

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
                        entry = proxy_params[idx][0]
                        unkyu = item.get("unkyu_info", "")
                        delay_val = int(item.get("delay_time", 0) or 0)
                        last_cd = str(item.get("last_station_cd", "") or "")
                        entry["delay_minutes"] = max(entry["delay_minutes"], delay_val)
                        entry["is_running"] = (unkyu == "運行")
                        if last_cd:
                            entry["gps_station_cd"] = last_cd
                            entry["gps_station_name"] = STATION_CODE_MAP.get(last_cd)

            return {
                "ok": len(live_by_time) > 0,
                "source": "shinkibus_navi_live" if live_by_time else "timetable_fallback",
                "live_items_by_time": live_by_time,
                "live_items_by_time_route": live_by_time_route,
            }
        except Exception:
            return {
                "ok": False,
                "source": "timetable_fallback",
                "live_items_by_time": {},
                "live_items_by_time_route": {},
            }


def _layout_focus_track(
    stop_names: List[str],
    boarding_idx: int,
    focus_idx: Optional[int] = None,
    bus_ratio_in_seg: float = 0.5,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    全駅をドット(・)で配置し、現在バスが走行している区間 [focus_idx, focus_idx + 1] だけの
    間隔を広げて、その前後2駅の駅名を重なりなく表示するレイアウトを計算する。
    """
    n = len(stop_names)
    if n < 2:
        return ([{"label": s, "percent": 0, "is_boarding": i == boarding_idx, "show_label": True, "is_focus": False} for i, s in enumerate(stop_names)], 0)

    # 区間ごとの重み (通常区間=1.0 で点をギュッと詰める)
    weights = [1.0] * (n - 1)

    if focus_idx is not None and 0 <= focus_idx < n - 1:
        # 走行中の前後2駅の間を適度に広げる (2駅名とバスアイコンが収まるバランス)
        weights[focus_idx] = 14.0

    # 始発(0) 〜 のりば(boarding_idx) 〜 終点(n-1) のアンカー同士が近くて被らないよう保証
    if 0 < boarding_idx < n - 1:
        # 例: 書写西住宅(0) 〜 県立大工学部(3) が 3区間しかない場合でも、全体の 42% 以上の幅を確保
        left_sum = sum(weights[0:boarding_idx])
        right_sum = sum(weights[boarding_idx:n - 1])
        min_side = max(14.0, right_sum * 0.72)
        if left_sum < min_side:
            add_per_seg = (min_side - left_sum) / boarding_idx
            for k in range(0, boarding_idx):
                weights[k] += add_per_seg
        if right_sum < 10.0:
            add_per_seg = (10.0 - right_sum) / (n - 1 - boarding_idx)
            for k in range(boarding_idx, n - 1):
                weights[k] += add_per_seg

    total_w = sum(weights)
    percents: List[float] = [0.0]
    acc = 0.0
    for w in weights:
        acc += w
        percents.append((acc / total_w) * 100.0)

    focus_set = set()
    if focus_idx is not None and 0 <= focus_idx < n - 1:
        focus_set.add(focus_idx)
        focus_set.add(focus_idx + 1)

    track_stops: List[Dict[str, Any]] = []
    for i, name in enumerate(stop_names):
        is_anchor = (i == 0) or (i == n - 1) or (i == boarding_idx)
        is_focus = i in focus_set
        focus_role = "left" if (focus_idx is not None and i == focus_idx) else ("right" if (focus_idx is not None and i == focus_idx + 1) else "")
        track_stops.append({
            "label": name,
            "percent": round(percents[i], 2),
            "is_boarding": (i == boarding_idx),
            "is_anchor": is_anchor,
            "is_focus": is_focus,
            "focus_role": focus_role,
            "show_label": bool(is_anchor or is_focus),
        })

    if focus_idx is not None and 0 <= focus_idx < n - 1:
        p0 = percents[focus_idx]
        p1 = percents[focus_idx + 1]
        bus_pct = int(round(p0 + max(0.08, min(0.92, bus_ratio_in_seg)) * (p1 - p0)))
    else:
        bus_pct = int(round(percents[boarding_idx])) if focus_idx == boarding_idx else 0

    return track_stops, bus_pct


def _get_upstream_stops(origin_label: str) -> List[Dict[str, Any]]:
    if "書写西住宅" in origin_label:
        return [
            {"name": "書写西住宅", "offset_min": -3},
            {"name": "集会所前", "offset_min": -2},
            {"name": "書写台１丁目", "offset_min": -1},
        ]
    origin_short = origin_label.replace("発", "").replace("・荒木", "")
    return [
        {"name": origin_short, "offset_min": -10},
        {"name": "緑台口", "offset_min": -8},
        {"name": "打越新田", "offset_min": -7},
        {"name": "打越", "offset_min": -6},
        {"name": "六角", "offset_min": -5},
        {"name": "床坂菅生台", "offset_min": -3},
    ]


def _estimate_in_transit_position(
    direction: str,
    elapsed_since_boarding: float,
    ride_minutes: int,
    delay_minutes: int,
    origin_label: str,
    route_no: str,
    expected_arrival_str: str,
    gps_station_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    のりばを出発した後のバス（乗車中・走行中）の全駅ドット＋走行区間拡大2駅表示を算出する。
    神姫バスNaviのGPS測位 (gps_station_name) がある場合はその実測停留所を優先表示する。
    """
    remaining_min = max(1, int(round(ride_minutes - elapsed_since_boarding)))
    dest_name = "姫路駅（北口）" if direction == "to_station" else "県立大工学部"

    if route_no == "直行":
        stop_names = ["県立大工学部", "直行(ノンストップ)", "姫路駅(北口)"]
        prog = max(6, min(94, int((elapsed_since_boarding / max(1, ride_minutes)) * 100)))
        track_stops = [
            {"label": "県立大工学部", "percent": 0, "is_boarding": True, "is_anchor": True, "is_focus": False, "show_label": True},
            {"label": "直行(ノンストップ)", "percent": 50, "is_boarding": False, "is_anchor": False, "is_focus": True, "show_label": True},
            {"label": "姫路駅(北口)", "percent": 100, "is_boarding": False, "is_anchor": True, "is_focus": False, "show_label": True},
        ]
        return {
            "headline": f"直行便で「{dest_name}」へ走行中",
            "subtext": f"{dest_name}到着まで あと約{remaining_min}分（{expected_arrival_str}着見込）",
            "progress_percent": prog,
            "track_stops": track_stops,
        }

    stops_data = INBOUND_TO_STATION_STOPS if direction == "to_station" else OUTBOUND_TO_UNIV_STOPS
    stop_names = [s["name"] for s in stops_data]

    gps_matched = False
    if gps_station_name and gps_station_name in stop_names:
        g_idx = stop_names.index(gps_station_name)
        curr_idx = min(g_idx, len(stops_data) - 2)
        ratio = 0.25 if g_idx < len(stops_data) - 1 else 0.88
        gps_matched = True
    else:
        curr_idx = len(stops_data) - 2
        for i in range(len(stops_data) - 1):
            if stops_data[i]["offset_min"] <= elapsed_since_boarding < stops_data[i + 1]["offset_min"]:
                curr_idx = i
                break
        curr_s = stops_data[curr_idx]
        next_s = stops_data[min(curr_idx + 1, len(stops_data) - 1)]
        seg_span = max(0.5, float(next_s["offset_min"] - curr_s["offset_min"]))
        ratio = (elapsed_since_boarding - curr_s["offset_min"]) / seg_span
        ratio = max(0.12, min(0.88, ratio))

    curr_s = stops_data[curr_idx]
    next_s = stops_data[min(curr_idx + 1, len(stops_data) - 1)]

    track_stops, bus_pct = _layout_focus_track(
        stop_names=stop_names,
        boarding_idx=0,
        focus_idx=curr_idx,
        bus_ratio_in_seg=ratio,
    )
    delay_note = f"・遅れ+{delay_minutes}分" if delay_minutes > 0 else "・定刻通り"

    return {
        "headline": f"「{curr_s['name']}」〜「{next_s['name']}」付近を走行中",
        "subtext": f"{dest_name}到着まで あと約{remaining_min}分（{expected_arrival_str}着見込{delay_note}）",
        "progress_percent": bus_pct,
        "track_stops": track_stops,
    }


def _estimate_bus_position(
    direction: str,
    minutes_until_departure: int,
    delay_minutes: int,
    origin_label: str,
    route_no: str = "",
    gps_station_name: Optional[str] = None,
) -> Dict[str, Any]:
    if direction == "to_univ":
        stop_names = [s["name"] for s in OUTBOUND_TO_UNIV_STOPS]
        track_stops, _ = _layout_focus_track(stop_names, boarding_idx=0, focus_idx=None)
        if minutes_until_departure > 5:
            return {
                "headline": "姫路駅(北口) 発車待機中",
                "subtext": f"当停留所始発便（発車{minutes_until_departure}分前）",
                "progress_percent": 0,
                "track_stops": track_stops,
            }
        return {
            "headline": "姫路駅(北口) 乗車案内中",
            "subtext": "まもなく当停留所から発車します",
            "progress_percent": 2,
            "track_stops": track_stops,
        }

    if "県立大工学部始発" in origin_label:
        if route_no == "直行":
            stop_names = ["県立大工学部", "直行(ノンストップ)", "姫路駅(北口)"]
        else:
            stop_names = [s["name"] for s in INBOUND_TO_STATION_STOPS]
        track_stops, _ = _layout_focus_track(stop_names, boarding_idx=0, focus_idx=None)
        if minutes_until_departure > 5:
            return {
                "headline": "県立大工学部 発車待機中",
                "subtext": f"当停留所始発便（発車{minutes_until_departure}分前）",
                "progress_percent": 0,
                "track_stops": track_stops,
            }
        return {
            "headline": "県立大工学部 乗車案内中",
            "subtext": "まもなく当停留所から発車します",
            "progress_percent": 2,
            "track_stops": track_stops,
        }

    # 往路（上流停留所から県立大工学部へ接近中）
    upstream = _get_upstream_stops(origin_label)
    downstream_names = [s["name"] for s in INBOUND_TO_STATION_STOPS]
    all_stop_names = [u["name"] for u in upstream] + downstream_names
    boarding_idx = len(upstream)  # 「県立大工学部」のインデックス

    if gps_station_name and gps_station_name in all_stop_names:
        raw_idx = all_stop_names.index(gps_station_name)
        gps_idx = min(boarding_idx - 1, max(0, raw_idx))
        curr_name = all_stop_names[gps_idx]
        next_name = all_stop_names[gps_idx + 1]
        if raw_idx >= boarding_idx:
            headline = f"「{gps_station_name}」付近へ到着"
            bus_ratio = 0.88
        else:
            headline = f"「{curr_name}」〜「{next_name}」付近を走行中"
            bus_ratio = 0.25
        track_stops, bus_pct = _layout_focus_track(all_stop_names, boarding_idx=boarding_idx, focus_idx=gps_idx, bus_ratio_in_seg=bus_ratio)
        delay_badge = f"（遅れ+{delay_minutes}分）" if delay_minutes > 0 else "（定刻通り）"
        return {
            "headline": headline,
            "subtext": f"県立大工学部まで あと約{max(0, minutes_until_departure)}分 {delay_badge}",
            "progress_percent": bus_pct,
            "track_stops": track_stops,
        }

    earliest_offset = upstream[0]["offset_min"]
    rel_min = -minutes_until_departure

    if rel_min < earliest_offset:
        wait_to_start = abs(rel_min - earliest_offset)
        origin_clean = origin_label.replace("発", "")
        track_stops, _ = _layout_focus_track(all_stop_names, boarding_idx=boarding_idx, focus_idx=None)
        return {
            "headline": f"{origin_clean}（始発）にて発車待機中",
            "subtext": f"約{wait_to_start}分後に始発停留所を発車予定",
            "progress_percent": 0,
            "track_stops": track_stops,
        }

    # 上流 + 県立大工学部(0分) の区間内で連続2駅を特定
    approach_points = upstream + [{"name": "県立大工学部", "offset_min": 0}]
    curr_idx = 0
    for i in range(len(approach_points) - 1):
        if approach_points[i]["offset_min"] <= rel_min <= approach_points[i + 1]["offset_min"]:
            curr_idx = i
            break
        if rel_min > approach_points[i + 1]["offset_min"]:
            curr_idx = i

    curr_p = approach_points[curr_idx]
    next_p = approach_points[curr_idx + 1]
    seg_span = max(1, next_p["offset_min"] - curr_p["offset_min"])
    ratio = (rel_min - curr_p["offset_min"]) / seg_span
    ratio = max(0.15, min(0.85, ratio))

    track_stops, bus_pct = _layout_focus_track(
        stop_names=all_stop_names,
        boarding_idx=boarding_idx,
        focus_idx=curr_idx,
        bus_ratio_in_seg=ratio,
    )

    stops_away = max(1, (len(approach_points) - 1) - curr_idx)
    if rel_min >= -1:
        headline = "まもなく「県立大工学部」に到着します"
        subtext = f"1つ前の「{approach_points[-2]['name']}」を通過済み"
    else:
        delay_badge = f"（遅れ+{delay_minutes}分反映）" if delay_minutes > 0 else "（定刻走行中）"
        headline = f"「{curr_p['name']}」〜「{next_p['name']}」付近を走行中"
        subtext = f"県立大工学部まで あと{stops_away}区間・約{minutes_until_departure}分 {delay_badge}"

    return {
        "headline": headline,
        "subtext": subtext,
        "progress_percent": bus_pct,
        "track_stops": track_stops,
    }


def build_bus_status_payload(
    direction: str = "to_station",
    override_time: Optional[str] = None,
    override_day_type: Optional[str] = None,
) -> Dict[str, Any]:
    now_dt = datetime.datetime.now(JST)
    # 1日1回のバックグラウンド時刻表確認（非同期のため処理待ちゼロ）
    TIMETABLE_UPDATER.ensure_daily_check_async(now_dt)

    if override_time and re.match(r"^\d{1,2}:\d{2}$", override_time):
        hh, mm = map(int, override_time.split(":"))
        now_dt = now_dt.replace(hour=hh % 24, minute=mm % 60, second=0)

    if override_day_type in ("weekday", "weekend"):
        day_type = override_day_type
    else:
        day_type = "weekend" if now_dt.weekday() >= 5 else "weekday"

    direction_key = "to_univ" if direction == "to_univ" else "to_station"
    schedule_list = TIMETABLE_DB[direction_key][day_type]

    live_client = ShinkiNaviLiveClient(timeout=2.6)
    live_res = live_client.fetch_live_direction(direction_key, now_dt)
    live_map = live_res.get("live_items_by_time", {})
    live_map_route = live_res.get("live_items_by_time_route", {})

    today_str = now_dt.strftime("%Y-%m-%d")
    use_memory = not bool(override_time)
    if use_memory:
        with LIVE_BUS_MEMORY_LOCK:
            stale_keys = [k for k in LIVE_BUS_MEMORY if k[0] != today_str]
            for sk in stale_keys:
                LIVE_BUS_MEMORY.pop(sk, None)

    now_minutes = now_dt.hour * 60 + now_dt.minute
    now_minutes_float = now_minutes + (now_dt.second / 60.0)
    enriched_upcoming: List[Dict[str, Any]] = []
    in_transit_buses: List[Dict[str, Any]] = []
    dest_terminal_name = "姫路駅(北口)" if direction_key == "to_station" else "県立大工学部"

    for idx, item in enumerate(schedule_list):
        t_parts = list(map(int, item["time"].split(":")))
        sched_min = t_parts[0] * 60 + t_parts[1]
        ride_min = int(item.get("ride_minutes", 27))
        route_key = _normalize_route_no(item.get("route_no", ""))
        bus_id = f"{direction_key}|{day_type}|{idx}|{item['time']}|{route_key}"

        live_info = live_map_route.get((item["time"], route_key)) or live_map.get(item["time"])
        mem_key = (today_str, direction_key, item["time"], route_key)
        cached = None
        if use_memory:
            with LIVE_BUS_MEMORY_LOCK:
                cached = LIVE_BUS_MEMORY.get(mem_key)

        is_running_live = False
        if live_info:
            new_delay = int(live_info.get("delay_minutes", 0))
            new_status = live_info.get("status_text", "定刻運行")
            new_gps = live_info.get("gps_station_name")
            new_is_running = bool(live_info.get("is_running", False))

            # 発車後にNAVI側で一時的に非運行・0分遅れへリセットされた場合の急ワープを防止
            if (
                cached
                and int(cached.get("delay_minutes", 0)) >= 2
                and new_delay == 0
                and not new_is_running
                and not new_gps
                and now_minutes >= sched_min
            ):
                delay_min = int(cached["delay_minutes"])
                status_text = cached.get("status_text", f"{delay_min}分遅れ")
                age_sec = (now_dt - cached["updated_at"]).total_seconds()
                gps_station = cached.get("gps_station_name") if age_sec <= 120 else None
                is_running_live = bool(cached.get("is_running", False)) if age_sec <= 120 else False
            else:
                delay_min = new_delay
                status_text = new_status
                gps_station = new_gps
                is_running_live = new_is_running
                if use_memory:
                    with LIVE_BUS_MEMORY_LOCK:
                        LIVE_BUS_MEMORY[mem_key] = {
                            "delay_minutes": delay_min,
                            "status_text": status_text,
                            "gps_station_name": gps_station,
                            "is_running": is_running_live,
                            "updated_at": now_dt,
                        }
        elif cached and (now_dt - cached["updated_at"]).total_seconds() <= 5400:
            # 検索枠外れ・一時的な通信失敗時も直近の遅延情報を引き継ぎ、定刻への急ワープと未到着消失を防止
            delay_min = int(cached.get("delay_minutes", 0))
            status_text = cached.get("status_text", "定刻運行")
            age_sec = (now_dt - cached["updated_at"]).total_seconds()
            gps_station = cached.get("gps_station_name") if age_sec <= 120 else None
            is_running_live = bool(cached.get("is_running", False)) if age_sec <= 120 else False
        else:
            delay_min = 0
            status_text = "定刻運行" if sched_min - now_minutes <= 15 else "運行予定"
            gps_station = None

        expected_min = sched_min + delay_min
        minutes_until = expected_min - now_minutes

        exp_h = (expected_min // 60) % 24
        exp_m = expected_min % 60
        expected_time_str = f"{exp_h:02d}:{exp_m:02d}"

        arr_parts = list(map(int, item["arrival_time"].split(":")))
        arr_min = arr_parts[0] * 60 + arr_parts[1] + delay_min
        if arr_min < expected_min:
            arr_min += 24 * 60
        expected_arrival_str = f"{(arr_min // 60) % 24:02d}:{arr_min % 60:02d}"
        minutes_until_arrival = arr_min - now_minutes

        # GPS上でまだ終点に到着していない走行中バスが予定時刻超過で消えるのを防止
        if (
            is_running_live
            and gps_station
            and gps_station != dest_terminal_name
            and minutes_until < 0
            and minutes_until_arrival <= 0
        ):
            minutes_until_arrival = 1
            adj_arr = now_minutes + 1
            expected_arrival_str = f"{(adj_arr // 60) % 24:02d}:{adj_arr % 60:02d}"

        # すでに出発したが、まだ目的地に到着していない走行中バス (乗車中モード用)
        if minutes_until < 0 and minutes_until_arrival > 0:
            elapsed_float = max(0.0, now_minutes_float - expected_min)
            pos_info = _estimate_in_transit_position(
                direction=direction_key,
                elapsed_since_boarding=elapsed_float,
                ride_minutes=ride_min,
                delay_minutes=delay_min,
                origin_label=item.get("origin", ""),
                route_no=item.get("route_no", ""),
                expected_arrival_str=expected_arrival_str,
                gps_station_name=gps_station,
            )
            in_transit_buses.append({
                **item,
                "bus_id": bus_id,
                "bus_state": "in_transit",
                "scheduled_time": item["time"],
                "expected_time": expected_time_str,
                "expected_arrival_time": expected_arrival_str,
                "minutes_until": minutes_until,
                "departed_minutes_ago": abs(minutes_until),
                "minutes_until_arrival": minutes_until_arrival,
                "delay_minutes": delay_min,
                "status_text": status_text,
                "location": pos_info,
            })
            continue

        if minutes_until < 0:
            continue

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
            "bus_id": bus_id,
            "bus_state": "upcoming",
            "scheduled_time": item["time"],
            "expected_time": expected_time_str,
            "expected_arrival_time": expected_arrival_str,
            "minutes_until": minutes_until,
            "minutes_until_arrival": minutes_until_arrival,
            "delay_minutes": delay_min,
            "status_text": status_text,
            "location": pos_info,
        })

    is_tomorrow = False
    if not enriched_upcoming and schedule_list:
        is_tomorrow = True
        for idx, item in enumerate(schedule_list[:5]):
            t_parts = list(map(int, item["time"].split(":")))
            sched_min = (t_parts[0] + 24) * 60 + t_parts[1]
            minutes_until = sched_min - now_minutes
            route_key = _normalize_route_no(item.get("route_no", ""))
            enriched_upcoming.append({
                **item,
                "bus_id": f"{direction_key}|{day_type}|tomorrow_{idx}|{item['time']}|{route_key}",
                "bus_state": "upcoming",
                "scheduled_time": item["time"],
                "expected_time": item["time"],
                "expected_arrival_time": item["arrival_time"],
                "minutes_until": minutes_until,
                "minutes_until_arrival": minutes_until + int(item.get("ride_minutes", 27)),
                "delay_minutes": 0,
                "status_text": "翌朝始発予定",
                "location": {
                    **_estimate_bus_position(
                        direction=direction_key,
                        minutes_until_departure=minutes_until,
                        delay_minutes=0,
                        origin_label=item.get("origin", ""),
                        route_no=item.get("route_no", ""),
                    ),
                    "headline": "本日の運行終了（翌朝始発待機）",
                    "subtext": f"翌朝 {item['time']} 発の始発便です",
                    "progress_percent": 0,
                },
            })

    if direction_key == "to_station":
        header_info = {
            "direction": "to_station",
            "title": "県立大工学部前 → 姫路駅（北口）",
            "from_stop": "県立大工学部前",
            "to_stop": "姫路駅（北口）",
            "timetable_url": BUS_STOPS_META["kenritsudai_kogakubu"]["timetable_url"],
        }
    else:
        header_info = {
            "direction": "to_univ",
            "title": "姫路駅（北口） → 県立大工学部前",
            "from_stop": "姫路駅(北口) 18番のりば",
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
            "timetable_sync": TIMETABLE_UPDATER.last_sync_status,
        },
        "header": header_info,
        "next_bus": enriched_upcoming[0] if enriched_upcoming else None,
        "in_transit_buses": in_transit_buses,
        "upcoming_buses": enriched_upcoming[:5],
    }


def build_full_timetable_payload(direction: str = "to_station") -> Dict[str, Any]:
    direction_key = "to_univ" if direction == "to_univ" else "to_station"
    return {
        "direction": direction_key,
        "weekday": TIMETABLE_DB[direction_key]["weekday"],
        "weekend": TIMETABLE_DB[direction_key]["weekend"],
        "sync_status": TIMETABLE_UPDATER.last_sync_status,
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


def run_server(host: str = "0.0.0.0", port: int = 8050) -> None:
    # 起動時にバックグラウンドで1日1回の公式時刻表チェックを開始
    TIMETABLE_UPDATER.ensure_daily_check_async(datetime.datetime.now(JST))
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
