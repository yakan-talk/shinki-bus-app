// -*- coding: utf-8 -*-
/**
 * 神姫バス 接近・時刻表 フロントエンド (県立大工学部前 ⇔ 姫路駅北口)
 * - これから乗る（乗車前）：出発済みは最新1本まで表示
 * - 乗車中・出発済：他の出発済みバスも「もっと見る」で全便確認可能＋到着までピン留め固定
 */

const AUTO_REFRESH_SECONDS = 30;
const PIN_STORAGE_PREFIX = "shinki_bus_pin_v1_";
const TRACK_MODE_STORAGE_KEY = "shinki_bus_track_mode_v1";

function loadTrackMode() {
  try {
    return localStorage.getItem(TRACK_MODE_STORAGE_KEY) === "vertical" ? "vertical" : "horizontal";
  } catch {
    return "horizontal";
  }
}

function saveTrackMode(mode) {
  try {
    localStorage.setItem(TRACK_MODE_STORAGE_KEY, mode);
  } catch {
    // ignore storage errors
  }
}

const state = {
  direction: "to_station", // "to_station" | "to_univ"
  countdown: AUTO_REFRESH_SECONDS,
  timerId: null,
  isFetching: false,
  lastPayload: null,
  selectedBusKey: null,
  viewMode: "upcoming", // "upcoming" | "in_transit"
  showAllInTransit: false,
  pinnedBusKey: null,
  trackMode: loadTrackMode(),
  timetableCache: {},
  selectedTimetableDay: "weekday",
};

const els = {
  dayTypeChip: document.getElementById("dayTypeChip"),
  liveSourceText: document.getElementById("liveSourceText"),
  updatedAtText: document.getElementById("updatedAtText"),
  autoCountdown: document.getElementById("autoCountdown"),
  refreshBtn: document.getElementById("refreshBtn"),
  locationRefreshBtn: document.getElementById("locationRefreshBtn"),
  locationToggleHead: document.getElementById("locationToggleHead"),
  routeTrackWrap: document.getElementById("routeTrackWrap"),
  routeVerticalWrap: document.getElementById("routeVerticalWrap"),

  tabToStation: document.getElementById("tabToStation"),
  tabToUniv: document.getElementById("tabToUniv"),

  modeSwitchBar: document.getElementById("modeSwitchBar"),
  btnModeUpcoming: document.getElementById("btnModeUpcoming"),
  btnModeInTransit: document.getElementById("btnModeInTransit"),
  modeUpcomingTime: document.getElementById("modeUpcomingTime"),
  modeInTransitTime: document.getElementById("modeInTransitTime"),
  pinnedReturnBar: document.getElementById("pinnedReturnBar"),
  pinnedReturnTime: document.getElementById("pinnedReturnTime"),

  heroRouteNo: document.getElementById("heroRouteNo"),
  heroRouteName: document.getElementById("heroRouteName"),
  pinToggleBtn: document.getElementById("pinToggleBtn"),
  pinBtnText: document.getElementById("pinBtnText"),
  heroDelayPill: document.getElementById("heroDelayPill"),
  countdownLabel: document.getElementById("countdownLabel"),
  countdownPrefix: document.getElementById("countdownPrefix"),
  heroMinutesUntil: document.getElementById("heroMinutesUntil"),
  countdownUnit: document.getElementById("countdownUnit"),
  heroSchedLabel: document.getElementById("heroSchedLabel"),
  heroScheduledTime: document.getElementById("heroScheduledTime"),
  heroDelayText: document.getElementById("heroDelayText"),
  heroArrivalTime: document.getElementById("heroArrivalTime"),

  locationBlock: document.getElementById("locationBlock"),
  locationBlockLabel: document.getElementById("locationBlockLabel"),
  heroLocationHeadline: document.getElementById("heroLocationHeadline"),
  heroLocationSubtext: document.getElementById("heroLocationSubtext"),
  heroProgressFill: document.getElementById("heroProgressFill"),
  heroBusPin: document.getElementById("heroBusPin"),
  stopTopLabelsLayer: document.getElementById("stopTopLabelsLayer"),
  stopDotsLayer: document.getElementById("stopDotsLayer"),
  stopLabelsLayer: document.getElementById("stopLabelsLayer"),

  boardingStopNote: document.getElementById("boardingStopNote"),
  upcomingList: document.getElementById("upcomingList"),

  toggleFullTimetableBtn: document.getElementById("toggleFullTimetableBtn"),
  timetableChevron: document.getElementById("timetableChevron"),
  fullTimetablePanel: document.getElementById("fullTimetablePanel"),
  btnDayWeekday: document.getElementById("btnDayWeekday"),
  btnDayWeekend: document.getElementById("btnDayWeekend"),
  fullTimetableGrid: document.getElementById("fullTimetableGrid"),
  officialTimetableLink: document.getElementById("officialTimetableLink"),
};

