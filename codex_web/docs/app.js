const DATA_ROOT = "data";
const REPORT_ORDER = ["investor_flow", "ipo", "krx_alert", "us_market", "nxt_market", "liquidity"];

let appIndex = null;
let currentDate = null;
let currentPayloads = {};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  const precision = Number.isInteger(digits) ? Math.min(Math.max(digits, 0), 20) : 0;
  return number.toLocaleString("ko-KR", {
    maximumFractionDigits: precision,
    minimumFractionDigits: precision,
  });
}

function formatEok(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${formatNumber(Number(value) / 100000000, digits)}억`;
}

function formatJoFromEok(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${formatNumber(Number(value) / 10000, 1)}조`;
}

function formatJoFromMillion(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${formatNumber(Number(value) / 1000000, 1)}조`;
}

function formatPlainPct(value, digits = 1) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return `${number.toFixed(digits)}%`;
}

function formatPct(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function signedClass(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return "";
  if (number > 0) return "positive";
  if (number < 0) return "negative";
  return "";
}

async function fetchJson(path) {
  const response = await fetch(`${path}?v=${Date.now()}`);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function availableDates() {
  return appIndex?.dates?.map((item) => item.date) || [];
}

function sortedDates() {
  return availableDates().slice().sort();
}

function latestDateOnOrBefore(dateStr) {
  const candidates = sortedDates().filter((date) => date <= dateStr);
  return candidates.at(-1) || null;
}

function previousAvailableDate(dateStr) {
  const candidates = sortedDates().filter((date) => date < dateStr);
  return candidates.at(-1) || null;
}

function nextAvailableDate(dateStr) {
  const candidates = sortedDates().filter((date) => date > dateStr);
  return candidates[0] || null;
}

function kstNowParts() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const hour = Number(values.hour === "24" ? "0" : values.hour);
  return {
    date: `${values.year}-${values.month}-${values.day}`,
    hour,
  };
}

function preferredCurrentDate() {
  const now = kstNowParts();
  if (now.hour < 6) {
    return previousAvailableDate(now.date) || latestDateOnOrBefore(now.date) || appIndex?.latest_date || now.date;
  }
  const [year, month, day] = now.date.split("-").map(Number);
  const dayOfWeek = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
  return availableDates().includes(now.date) || isWeekday
    ? now.date
    : latestDateOnOrBefore(now.date) || appIndex?.latest_date || now.date;
}

function weekdayEn(dateStr) {
  if (!dateStr) return "-";
  const [year, month, day] = dateStr.split("-").map(Number);
  if (!year || !month || !day) return "-";
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-US", {
    weekday: "long",
    timeZone: "UTC",
  });
}

function dateWithWeekday(dateStr) {
  return dateStr ? `${dateStr} ${weekdayEn(dateStr)}` : "-";
}

function shiftDateString(dateStr, days) {
  if (!dateStr) return null;
  const [year, month, day] = dateStr.split("-").map(Number);
  if (!year || !month || !day) return null;
  const date = new Date(Date.UTC(year, month - 1, day + days));
  return date.toISOString().slice(0, 10);
}

function selectedDay() {
  return appIndex?.dates?.find((item) => item.date === currentDate);
}

async function loadReport(name) {
  try {
    return await fetchJson(`${DATA_ROOT}/${currentDate}/${name}.json`);
  } catch (error) {
    return { report: name, status: "missing", data: { error: error.message }, summary: {} };
  }
}

async function loadCurrentPayloads() {
  const day = selectedDay();
  const names = day ? REPORT_ORDER.filter((name) => day.reports?.[name]) : REPORT_ORDER;
  const entries = await Promise.all(names.map(async (name) => [name, await loadReport(name)]));
  currentPayloads = Object.fromEntries(entries);
}

async function loadWorkflowStatus() {
  try {
    return await fetchJson(`${DATA_ROOT}/workflow_status.json`);
  } catch (error) {
    return null;
  }
}

function globalMemoKey() {
  return "krxmarket:memo:global";
}

function dailyMemoKey() {
  return `krxmarket:memo:daily:${currentDate || "none"}`;
}

function loadMemo() {
  $("globalMemoBox").value = localStorage.getItem(globalMemoKey()) || "";
  $("dailyMemoBox").value = localStorage.getItem(dailyMemoKey()) || "";
  $("globalNoteStatus").textContent = "브라우저에 저장";
  $("dailyNoteStatus").textContent = currentDate ? `${currentDate} 저장` : "선택일에 저장";
}

function showSavedStatus(id, idleText) {
  $(id).textContent = "저장됨";
  window.clearTimeout(showSavedStatus[id]);
  showSavedStatus[id] = window.setTimeout(() => {
    $(id).textContent = idleText;
  }, 1200);
}

function saveGlobalMemo() {
  localStorage.setItem(globalMemoKey(), $("globalMemoBox").value);
  showSavedStatus("globalNoteStatus", "브라우저에 저장");
}

function saveDailyMemo() {
  localStorage.setItem(dailyMemoKey(), $("dailyMemoBox").value);
  showSavedStatus("dailyNoteStatus", currentDate ? `${currentDate} 저장` : "선택일에 저장");
}

function renderWorkflowAlert(status) {
  const target = $("workflowAlert");
  if (!target) return;
  if (!status) {
    target.className = "workflowAlert";
    target.textContent = "Workflow 상태: 아직 알림 데이터 없음";
    return;
  }
  const generatedAt = status.generated_at ? ` · ${status.generated_at}` : "";
  if (status.failed) {
    target.className = "workflowAlert fail";
    target.textContent = `⚠️ Workflow 실패: ${status.message || "데이터 갱신 실패"}${generatedAt}`;
    return;
  }
  target.className = "workflowAlert ok";
  target.textContent = `Workflow 정상${generatedAt}`;
}

function metric(label, value, caption = "", valueClass = "") {
  const spanClass = valueClass ? ` class="${escapeHtml(valueClass)}"` : "";
  return `
    <article class="metric">
      <strong>${escapeHtml(label)}</strong>
      <span${spanClass}>${escapeHtml(value)}</span>
      <small>${escapeHtml(caption)}</small>
    </article>
  `;
}

function miniList(title, rows, formatter) {
  const body = rows?.length
    ? rows.slice(0, 5).map(formatter).join("")
    : `<div class="miniItem"><span class="muted">데이터 없음</span><span></span></div>`;
  return `
    <article class="miniList">
      <h3>${escapeHtml(title)}</h3>
      ${body}
    </article>
  `;
}

function miniItem(left, right, cls = "") {
  return `<div class="miniItem"><span>${escapeHtml(left)}</span><span class="${cls}">${escapeHtml(right)}</span></div>`;
}

function tablePanel(title, rows, columns, subtitle = "") {
  if (!rows || !rows.length) {
    return `
      <section class="panel">
        <div class="panelHeader"><h3>${escapeHtml(title)}</h3><small>${escapeHtml(subtitle)}</small></div>
        <div class="empty">데이터 없음</div>
      </section>
    `;
  }
  const header = columns.map((col) => `<th class="${col.numeric ? "num" : ""}">${escapeHtml(col.label)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((col) => {
          const raw = col.value ? col.value(row) : row[col.key];
          const value = col.format ? col.format(raw, row) : raw;
          const cls = [col.numeric ? "num" : "", col.className ? col.className(raw, row) : ""].join(" ");
          return `<td class="${cls}">${col.html ? value ?? "-" : escapeHtml(value ?? "-")}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `
    <section class="panel">
      <div class="panelHeader"><h3>${escapeHtml(title)}</h3><small>${escapeHtml(subtitle)}</small></div>
      <div class="tableWrap">
        <table>
          <thead><tr>${header}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>
  `;
}

function latestRowOnOrBefore(rows, dateKey, dateStr) {
  if (!rows?.length) return null;
  const candidates = rows.filter((row) => !dateStr || !row[dateKey] || row[dateKey] <= dateStr);
  return (candidates.length ? candidates : rows).at(-1);
}

function asNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function asFiniteValue(value) {
  if (value === null || value === undefined || value === "") return NaN;
  const number = Number(value);
  return Number.isFinite(number) ? number : NaN;
}

function sortByAvgTradeValueDesc(rows) {
  return (rows || []).slice().sort((a, b) => asNumber(b.avg_trade_value_5d, 0) - asNumber(a.avg_trade_value_5d, 0));
}

function tradeTotalEok(row, market) {
  if (!row) return null;
  const krx = asNumber(row[`${market}_Trade`], 0);
  const nxt = asNumber(row[`NXT_${market}_Trade`], 0);
  const total = asNumber(row[`${market}_Trade_Total`], NaN);
  return Number.isFinite(total) && total >= krx + nxt ? total : krx + nxt;
}

function shortDate(dateStr) {
  return String(dateStr || "").slice(5);
}

function candleCell(row) {
  const open = asNumber(row.Open, NaN);
  const high = asNumber(row.High, NaN);
  const low = asNumber(row.Low, NaN);
  const close = asNumber(row.Close, NaN);
  if (![open, high, low, close].every(Number.isFinite) || high <= low) return "-";
  const y = (price) => 8 + ((high - price) / (high - low)) * 38;
  const color = close >= open ? "var(--red)" : "var(--blue)";
  const bodyY = Math.min(y(open), y(close));
  const bodyH = Math.max(Math.abs(y(open) - y(close)), 3);
  return `
    <div class="candleCell candleOnly">
      <svg class="miniCandle" viewBox="0 0 54 54" aria-hidden="true">
        <line x1="27" x2="27" y1="${y(high).toFixed(1)}" y2="${y(low).toFixed(1)}" stroke="${color}" stroke-width="2" />
        <rect x="20" y="${bodyY.toFixed(1)}" width="14" height="${bodyH.toFixed(1)}" rx="1.5" fill="${color}" />
      </svg>
    </div>
  `;
}

function chartShell(title, subtitle, body) {
  return `
    <section class="panel chartPanel">
      <div class="panelHeader"><h3>${escapeHtml(title)}</h3><small>${escapeHtml(subtitle)}</small></div>
      ${body || `<div class="empty">데이터 없음</div>`}
    </section>
  `;
}

function tradeBarsSvg(rows, options = {}) {
  const data = (rows || []).slice(-24);
  if (!data.length) return "";
  const width = 940;
  const height = options.height || 330;
  const margin = { left: 52, right: 32, top: 26, bottom: 58 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const maxTrade = Math.max(
    1,
    ...data.flatMap((row) => [tradeTotalEok(row, "KOSPI") || 0, tradeTotalEok(row, "KOSDAQ") || 0])
  );
  const y = (value) => margin.top + plotH - (value / (maxTrade * 1.18)) * plotH;
  const groupW = plotW / data.length;
  const barW = Math.max(5, Math.min(13, groupW * 0.24));
  const colors = {
    kospiKrx: "#64b5f6",
    kospiNxt: "#1976d2",
    kosdaqKrx: "#81c784",
    kosdaqNxt: "#2e7d32",
  };
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const value = maxTrade * ratio;
      const yy = y(value);
      return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${yy}" y2="${yy}" class="gridLine" />
        <text x="${margin.left - 10}" y="${yy + 4}" class="axisText" text-anchor="end">${formatNumber(value / 10000, 1)}조</text>`;
    })
    .join("");

  function rect(x, value, bottom, color) {
    const safeValue = Math.max(0, asNumber(value, 0));
    const safeBottom = Math.max(0, asNumber(bottom, 0));
    if (!safeValue) return "";
    const yTop = y(safeBottom + safeValue);
    const yBottom = y(safeBottom);
    return `<rect x="${x}" y="${yTop}" width="${barW}" height="${Math.max(yBottom - yTop, 1)}" fill="${color}" rx="2" />`;
  }

  const bars = data
    .map((row, index) => {
      const center = margin.left + groupW * index + groupW / 2;
      const kospiX = center - barW - 2;
      const kosdaqX = center + 2;
      const kospiKrx = asNumber(row.KOSPI_Trade, 0);
      const kospiNxt = asNumber(row.NXT_KOSPI_Trade, 0);
      const kosdaqKrx = asNumber(row.KOSDAQ_Trade, 0);
      const kosdaqNxt = asNumber(row.NXT_KOSDAQ_Trade, 0);
      const label = index % Math.ceil(data.length / 8) === 0 || index === data.length - 1
        ? `<text x="${center}" y="${height - 30}" class="axisText" text-anchor="middle">${shortDate(row.Date)}</text>`
        : "";
      return `
        ${rect(kospiX, kospiKrx, 0, colors.kospiKrx)}
        ${rect(kospiX, kospiNxt, kospiKrx, colors.kospiNxt)}
        ${rect(kosdaqX, kosdaqKrx, 0, colors.kosdaqKrx)}
        ${rect(kosdaqX, kosdaqNxt, kosdaqKrx, colors.kosdaqNxt)}
        ${label}
      `;
    })
    .join("");

  const last = data.at(-1);
  const lastCenter = margin.left + groupW * (data.length - 1) + groupW / 2;
  const labels = last
    ? `
      <text x="${lastCenter - barW - 4}" y="${y(tradeTotalEok(last, "KOSPI") || 0) - 8}" class="chartValue" text-anchor="middle">${formatJoFromEok(tradeTotalEok(last, "KOSPI"))}</text>
      <text x="${lastCenter + barW + 8}" y="${y(tradeTotalEok(last, "KOSDAQ") || 0) - 8}" class="chartValue" text-anchor="middle">${formatJoFromEok(tradeTotalEok(last, "KOSDAQ"))}</text>
    `
    : "";

  return `
    <svg class="chartSvg" viewBox="0 0 ${width} ${height}" role="img" aria-label="KRX and NXT trade value chart">
      ${grid}
      ${bars}
      ${labels}
      <line x1="${margin.left}" x2="${width - margin.right}" y1="${margin.top + plotH}" y2="${margin.top + plotH}" class="axisLine" />
      <g class="legend">
        <rect x="${margin.left}" y="8" width="10" height="10" fill="${colors.kospiKrx}" /><text x="${margin.left + 16}" y="17">KOSPI KRX</text>
        <rect x="${margin.left + 105}" y="8" width="10" height="10" fill="${colors.kospiNxt}" /><text x="${margin.left + 121}" y="17">KOSPI NXT</text>
        <rect x="${margin.left + 210}" y="8" width="10" height="10" fill="${colors.kosdaqKrx}" /><text x="${margin.left + 226}" y="17">KOSDAQ KRX</text>
        <rect x="${margin.left + 332}" y="8" width="10" height="10" fill="${colors.kosdaqNxt}" /><text x="${margin.left + 348}" y="17">KOSDAQ NXT</text>
      </g>
    </svg>
  `;
}

function liquiditySvg(rows) {
  const data = (rows || []).slice(-24);
  if (!data.length) return "";
  const width = 940;
  const height = 310;
  const margin = { left: 72, right: 76, top: 28, bottom: 58 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const deposits = data.map((row) => asFiniteValue(row.Deposit_Value)).filter(Number.isFinite);
  const closes = data.map((row) => asFiniteValue(row.KOSPI_Close)).filter(Number.isFinite);
  const depMinRaw = deposits.length ? Math.min(...deposits) : 0;
  const depMaxRaw = deposits.length ? Math.max(...deposits) : 1;
  const closeMin = closes.length ? Math.min(...closes) : 0;
  const closeMax = closes.length ? Math.max(...closes) : 1;
  const depRangeRaw = Math.max(depMaxRaw - depMinRaw, 1);
  const depMin = Math.max(0, depMinRaw - depRangeRaw * 0.2);
  const depMax = depMaxRaw + depRangeRaw * 0.2;
  const depRange = Math.max(depMax - depMin, 1);
  const closeRange = Math.max(closeMax - closeMin, 1);
  const lineY = (value, min, range) => margin.top + plotH - ((value - min) / range) * plotH;
  const groupW = plotW / data.length;
  const depositPath = data
    .map((row, index) => {
      const value = asFiniteValue(row.Deposit_Value);
      if (!Number.isFinite(value)) return "";
      const x = margin.left + groupW * index + groupW / 2;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${lineY(value, depMin, depRange).toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
  const closePath = data
    .map((row, index) => {
      const value = asFiniteValue(row.KOSPI_Close);
      if (!Number.isFinite(value)) return "";
      const x = margin.left + groupW * index + groupW / 2;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${lineY(value, closeMin - closeRange * 0.15, closeRange * 1.3).toFixed(1)}`;
    })
    .filter(Boolean)
    .join(" ");
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const value = depMin + depRange * ratio;
      const yy = lineY(value, depMin, depRange);
      return `<line x1="${margin.left}" x2="${width - margin.right}" y1="${yy}" y2="${yy}" class="gridLine" />
        <text x="${margin.left - 10}" y="${yy + 4}" class="axisText" text-anchor="end">${formatJoFromMillion(value)}</text>`;
    })
    .join("");
  const lastDeposit = data.slice().reverse().find((row) => Number.isFinite(asFiniteValue(row.Deposit_Value)));
  const labels = lastDeposit
    ? `<text x="${width - margin.right - 4}" y="${lineY(asFiniteValue(lastDeposit.Deposit_Value), depMin, depRange) - 10}" class="chartValue" text-anchor="end">${formatJoFromMillion(lastDeposit.Deposit_Value)}</text>`
    : "";
  return `
    <div class="chartStackInner">
      <svg class="chartSvg" viewBox="0 0 ${width} ${height}" role="img" aria-label="customer deposit and KOSPI close chart">
        ${grid}
        <path d="${depositPath}" class="depositLine" />
        <path d="${closePath}" class="closeLine" />
        ${labels}
        <line x1="${margin.left}" x2="${width - margin.right}" y1="${margin.top + plotH}" y2="${margin.top + plotH}" class="axisLine" />
        <g class="legend">
          <line x1="${margin.left}" x2="${margin.left + 18}" y1="18" y2="18" class="depositLine" /><text x="${margin.left + 25}" y="22">고객예탁금</text>
          <line x1="${margin.left + 122}" x2="${margin.left + 140}" y1="18" y2="18" class="closeLine" /><text x="${margin.left + 147}" y="22">KOSPI 종가</text>
        </g>
      </svg>
    </div>
  `;
}

function creditSvg(rows) {
  const data = (rows || []).slice(-24);
  if (!data.length) return "";
  const width = 940;
  const height = 260;
  const margin = { left: 52, right: 70, top: 26, bottom: 48 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const maxCredit = Math.max(1, ...data.map((row) => asNumber(row.Credit_Total, 0)));
  const ratioValues = data.flatMap((row) => [asNumber(row.Ratio_KOSPI, NaN), asNumber(row.Ratio_KOSDAQ, NaN)]).filter(Number.isFinite);
  const ratioMin = ratioValues.length ? Math.min(...ratioValues) : 0;
  const ratioMax = ratioValues.length ? Math.max(...ratioValues) : 1;
  const ratioRange = Math.max(ratioMax - ratioMin, 0.01);
  const yCredit = (value) => margin.top + plotH - (value / (maxCredit * 1.12)) * plotH;
  const yRatio = (value) => margin.top + plotH - ((value - ratioMin) / ratioRange) * plotH;
  const groupW = plotW / data.length;
  const barW = Math.max(5, Math.min(15, groupW * 0.34));
  const bars = data
    .map((row, index) => {
      const x = margin.left + groupW * index + groupW / 2 - barW / 2;
      const kospi = asNumber(row.Credit_KOSPI, 0);
      const kosdaq = asNumber(row.Credit_KOSDAQ, 0);
      const yKosdaq = yCredit(kosdaq);
      const yTotal = yCredit(kospi + kosdaq);
      const y0 = yCredit(0);
      const label = index % Math.ceil(data.length / 8) === 0 || index === data.length - 1
        ? `<text x="${x + barW / 2}" y="${height - 24}" class="axisText" text-anchor="middle">${shortDate(row.Date)}</text>`
        : "";
      return `
        <rect x="${x}" y="${yKosdaq}" width="${barW}" height="${Math.max(y0 - yKosdaq, 1)}" fill="#bb4a4a" rx="2" />
        <rect x="${x}" y="${yTotal}" width="${barW}" height="${Math.max(yKosdaq - yTotal, 1)}" fill="#4a7ebb" rx="2" />
        ${label}
      `;
    })
    .join("");
  const line = (key) =>
    data
      .map((row, index) => {
        const value = asNumber(row[key], NaN);
        if (!Number.isFinite(value)) return "";
        const x = margin.left + groupW * index + groupW / 2;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${yRatio(value).toFixed(1)}`;
      })
      .filter(Boolean)
      .join(" ");
  const last = data.at(-1);
  const lastX = last ? margin.left + groupW * (data.length - 1) + groupW / 2 : 0;
  const lastLabels = last
    ? `
      <text x="${lastX + 10}" y="${yRatio(asNumber(last.Ratio_KOSPI, 0)) - 8}" class="chartValue" text-anchor="start">${formatPlainPct(last.Ratio_KOSPI)}</text>
      <text x="${lastX + 10}" y="${yRatio(asNumber(last.Ratio_KOSDAQ, 0)) + 16}" class="chartValue" text-anchor="start">${formatPlainPct(last.Ratio_KOSDAQ)}</text>
    `
    : "";
  const footnote = last
    ? `
      <div class="creditFootnote">
        <strong>KOSPI신용 ${formatJoFromMillion(last.Credit_KOSPI)}</strong>
        <strong>KOSDAQ신용 ${formatJoFromMillion(last.Credit_KOSDAQ)}</strong>
        <strong>합계 ${formatJoFromMillion(last.Credit_Total)}</strong>
      </div>
    `
    : "";
  return `
    <div class="chartStackInner">
      <svg class="chartSvg" viewBox="0 0 ${width} ${height}" role="img" aria-label="credit balance and ratio chart">
        <line x1="${margin.left}" x2="${width - margin.right}" y1="${margin.top + plotH}" y2="${margin.top + plotH}" class="axisLine" />
        ${bars}
        <path d="${line("Ratio_KOSPI")}" class="ratioKospiLine" />
        <path d="${line("Ratio_KOSDAQ")}" class="ratioKosdaqLine" />
        ${lastLabels}
        <g class="legend">
          <rect x="${margin.left}" y="8" width="10" height="10" fill="#bb4a4a" /><text x="${margin.left + 16}" y="17">KOSDAQ 신용</text>
          <rect x="${margin.left + 112}" y="8" width="10" height="10" fill="#4a7ebb" /><text x="${margin.left + 128}" y="17">KOSPI 신용</text>
          <line x1="${margin.left + 222}" x2="${margin.left + 240}" y1="13" y2="13" class="ratioKospiLine" /><text x="${margin.left + 247}" y="17">KOSPI 잔고율</text>
          <line x1="${margin.left + 355}" x2="${margin.left + 373}" y1="13" y2="13" class="ratioKosdaqLine" /><text x="${margin.left + 380}" y="17">KOSDAQ 잔고율</text>
        </g>
      </svg>
      ${footnote}
    </div>
  `;
}

function renderSummary() {
  const usPayload = currentPayloads.us_market;
  const flow = currentPayloads.investor_flow?.data || {};
  const ipo = currentPayloads.ipo?.data || {};
  const us = usPayload?.data || {};
  const liquidity = currentPayloads.liquidity?.data || {};
  const todayIpoItems = ipo.today_items || [];
  const nextIpoItems = ipo.next_items || ipo.items || [];
  const liquidityRow = latestRowOnOrBefore(liquidity.lower, "Date", currentDate);
  const nasdaq = (us.fixed || []).find((row) => row.Ticker === "^IXIC");
  const usMarketDate = us.market_date || us.target_session_date || shiftDateString(usPayload?.date || currentDate, -1);
  const ipoQuickRows = [
    ...todayIpoItems.map((row) => ({ ...row, bucket: "오늘" })),
    ...nextIpoItems.map((row) => ({ ...row, bucket: "다음" })),
  ];

  $("summaryCards").innerHTML = [
    metric("신규상장", `${todayIpoItems.length}/${nextIpoItems.length}`, `${ipo.today_listing_date || "오늘"} / ${ipo.next_listing_date || ipo.target_listing_date || "다음"}`),
    metric("NASDAQ", nasdaq ? formatPct(nasdaq.Chg) : "-", usMarketDate || "미국장", signedClass(nasdaq?.Chg)),
    metric("KOSPI 거래대금", formatJoFromEok(tradeTotalEok(liquidityRow, "KOSPI")), liquidityRow?.Date ? `${liquidityRow.Date} KRX+NXT` : "시장 유동성"),
    metric("KOSDAQ 거래대금", formatJoFromEok(tradeTotalEok(liquidityRow, "KOSDAQ")), liquidityRow?.Date ? `${liquidityRow.Date} KRX+NXT` : "시장 유동성"),
    metric("Data", currentDate || "-", `${weekdayEn(currentDate)} · ${selectedDay() ? "available" : "missing"}`),
  ].join("");

  $("quickLists").innerHTML = [
    miniList("외국인 수급", flow.foreigner || [], (row) => miniItem(row.name, `${formatNumber(row.buy_amount_eok)}억`)),
    miniList("기관 수급", flow.institution || [], (row) => miniItem(row.name, `${formatNumber(row.buy_amount_eok)}억`)),
    miniList("신규상장 오늘/다음", ipoQuickRows, (row) => miniItem(`${row.bucket} ${row.name}`, formatEok(row.market_cap))),
  ].join("");
}

function renderAlerts() {
  const payload = currentPayloads.krx_alert;
  if (!payload || payload.status !== "ok") {
    $("alerts").innerHTML = sectionEmpty("투자경고", payload?.data?.reason || payload?.data?.error || "데이터 없음");
    return;
  }
  const data = payload.data || {};
  if (data.target_date && currentDate && data.target_date !== currentDate) {
    $("alerts").innerHTML = sectionEmpty("투자경고", `${currentDate} 화면용 Risk Watch 데이터가 아직 없습니다. 현재 파일 대상일: ${data.target_date}`);
    return;
  }
  const releaseCols = [
    { key: "name", label: "종목" },
    { key: "diff_pct", label: "거리", numeric: true, format: formatPct, className: signedClass },
    { key: "avg_trade_value_5d", label: "5일 평균 거래대금", numeric: true, format: formatEok },
    { key: "current_price", label: "현재가", numeric: true, format: formatNumber },
    { key: "release_ceiling", label: "트리거", numeric: true, format: formatNumber },
    { key: "valid_until", label: "유효일" },
  ];
  const triggerCols = [
    { key: "name", label: "종목" },
    { key: "diff_pct", label: "거리", numeric: true, format: formatPct, className: signedClass },
    { key: "avg_trade_value_5d", label: "5일 평균 거래대금", numeric: true, format: formatEok },
    { key: "current_price", label: "현재가", numeric: true, format: formatNumber },
    { key: "trigger_price", label: "트리거", numeric: true, format: formatNumber },
    { key: "valid_until", label: "유효일" },
  ];
  $("alerts").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">Risk Watch</span><h2>투자경고</h2></div><span class="dateBadge">${escapeHtml(data.target_date || "")}</span></div>
    ${tablePanel("투자경고 해제 심사", sortByAvgTradeValueDesc(data.release), releaseCols, "5일 평균 거래대금순")}
    <div class="twoCol">
      ${tablePanel("지정 예고", sortByAvgTradeValueDesc(data.designation), triggerCols, "5일 평균 거래대금순")}
      ${tablePanel("재지정 심사", sortByAvgTradeValueDesc(data.redesignation), triggerCols, "5일 평균 거래대금순")}
    </div>
  `;
}

function renderUsMarket() {
  const payload = currentPayloads.us_market;
  if (!payload || payload.status !== "ok") {
    $("us").innerHTML = sectionEmpty("미국장", payload?.data?.error || "데이터 없음");
    return;
  }
  const cols = [
    { key: "Name", label: "Name" },
    { label: "Candle", value: candleCell, html: true },
    { key: "Chg", label: "Chg", numeric: true, format: formatPct, className: signedClass },
    { key: "Body", label: "Body", numeric: true, format: formatPct, className: signedClass },
  ];
  const marketDate = payload.data.market_date || payload.data.target_session_date || shiftDateString(payload.date || currentDate, -1) || "Latest";
  $("us").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">US Market</span><h2>미국장</h2></div><span class="dateBadge">${escapeHtml(marketDate)}</span></div>
    <div class="twoCol">
      ${tablePanel("주요 지수·섹터", payload.data.fixed || [], cols)}
      ${tablePanel("거래대금 상위", payload.data.top_traded_value || [], cols)}
    </div>
  `;
}

function renderFlow() {
  const payload = currentPayloads.investor_flow;
  if (!payload || payload.status !== "ok") {
    $("flow").innerHTML = sectionEmpty("수급", payload?.data?.reason || payload?.data?.error || "데이터 없음");
    return;
  }
  const cols = [
    { key: "rank", label: "#", numeric: true },
    { key: "ticker", label: "Ticker" },
    { key: "name", label: "종목" },
    { key: "sector", label: "업종" },
    { key: "buy_amount_eok", label: "매수금액", numeric: true, format: (v) => `${formatNumber(v)}억` },
    { key: "net_buy_amount_eok", label: "순매수", numeric: true, format: (v) => `${formatNumber(v)}억`, className: signedClass },
    { key: "market", label: "시장" },
  ];
  $("flow").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">Flow</span><h2>전일 수급 상위</h2></div><span class="dateBadge">${escapeHtml(payload.data.trade_date || "")}</span></div>
    <div class="twoCol">
      ${tablePanel("외국인", payload.data.foreigner || [], cols)}
      ${tablePanel("기관합계", payload.data.institution || [], cols)}
    </div>
  `;
}

function renderIpo() {
  const payload = currentPayloads.ipo;
  if (!payload || payload.status !== "ok") {
    $("ipo").innerHTML = sectionEmpty("IPO", payload?.data?.reason || payload?.data?.error || "데이터 없음");
    return;
  }
  const cols = [
    { key: "name", label: "회사" },
    { key: "code", label: "Code" },
    { key: "lead_manager", label: "주간사" },
    { key: "offer_price", label: "공모가", numeric: true, format: formatNumber },
    { key: "market_cap", label: "시가총액", numeric: true, format: formatEok },
    { key: "floating_ratio", label: "유통비율", numeric: true, format: formatPct },
    { key: "floating_amount", label: "유통금액", numeric: true, format: formatEok },
    { key: "subscription_competition", label: "청약경쟁률" },
  ];
  const todayItems = payload.data.today_items || [];
  const nextItems = payload.data.next_items || payload.data.items || [];
  $("ipo").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">IPO</span><h2>신규상장</h2></div><span class="dateBadge">${escapeHtml(`${todayItems.length}/${nextItems.length}`)}</span></div>
    <div class="twoCol">
      ${tablePanel("오늘 거래일 신규상장", todayItems, cols, payload.data.today_listing_date || currentDate || "")}
      ${tablePanel("다음 거래일 신규상장", nextItems, cols, payload.data.next_listing_date || payload.data.target_listing_date || "")}
    </div>
  `;
}

function renderExtra() {
  const liquidity = currentPayloads.liquidity;
  const lowerRows = liquidity?.data?.lower || [];
  const upperRows = liquidity?.data?.upper || [];
  const latestLower = lowerRows.at(-1);
  $("extra").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">Extra</span><h2>보조 지표</h2></div><span class="dateBadge">Liquidity / KRX+NXT</span></div>
    <div class="twoCol">
      ${chartShell("시장 유동성", "신용잔고율 / 예탁금", `${creditSvg(upperRows)}${liquiditySvg(lowerRows)}`)}
      ${chartShell("KOSPI · KOSDAQ 거래대금", latestLower?.Date ? `${latestLower.Date} KRX + NXT` : "KRX + NXT", tradeBarsSvg(lowerRows, { height: 390 }))}
    </div>
  `;
}

function sectionEmpty(title, message) {
  return `
    <div class="sectionHeader"><div><span class="eyebrow">Report</span><h2>${escapeHtml(title)}</h2></div></div>
    <div class="empty">${escapeHtml(message || "데이터 없음")}</div>
  `;
}

async function renderAll() {
  $("selectedDateLabel").textContent = dateWithWeekday(currentDate);
  $("briefTitle").textContent = currentDate === preferredCurrentDate() ? "오늘 요약" : "선택일 요약";
  const nextButton = $("nextDayButton");
  if (nextButton) {
    const nextDate = nextAvailableDate(currentDate);
    nextButton.disabled = !nextDate;
    nextButton.title = nextDate ? `다음 거래일 ${nextDate}` : "가장 최신 거래일입니다";
  }
  await loadCurrentPayloads();
  const workflowStatus = await loadWorkflowStatus();
  loadMemo();
  renderWorkflowAlert(workflowStatus);
  renderSummary();
  renderUsMarket();
  renderAlerts();
  renderFlow();
  renderIpo();
  renderExtra();
}

async function init() {
  appIndex = await fetchJson(`${DATA_ROOT}/index.json`);
  $("lastUpdated").textContent = appIndex.generated_at ? `Updated ${appIndex.generated_at}` : "아직 생성된 데이터가 없습니다";
  currentDate = preferredCurrentDate();
  $("dateInput").value = currentDate;
  await renderAll();
}

$("dateInput").addEventListener("change", async (event) => {
  currentDate = event.target.value;
  await renderAll();
});

$("todayButton").addEventListener("click", async () => {
  currentDate = preferredCurrentDate();
  $("dateInput").value = currentDate;
  await renderAll();
});

$("nextDayButton").addEventListener("click", async () => {
  const nextDate = nextAvailableDate(currentDate);
  if (!nextDate) return;
  currentDate = nextDate;
  $("dateInput").value = currentDate;
  await renderAll();
});

$("globalMemoBox").addEventListener("input", saveGlobalMemo);
$("dailyMemoBox").addEventListener("input", saveDailyMemo);

init().catch((error) => {
  $("summaryCards").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
});
