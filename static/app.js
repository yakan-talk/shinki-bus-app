// -*- coding: utf-8 -*-
/**
 * 神姫バス 接近・時刻表 フロントエンド (県立大工学部前 ⇔ 姫路駅北口)
 */

const AUTO_REFRESH_SECONDS = 30;

const state = {
  direction: "to_station", // "to_station" | "to_univ"
  countdown: AUTO_REFRESH_SECONDS,
  timerId: null,
  isFetching: false,
  timetableCache: {},
  selectedTimetableDay: "weekday",
};

const els = {
  dayTypeChip: document.getElementById("dayTypeChip"),
  liveSourceText: document.getElementById("liveSourceText"),
  updatedAtText: document.getElementById("updatedAtText"),
  autoCountdown: document.getElementById("autoCountdown"),
  refreshBtn: document.getElementById("refreshBtn"),

  tabToStation: document.getElementById("tabToStation"),
  tabToUniv: document.getElementById("tabToUniv"),

  heroRouteNo: document.getElementById("heroRouteNo"),
  heroRouteName: document.getElementById("heroRouteName"),
  heroDelayPill: document.getElementById("heroDelayPill"),
  countdownPrefix: document.getElementById("countdownPrefix"),
  heroMinutesUntil: document.getElementById("heroMinutesUntil"),
  countdownUnit: document.getElementById("countdownUnit"),
  heroScheduledTime: document.getElementById("heroScheduledTime"),
  heroDelayText: document.getElementById("heroDelayText"),
  heroArrivalTime: document.getElementById("heroArrivalTime"),

  heroLocationHeadline: document.getElementById("heroLocationHeadline"),
  heroLocationSubtext: document.getElementById("heroLocationSubtext"),
  heroProgressFill: document.getElementById("heroProgressFill"),
  heroBusPin: document.getElementById("heroBusPin"),
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

async function fetchBusStatus() {
  if (state.isFetching) return;
  state.isFetching = true;
  els.refreshBtn.textContent = "更新中";

  try {
    const res = await fetch(`/api/bus-status?direction=${encodeURIComponent(state.direction)}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderBusStatus(data);
    state.countdown = AUTO_REFRESH_SECONDS;
    els.autoCountdown.textContent = String(state.countdown);
  } catch (err) {
    console.error("Failed to fetch bus status:", err);
  } finally {
    state.isFetching = false;
    els.refreshBtn.textContent = "更新";
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

  const next = data.next_bus;
  if (!next) {
    els.heroRouteNo.textContent = "--";
    els.heroRouteName.textContent = "本日の運行終了";
    els.heroMinutesUntil.textContent = "--";
    els.heroLocationHeadline.textContent = "現在運行中のバスはありません";
    els.heroLocationSubtext.textContent = "";
    els.upcomingList.innerHTML = "";
    return;
  }

  els.heroRouteNo.textContent = formatRouteLabel(next.route_no);
  els.heroRouteName.textContent = `${next.destination}行`;

  const delayMin = Number(next.delay_minutes || 0);
  if (delayMin > 0) {
    els.heroDelayPill.textContent = `遅れ +${delayMin}分`;
    els.heroDelayPill.className = "status-tag delayed";
    els.heroDelayText.innerHTML = `遅れ <strong>+${delayMin}分</strong> (見込 ${next.expected_time})`;
  } else {
    els.heroDelayPill.textContent = "定刻運行";
    els.heroDelayPill.className = "status-tag";
    els.heroDelayText.innerHTML = `遅れ <strong>+0分</strong>`;
  }

  const mins = Number(next.minutes_until ?? 0);
  if (mins <= 0) {
    els.countdownPrefix.textContent = "";
    els.heroMinutesUntil.textContent = "まもなく";
    els.countdownUnit.textContent = "発車";
  } else {
    els.countdownPrefix.textContent = data.is_tomorrow ? "翌朝まで あと" : "あと";
    els.heroMinutesUntil.textContent = String(mins);
    els.countdownUnit.textContent = "分";
  }

  els.heroScheduledTime.textContent = next.scheduled_time;
  els.heroArrivalTime.textContent = next.expected_arrival_time || next.arrival_time;

  const loc = next.location || {};
  els.heroLocationHeadline.textContent = loc.headline || "--";
  els.heroLocationSubtext.textContent = loc.subtext || "";

  const prog = Math.max(0, Math.min(100, Number(loc.progress_percent ?? 0)));
  els.heroProgressFill.style.width = `${prog}%`;
  els.heroBusPin.style.left = `${prog}%`;

  const trackStops = loc.track_stops || [];
  els.stopDotsLayer.innerHTML = trackStops
    .map(
      (s) =>
        `<span class="stop-dot ${s.is_boarding ? "boarding" : ""}" style="left: ${s.percent}%;"></span>`
    )
    .join("");

  els.stopLabelsLayer.innerHTML = trackStops
    .filter((s) => s.show_label !== false)
    .map((s) => {
      let alignClass = "";
      if (s.percent <= 5) alignClass = "align-left";
      else if (s.percent >= 95) alignClass = "align-right";
      const boardingClass = s.is_boarding ? "boarding" : "";
      const tag = s.is_boarding ? "<br>(のりば)" : "";
      return `<span class="stop-label-item ${alignClass} ${boardingClass}" style="left: ${s.percent}%;">${s.label}${tag}</span>`;
    })
    .join("");

  const upcoming = data.upcoming_buses || [];
  els.upcomingList.innerHTML = upcoming
    .map((bus) => {
      const bDelay = Number(bus.delay_minutes || 0);
      const delayStr = bDelay > 0 ? `遅れ +${bDelay}分` : "遅れなし";
      const locText = bus.location?.headline || "";

      return `
        <div class="bus-row">
          <div class="bus-row-top">
            <div>
              <span class="bus-row-time">${bus.scheduled_time}発</span>
              <span class="bus-row-arr">→ ${bus.expected_arrival_time || bus.arrival_time}着</span>
            </div>
            <span class="bus-row-wait">あと ${bus.minutes_until}分</span>
          </div>
          <div class="bus-row-mid">
            <span class="mini-route">${formatRouteLabel(bus.route_no)}</span>
            <span>${bus.destination}行</span>
          </div>
          <div class="bus-row-sub">
            <span>${locText}</span>
            <span>${delayStr}</span>
          </div>
        </div>
      `;
    })
    .join("");
}

function setDirection(newDir) {
  if (newDir !== "to_station" && newDir !== "to_univ") return;
  state.direction = newDir;

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

els.refreshBtn.addEventListener("click", () => fetchBusStatus());
els.tabToStation.addEventListener("click", () => setDirection("to_station"));
els.tabToUniv.addEventListener("click", () => setDirection("to_univ"));

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

fetchBusStatus();
startAutoRefreshLoop();