function formatRouteLabel(routeNo) {
  const str = String(routeNo || "");
  return str === "直行" ? "直行" : `${str}系統`;
}

function getBusKey(bus) {
  if (!bus) return "";
  return `${bus.bus_state || "upcoming"}:${bus.scheduled_time}`;
}

function loadPinnedKey(dir) {
  try {
    return localStorage.getItem(`${PIN_STORAGE_PREFIX}${dir}`) || null;
  } catch {
    return null;
  }
}

function savePinnedKey(dir, key) {
  try {
    if (key) {
      localStorage.setItem(`${PIN_STORAGE_PREFIX}${dir}`, key);
    } else {
      localStorage.removeItem(`${PIN_STORAGE_PREFIX}${dir}`);
    }
  } catch {
    // ignore storage errors
  }
}

async function fetchBusStatus() {
  if (state.isFetching) return;
  state.isFetching = true;
  els.refreshBtn.textContent = "更新中";
  if (els.locationRefreshBtn) els.locationRefreshBtn.disabled = true;

  try {
    const res = await fetch(`/api/bus-status?direction=${encodeURIComponent(state.direction)}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.lastPayload = data;
    renderBusStatus(data);
    state.countdown = AUTO_REFRESH_SECONDS;
    els.autoCountdown.textContent = String(state.countdown);
  } catch (err) {
    console.error("Failed to fetch bus status:", err);
  } finally {
    state.isFetching = false;
    els.refreshBtn.textContent = "更新";
    if (els.locationRefreshBtn) els.locationRefreshBtn.disabled = false;
  }
}

function renderBusStatus(data) {
  els.updatedAtText.textContent = (data.updated_at || "--:--").slice(0, 5);
  els.dayTypeChip.textContent = data.day_type_label || "平日ダイヤ";
  els.liveSourceText.textContent = data.data_source?.label || "時刻表モード";

  if (data.header?.from_stop) {
    els.boardingStopNote.textContent = `${data.header.from_stop} 発`;
  }
  if (data.header?.timetable_url) {
    els.officialTimetableLink.href = data.header.timetable_url;
  }

  const inTransitList = data.in_transit_buses || [];
  const upcomingList = data.upcoming_buses || [];
  const latestInTransit = inTransitList.length > 0 ? inTransitList[inTransitList.length - 1] : null;
  const firstUpcoming = data.next_bus || upcomingList[0] || null;
  const allBuses = [...inTransitList, ...upcomingList];

  // ピン留め中のバスが到着済みになって消えた場合は自動解除
  if (state.pinnedBusKey) {
    const pinnedExists = allBuses.some((b) => getBusKey(b) === state.pinnedBusKey);
    if (!pinnedExists) {
      // これから乗っていたバスが発車して in_transit に移った場合は自動追尾する
      const schedTime = state.pinnedBusKey.split(":").slice(1).join(":");
      const movedToTransit = inTransitList.find((b) => b.scheduled_time === schedTime);
      if (movedToTransit) {
        state.pinnedBusKey = getBusKey(movedToTransit);
        savePinnedKey(state.direction, state.pinnedBusKey);
      } else {
        state.pinnedBusKey = null;
        savePinnedKey(state.direction, null);
      }
    }
  }

  // 表示対象バスの決定（現在選択中を優先。なければピン留め → 現在のモードデフォルト）
  let activeBus = null;
  if (state.selectedBusKey) {
    activeBus = allBuses.find((b) => getBusKey(b) === state.selectedBusKey) || null;
  }
  if (!activeBus && state.pinnedBusKey) {
    activeBus = allBuses.find((b) => getBusKey(b) === state.pinnedBusKey) || null;
  }
  if (!activeBus) {
    activeBus = state.viewMode === "in_transit" && latestInTransit ? latestInTransit : (firstUpcoming || latestInTransit);
  }
  state.selectedBusKey = activeBus ? getBusKey(activeBus) : null;

  const isViewingInTransit = Boolean(activeBus && activeBus.bus_state === "in_transit");
  state.viewMode = isViewingInTransit ? "in_transit" : "upcoming";

  // 別のバスを見に行っている時に、元のピン留めバスへ戻れるショートカットを表示
  const pinnedBus = state.pinnedBusKey ? allBuses.find((b) => getBusKey(b) === state.pinnedBusKey) : null;
  if (pinnedBus && activeBus && getBusKey(pinnedBus) !== getBusKey(activeBus)) {
    els.pinnedReturnBar.classList.remove("hidden");
    els.pinnedReturnTime.textContent = pinnedBus.scheduled_time;
  } else {
    els.pinnedReturnBar.classList.add("hidden");
  }

  // 上部モード切替バー（走行中バスがある時のみ表示）
  if (latestInTransit && firstUpcoming) {
    els.modeSwitchBar.classList.remove("hidden");
    els.modeUpcomingTime.textContent = firstUpcoming.scheduled_time;
    const inTransitDisplayTime = isViewingInTransit ? activeBus.scheduled_time : latestInTransit.scheduled_time;
    els.modeInTransitTime.textContent = inTransitDisplayTime;

    els.btnModeUpcoming.classList.toggle("active", !isViewingInTransit);
    els.btnModeInTransit.classList.toggle("active", isViewingInTransit);
  } else {
    els.modeSwitchBar.classList.add("hidden");
  }

  if (!activeBus) {
    els.heroRouteNo.textContent = "--";
    els.heroRouteName.textContent = "本日の運行終了";
    els.heroMinutesUntil.textContent = "--";
    els.heroLocationHeadline.textContent = "現在運行中のバスはありません";
    els.heroLocationSubtext.textContent = "";
    els.pinToggleBtn.classList.add("hidden");
    els.upcomingList.innerHTML = "";
    return;
  }

  renderMainHeroCard(activeBus, data);
  renderBusList(inTransitList, upcomingList, activeBus);
}

function formatAnchorLabelHtml(s, isInTransit) {
  let text = String(s.label || "");
  if (text === "姫路駅(北口)") {
    text = "姫路駅<br>(北口)";
  } else if (text === "書写西住宅") {
    text = "書写<br>西住宅";
  } else if (text === "バーズタウン") {
    text = "バーズ<br>タウン";
  }
  if (s.is_boarding) {
    const tag = isInTransit ? "(発車済)" : "(のりば)";
    return `${text}<br>${tag}`;
  }
  return text;
}

function formatDestShort(dest) {
  return String(dest || "").replace(/（[^）]*経由）/g, "").trim();
}

function renderMainHeroCard(bus, data) {
  const isInTransit = bus.bus_state === "in_transit";
  const busKey = getBusKey(bus);
  const isPinned = state.pinnedBusKey === busKey;
  const destShort = state.direction === "to_station" ? "姫路駅(北口)" : "県立大工学部前";

  els.heroRouteNo.textContent = formatRouteLabel(bus.route_no);
  els.heroRouteName.textContent = `${formatDestShort(bus.destination)}行`;

  // ピン留めボタン表示（出発済バスまたは選択中バスを到着までピン留め）
  els.pinToggleBtn.classList.remove("hidden");
  els.pinToggleBtn.classList.toggle("pinned", isPinned);
  els.pinBtnText.textContent = isPinned ? "📌 ピン留め中" : "📌 ピン留め";

  const delayMin = Number(bus.delay_minutes || 0);
  if (isInTransit) {
    if (delayMin > 0) {
      els.heroDelayPill.textContent = `遅れ +${delayMin}分`;
      els.heroDelayPill.className = "status-tag delayed";
      els.heroDelayText.innerHTML = `遅れ <strong>+${delayMin}分</strong>`;
    } else {
      els.heroDelayPill.textContent = "走行中";
      els.heroDelayPill.className = "status-tag in-transit";
      els.heroDelayText.innerHTML = `遅れ <strong>+0分</strong>`;
    }
    els.countdownLabel.textContent = `${destShort} 到着まで`;
    els.countdownPrefix.textContent = "あと";
    els.heroMinutesUntil.textContent = String(Math.max(1, Number(bus.minutes_until_arrival ?? 1)));
    els.countdownUnit.textContent = "分";
    els.heroSchedLabel.innerHTML = `発車 <strong>${bus.scheduled_time}</strong>`;
    els.locationBlockLabel.textContent = "現在の走行位置";
  } else {
    if (delayMin > 0) {
      els.heroDelayPill.textContent = `遅れ +${delayMin}分`;
      els.heroDelayPill.className = "status-tag delayed";
      els.heroDelayText.innerHTML = `遅れ <strong>+${delayMin}分</strong>`;
    } else {
      els.heroDelayPill.textContent = "定刻";
      els.heroDelayPill.className = "status-tag";
      els.heroDelayText.innerHTML = `遅れ <strong>+0分</strong>`;
    }
    els.countdownLabel.textContent = "次のバスまで";
    const mins = Number(bus.minutes_until ?? 0);
    if (mins <= 0) {
      els.countdownPrefix.textContent = "";
      els.heroMinutesUntil.textContent = "まもなく";
      els.countdownUnit.textContent = "発車";
    } else {
      els.countdownPrefix.textContent = data.is_tomorrow ? "翌朝まで あと" : "あと";
      els.heroMinutesUntil.textContent = String(mins);
      els.countdownUnit.textContent = "分";
    }
    els.heroSchedLabel.innerHTML = `定刻 <strong>${bus.scheduled_time}</strong>`;
    els.locationBlockLabel.textContent = "現在の走行位置";
  }

  els.heroArrivalTime.textContent = bus.expected_arrival_time || bus.arrival_time;

  const loc = bus.location || {};
  els.heroLocationHeadline.textContent = loc.headline || "--";
  // 乗車中は上のカウントダウンと重複する到着予定・遅延サブテキストを省略してスッキリさせる
  els.heroLocationSubtext.textContent = isInTransit ? "" : (loc.subtext || "");

  const prog = Math.max(0, Math.min(100, Number(loc.progress_percent ?? 0)));
  els.heroProgressFill.style.width = `${prog}%`;
  els.heroBusPin.style.left = `${prog}%`;

  const trackStops = loc.track_stops || [];

  // 上側ラベル: 走行中の前後2駅 (is_focus) を各ドットの真上に中央揃えで表示
  const focusStops = trackStops.filter((s) => s.is_focus);
  els.stopTopLabelsLayer.innerHTML = focusStops
    .map((s) => {
      const tag = s.is_boarding ? (isInTransit ? "<br>(発車済)" : "<br>(のりば)") : "";
      return `<span class="stop-top-label-item" style="left: ${s.percent}%;">${s.label}${tag}</span>`;
    })
    .join("");
  els.stopTopLabelsLayer.style.display = focusStops.length > 0 ? "block" : "none";

  // 中段: 全駅ドット
  els.stopDotsLayer.innerHTML = trackStops
    .map(
      (s) =>
        `<span class="stop-dot ${s.is_boarding ? "boarding" : ""} ${s.is_focus ? "focus-stop" : ""}" style="left: ${s.percent}%;"></span>`
    )
    .join("");

  // 下側ラベル: 上側(is_focus)と重複しない始発・のりば・終着駅のみをドットの真下に中央揃えで表示
  els.stopLabelsLayer.innerHTML = trackStops
    .filter((s) => s.is_anchor && !s.is_focus)
    .map((s) => {
      const boardingClass = s.is_boarding ? "boarding" : "";
      const htmlLabel = formatAnchorLabelHtml(s, isInTransit);
      return `<span class="stop-label-item ${boardingClass}" style="left: ${s.percent}%;">${htmlLabel}</span>`;
    })
    .join("");

  const isVert = state.trackMode === "vertical";
  if (els.locationToggleHead) {
    els.locationToggleHead.classList.toggle("expanded", isVert);
    els.locationToggleHead.setAttribute("aria-expanded", String(isVert));
  }
  if (els.routeTrackWrap && els.routeVerticalWrap) {
    els.routeTrackWrap.classList.toggle("hidden", isVert);
    els.routeVerticalWrap.classList.toggle("hidden", !isVert);
    if (isVert) {
      renderVerticalTrack(bus, trackStops, prog, isInTransit);
    }
  }
}

function parseHHMMToMinutes(hhmm) {
  if (!hhmm || !hhmm.includes(":")) return null;
  const [h, m] = hhmm.split(":").map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}

function formatMinutesToHHMM(totalMin) {
  const m = ((Math.round(totalMin) % 1440) + 1440) % 1440;
  const hh = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(m % 60).padStart(2, "0");
  return `${hh}:${mm}`;
}

function computeStopTimesList(trackStops, boardingIdx, depMin, arrMin) {
  const n = trackStops.length;
  return trackStops.map((_, idx) => {
    if (depMin === null) return "--:--";
    if (idx < boardingIdx) {
      return formatMinutesToHHMM(depMin - (boardingIdx - idx));
    }
    if (arrMin !== null && n - 1 > boardingIdx) {
      const dur = arrMin >= depMin ? arrMin - depMin : arrMin + 1440 - depMin;
      const ratio = (idx - boardingIdx) / (n - 1 - boardingIdx);
      return formatMinutesToHHMM(depMin + dur * ratio);
    }
    return formatMinutesToHHMM(depMin + (idx - boardingIdx));
  });
}

function renderVerticalTrack(bus, trackStops, prog, isInTransit) {
  const n = trackStops.length;
  if (n === 0) {
    els.routeVerticalWrap.innerHTML = "";
    return;
  }

  const delayMin = Number(bus.delay_minutes || 0);
  const schedDepMin = parseHHMMToMinutes(bus.scheduled_time);
  const schedArrMin = parseHHMMToMinutes(bus.arrival_time);
  const expDepMin =
    parseHHMMToMinutes(bus.expected_time) ??
    (schedDepMin !== null ? schedDepMin + delayMin : null);
  const expArrMin =
    parseHHMMToMinutes(bus.expected_arrival_time) ??
    (schedArrMin !== null ? schedArrMin + delayMin : null);

  let boardingIdx = trackStops.findIndex((s) => s.is_boarding);
  if (boardingIdx < 0) boardingIdx = 0;

  // 定刻ベースと遅れ込みベースの各駅通過時刻を算出
  const schedStopTimes = computeStopTimesList(trackStops, boardingIdx, schedDepMin, schedArrMin);
  const expStopTimes = computeStopTimesList(trackStops, boardingIdx, expDepMin, expArrMin);

  // 縦バー上のバス位置 (0% 〜 100%)
  const focusIndices = [];
  trackStops.forEach((s, i) => {
    if (s.is_focus) focusIndices.push(i);
  });

  let busFloatIdx = 0;
  if (focusIndices.length >= 2) {
    const f0 = focusIndices[0];
    const f1 = focusIndices[focusIndices.length - 1];
    const p0 = Number(trackStops[f0].percent || 0);
    const p1 = Number(trackStops[f1].percent || 100);
    const ratio = p1 > p0 ? Math.max(0, Math.min(1, (prog - p0) / (p1 - p0))) : 0.5;
    busFloatIdx = f0 + ratio * (f1 - f0);
  } else if (n > 1) {
    busFloatIdx = (prog / 100) * (n - 1);
  }

  const busTopPct = n > 1 ? (busFloatIdx / (n - 1)) * 100 : 0;
  const rowHeightPx = 32;
  const busTopPx = 16 + busFloatIdx * rowHeightPx;

  const rowsHtml = trackStops
    .map((s, i) => {
      const tag = s.is_boarding ? (isInTransit ? " (発車済)" : " (のりば)") : "";
      const rowCls = `${s.is_boarding ? "is-boarding" : ""} ${s.is_focus ? "is-focus" : ""}`;
      const dotCls = `${s.is_boarding ? "boarding" : ""} ${s.is_focus ? "focus-stop" : ""}`;
      const timeHtml =
        delayMin > 0
          ? `<span class="v-stop-time has-delay">
               <span class="v-time-expected">${expStopTimes[i]}</span>
               <span class="v-time-scheduled-strike">${schedStopTimes[i]}</span>
             </span>`
          : `<span class="v-stop-time">${schedStopTimes[i]}</span>`;
      return `
        <div class="v-stop-row ${rowCls}">
          <span class="v-stop-dot ${dotCls}"></span>
          ${timeHtml}
          <span class="v-stop-name">${s.label}${tag}</span>
        </div>
      `;
    })
    .join("");

  els.routeVerticalWrap.innerHTML = `
    <div class="v-track-container">
      <div class="v-track-line">
        <div class="v-track-fill" style="height: ${busTopPct.toFixed(2)}%;"></div>
      </div>
      <div class="v-bus-marker" style="top: ${busTopPx.toFixed(1)}px;" title="現在位置">
        <svg class="bus-svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M4 16c0 .88.39 1.67 1 2.22V20c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h8v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1.78c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z"/>
        </svg>
      </div>
      ${rowsHtml}
    </div>
  `;
}

function renderBusList(inTransitList, upcomingList, activeBus) {
  const activeKey = getBusKey(activeBus);
  const isInTransitMode = state.viewMode === "in_transit";

  // 時系列順（古い発車 → 新しい発車）のまま並べる
  let visibleInTransit = [];
  let hiddenInTransitCount = 0;

  if (!isInTransitMode) {
    // これから乗るモード: 直近に出発した最新の1本のみ
    visibleInTransit = inTransitList.slice(-1);
  } else {
    // 乗車中・出発済モード: 時系列順で表示（3本以上あるときは「もっと見る」で古い便も展開）
    if (state.showAllInTransit || inTransitList.length <= 2) {
      visibleInTransit = inTransitList;
    } else {
      visibleInTransit = inTransitList.slice(-2);
      hiddenInTransitCount = inTransitList.length - 2;
    }
  }

  const displayBuses = [...visibleInTransit, ...upcomingList];

  let html = displayBuses
    .map((bus) => {
      const key = getBusKey(bus);
      const isSelected = key === activeKey;
      const isPinned = key === state.pinnedBusKey;
      const isInTransit = bus.bus_state === "in_transit";
      const bDelay = Number(bus.delay_minutes || 0);
      const delayStr = bDelay > 0 ? `遅れ +${bDelay}分` : "定刻";
      const locText = bus.location?.headline || "";

      const rightBadge = isInTransit
        ? `<span class="bus-row-wait in-transit-badge">走行中 あと${bus.minutes_until_arrival}分</span>`
        : `<span class="bus-row-wait">あと ${bus.minutes_until}分</span>`;

      const pinMark = isPinned ? " 📌" : "";
      const timeLabel = isInTransit ? `${bus.scheduled_time}発 (出発済)${pinMark}` : `${bus.scheduled_time}発${pinMark}`;

      return `
        <div class="bus-row ${isSelected ? "selected" : ""} ${isInTransit ? "in-transit-row" : ""}" data-bus-key="${key}">
          <div class="bus-row-top">
            <div>
              <span class="bus-row-time">${timeLabel}</span>
              <span class="bus-row-arr">→ ${bus.expected_arrival_time || bus.arrival_time}着</span>
            </div>
            ${rightBadge}
          </div>
          <div class="bus-row-mid">
            <span class="mini-route">${formatRouteLabel(bus.route_no)}</span>
            <span>${formatDestShort(bus.destination)}行</span>
          </div>
          <div class="bus-row-sub">
            <span>${locText}</span>
            <span>${delayStr}</span>
          </div>
        </div>
      `;
    })
    .join("");

  if (isInTransitMode && inTransitList.length > 2) {
    const toggleText = state.showAllInTransit
      ? "古い出発済を折りたたむ"
      : `さらに前の出発済を見る（他 ${hiddenInTransitCount}本）`;
    html =
      `<button type="button" class="show-more-btn" id="toggleInTransitMoreBtn">${toggleText}</button>` + html;
  }

  els.upcomingList.innerHTML = html;

  const moreBtn = document.getElementById("toggleInTransitMoreBtn");
  if (moreBtn) {
    moreBtn.addEventListener("click", () => {
      state.showAllInTransit = !state.showAllInTransit;
      renderBusStatus(state.lastPayload);
    });
  }

  els.upcomingList.querySelectorAll(".bus-row").forEach((row) => {
    row.addEventListener("click", () => {
      const k = row.getAttribute("data-bus-key");
      if (k && state.lastPayload) {
        state.selectedBusKey = k;
        state.viewMode = k.startsWith("in_transit:") ? "in_transit" : "upcoming";
        renderBusStatus(state.lastPayload);
      }
    });
  });
}

function setDirection(newDir) {
  if (newDir !== "to_station" && newDir !== "to_univ") return;
  state.direction = newDir;
  state.selectedBusKey = null;
  state.viewMode = "upcoming";
  state.showAllInTransit = false;
  state.pinnedBusKey = loadPinnedKey(newDir);

  const isToStation = newDir === "to_station";
  els.tabToStation.classList.toggle("active", isToStation);
  els.tabToStation.setAttribute("aria-selected", String(isToStation));
  els.tabToUniv.classList.toggle("active", !isToStation);
  els.tabToUniv.setAttribute("aria-selected", String(!isToStation));

  fetchBusStatus();
  if (!els.fullTimetablePanel.classList.contains("hidden")) {
    loadAndRenderFullTimetable();
  }
}

async function loadAndRenderFullTimetable() {
  const dir = state.direction;
  if (!state.timetableCache[dir]) {
    try {
      const res = await fetch(`/api/timetable?direction=${encodeURIComponent(dir)}`);
      if (res.ok) {
        state.timetableCache[dir] = await res.json();
      }
    } catch (e) {
      console.error(e);
    }
  }
  const ttData = state.timetableCache[dir];
  if (!ttData) return;

  const list = ttData[state.selectedTimetableDay] || [];
  const byHour = {};
  for (const item of list) {
    const [hh, mm] = item.time.split(":");
    if (!byHour[hh]) byHour[hh] = [];
    byHour[hh].push({ mm, route_no: item.route_no });
  }

  const hours = Object.keys(byHour).sort((a, b) => Number(a) - Number(b));
  els.fullTimetableGrid.innerHTML = hours
    .map((hh) => {
      const mins = byHour[hh]
        .map((e) => `<span class="tt-min-item"><small>[${e.route_no}]</small>${e.mm}</span>`)
        .join("");
      return `
        <div class="tt-row">
          <div class="tt-hour">${hh}時</div>
          <div class="tt-mins">${mins}</div>
        </div>
      `;
    })
    .join("");
}

function startAutoRefreshLoop() {
  if (state.timerId) clearInterval(state.timerId);
  state.timerId = setInterval(() => {
    state.countdown -= 1;
    if (state.countdown <= 0) {
      fetchBusStatus();
    } else {
      els.autoCountdown.textContent = String(state.countdown);
    }
  }, 1000);
}

function toggleTrackMode(forceMode, options = {}) {
  const prevMode = state.trackMode;
  const nextMode =
    typeof forceMode === "string"
      ? forceMode
      : state.trackMode === "vertical"
      ? "horizontal"
      : "vertical";

  if (prevMode === nextMode && !options.scrollToBus) return;

  state.trackMode = nextMode;
  saveTrackMode(nextMode);
  if (state.lastPayload) renderBusStatus(state.lastPayload);

  // 縦から横に戻したとき: スクロール位置を自然に整える
  if (prevMode === "vertical" && nextMode === "horizontal") {
    const locEl = els.locationBlock || els.locationToggleHead;
    if (locEl) {
      const rect = locEl.getBoundingClientRect();
      // 上部が見切れている、または画面外になっている場合は自然に一番上（ヘッダー下）にスムーズスクロール
      if (rect.top < 20 || rect.bottom > window.innerHeight) {
        locEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }

  // 縦表示に展開したとき: 横のバスアイコンを押した、または指定があれば縦のバスアイコン位置へスクロール
  if (nextMode === "vertical" && options.scrollToBus) {
    requestAnimationFrame(() => {
      const vBus = document.querySelector(".v-bus-marker");
      if (vBus) {
        vBus.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }
}

els.refreshBtn.addEventListener("click", () => fetchBusStatus());
if (els.locationRefreshBtn) {
  els.locationRefreshBtn.addEventListener("click", () => fetchBusStatus());
}
if (els.locationToggleHead) {
  els.locationToggleHead.addEventListener("click", () => toggleTrackMode());
}
if (els.heroBusPin) {
  els.heroBusPin.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleTrackMode("vertical", { scrollToBus: true });
  });
}
if (els.routeTrackWrap) {
  els.routeTrackWrap.addEventListener("click", (e) => {
    // バスアイコン以外のトラックタップ
    toggleTrackMode("vertical", { scrollToBus: true });
  });
}
if (els.routeVerticalWrap) {
  els.routeVerticalWrap.addEventListener("click", () => toggleTrackMode("horizontal"));
}
els.tabToStation.addEventListener("click", () => setDirection("to_station"));
els.tabToUniv.addEventListener("click", () => setDirection("to_univ"));

els.pinToggleBtn.addEventListener("click", () => {
  if (!state.selectedBusKey) return;
  if (state.pinnedBusKey === state.selectedBusKey) {
    state.pinnedBusKey = null;
  } else {
    state.pinnedBusKey = state.selectedBusKey;
  }
  savePinnedKey(state.direction, state.pinnedBusKey);
  if (state.lastPayload) {
    renderBusStatus(state.lastPayload);
  }
});

els.btnModeUpcoming.addEventListener("click", () => {
  if (!state.lastPayload) return;
  state.viewMode = "upcoming";
  const firstUp = state.lastPayload.next_bus || (state.lastPayload.upcoming_buses || [])[0];
  if (firstUp) {
    state.selectedBusKey = getBusKey(firstUp);
    renderBusStatus(state.lastPayload);
  }
});

els.pinnedReturnBar.addEventListener("click", () => {
  if (!state.lastPayload || !state.pinnedBusKey) return;
  state.selectedBusKey = state.pinnedBusKey;
  state.viewMode = state.pinnedBusKey.startsWith("in_transit:") ? "in_transit" : "upcoming";
  renderBusStatus(state.lastPayload);
});

els.btnModeInTransit.addEventListener("click", () => {
  if (!state.lastPayload) return;
  state.viewMode = "in_transit";
  const inTr = state.lastPayload.in_transit_buses || [];
  if (inTr.length > 0) {
    state.selectedBusKey = getBusKey(inTr[inTr.length - 1]);
    renderBusStatus(state.lastPayload);
  }
});

els.toggleFullTimetableBtn.addEventListener("click", () => {
  const isHidden = els.fullTimetablePanel.classList.toggle("hidden");
  els.toggleFullTimetableBtn.setAttribute("aria-expanded", String(!isHidden));
  els.timetableChevron.textContent = isHidden ? "▼" : "▲";
  if (!isHidden) {
    loadAndRenderFullTimetable();
  }
});

els.btnDayWeekday.addEventListener("click", () => {
  state.selectedTimetableDay = "weekday";
  els.btnDayWeekday.classList.add("active");
  els.btnDayWeekend.classList.remove("active");
  loadAndRenderFullTimetable();
});

els.btnDayWeekend.addEventListener("click", () => {
  state.selectedTimetableDay = "weekend";
  els.btnDayWeekend.classList.add("active");
  els.btnDayWeekday.classList.remove("active");
  loadAndRenderFullTimetable();
});

state.pinnedBusKey = loadPinnedKey(state.direction);
fetchBusStatus();
startAutoRefreshLoop();
