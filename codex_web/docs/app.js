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
  return number.toLocaleString("ko-KR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatEok(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${formatNumber(Number(value) / 100000000, digits)}억`;
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
  const names = REPORT_ORDER.filter((name) => day?.reports?.[name]);
  const entries = await Promise.all(names.map(async (name) => [name, await loadReport(name)]));
  currentPayloads = Object.fromEntries(entries);
}

function memoKey() {
  return `krxmarket:memo:${currentDate || "none"}`;
}

function loadMemo() {
  $("memoBox").value = localStorage.getItem(memoKey()) || "";
  $("noteStatus").textContent = "브라우저에 저장";
}

function saveMemo() {
  localStorage.setItem(memoKey(), $("memoBox").value);
  $("noteStatus").textContent = "저장됨";
  window.clearTimeout(saveMemo._timer);
  saveMemo._timer = window.setTimeout(() => {
    $("noteStatus").textContent = "브라우저에 저장";
  }, 1200);
}

function metric(label, value, caption = "") {
  return `
    <article class="metric">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value)}</span>
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
          return `<td class="${cls}">${escapeHtml(value ?? "-")}</td>`;
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

function renderSummary() {
  const flow = currentPayloads.investor_flow?.data || {};
  const ipo = currentPayloads.ipo?.data || {};
  const alert = currentPayloads.krx_alert?.data || {};
  const us = currentPayloads.us_market?.data || {};
  const foreignTop = flow.foreigner?.[0];
  const instTop = flow.institution?.[0];
  const ipoCount = ipo.items?.length || 0;
  const releaseCount = alert.release?.length || 0;
  const designationCount = (alert.designation?.length || 0) + (alert.redesignation?.length || 0);
  const nasdaq = (us.fixed || []).find((row) => row.Ticker === "^IXIC");

  $("summaryCards").innerHTML = [
    metric("외국인 1위", foreignTop?.name || "-", foreignTop ? `${formatNumber(foreignTop.buy_amount_eok)}억 매수` : "수급"),
    metric("기관 1위", instTop?.name || "-", instTop ? `${formatNumber(instTop.buy_amount_eok)}억 매수` : "수급"),
    metric("신규상장", `${ipoCount}`, ipo.target_listing_date || "다음 거래일"),
    metric("투자경고", `${releaseCount}/${designationCount}`, "해제 / 지정·재지정"),
    metric("NASDAQ", nasdaq ? formatPct(nasdaq.Chg) : "-", "미국장"),
    metric("US Top", us.top_traded_value?.[0]?.Ticker || "-", us.top_traded_value?.[0]?.Name || "거래대금"),
    metric("NXT", currentPayloads.nxt_market?.data?.trade_time || "-", currentPayloads.nxt_market?.data?.trade_date || "누적 거래대금"),
    metric("Data", currentDate || "-", selectedDay() ? "available" : "missing"),
  ].join("");

  $("quickLists").innerHTML = [
    miniList("외국인 수급", flow.foreigner || [], (row) => miniItem(row.name, `${formatNumber(row.buy_amount_eok)}억`)),
    miniList("기관 수급", flow.institution || [], (row) => miniItem(row.name, `${formatNumber(row.buy_amount_eok)}억`)),
    miniList("다음 거래일 신규상장", ipo.items || [], (row) => miniItem(row.name, formatEok(row.market_cap))),
  ].join("");
}

function renderAlerts() {
  const payload = currentPayloads.krx_alert;
  if (!payload || payload.status !== "ok") {
    $("alerts").innerHTML = sectionEmpty("투자경고", payload?.data?.reason || payload?.data?.error || "데이터 없음");
    return;
  }
  const data = payload.data || {};
  const releaseCols = [
    { key: "code", label: "Code" },
    { key: "name", label: "종목" },
    { key: "current_price", label: "현재가", numeric: true, format: formatNumber },
    { key: "release_ceiling", label: "해제 상한", numeric: true, format: formatNumber },
    { key: "diff_pct", label: "여유율", numeric: true, format: formatPct, className: signedClass },
    { key: "avg_trade_value_5d", label: "5일 평균 거래대금", numeric: true, format: formatEok },
  ];
  const triggerCols = [
    { key: "code", label: "Code" },
    { key: "name", label: "종목" },
    { key: "current_price", label: "현재가", numeric: true, format: formatNumber },
    { key: "trigger_price", label: "트리거", numeric: true, format: formatNumber },
    { key: "diff_pct", label: "거리", numeric: true, format: formatPct, className: signedClass },
    { key: "avg_trade_value_5d", label: "5일 평균 거래대금", numeric: true, format: formatEok },
    { key: "valid_until", label: "유효일" },
  ];
  $("alerts").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">Risk Watch</span><h2>투자경고</h2></div><span class="dateBadge">${escapeHtml(data.target_date || "")}</span></div>
    ${tablePanel("투자경고 해제 심사", data.release || [], releaseCols, "필터 통과 전체")}
    <div class="twoCol">
      ${tablePanel("지정 예고", data.designation || [], triggerCols)}
      ${tablePanel("재지정 심사", data.redesignation || [], triggerCols)}
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
    { key: "Ticker", label: "Ticker" },
    { key: "Name", label: "Name" },
    { key: "Chg", label: "Chg", numeric: true, format: formatPct, className: signedClass },
    { key: "Body", label: "Body", numeric: true, format: formatPct, className: signedClass },
    { key: "Close", label: "Close", numeric: true, format: (v) => formatNumber(v, 2) },
    { key: "Volume", label: "Volume", numeric: true, format: formatNumber },
  ];
  $("us").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">US Market</span><h2>미국장</h2></div><span class="dateBadge">Latest</span></div>
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
    <div class="sectionHeader"><div><span class="eyebrow">Flow</span><h2>수급</h2></div><span class="dateBadge">${escapeHtml(payload.data.trade_date || "")}</span></div>
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
  $("ipo").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">IPO</span><h2>신규상장</h2></div><span class="dateBadge">${escapeHtml(payload.data.target_listing_date || "")}</span></div>
    ${tablePanel("다음 거래일 신규상장", payload.data.items || [], cols)}
  `;
}

function renderExtra() {
  const liquidity = currentPayloads.liquidity;
  const nxt = currentPayloads.nxt_market;
  const lowerCols = [
    { key: "Date", label: "Date" },
    { key: "KOSPI_Trade_Total", label: "KOSPI 거래대금", numeric: true, format: (v) => `${formatNumber(v)}억` },
    { key: "KOSDAQ_Trade_Total", label: "KOSDAQ 거래대금", numeric: true, format: (v) => `${formatNumber(v)}억` },
    { key: "Deposit_Value", label: "예탁금", numeric: true, format: (v) => `${formatNumber(v)}억` },
  ];
  const nxtRows = nxt?.status === "ok"
    ? [
        { market: "Total", value: nxt.data.total_trade_value, volume: nxt.data.total_trade_volume, issues: nxt.data.issue_total_count },
        { market: "KOSPI", value: nxt.data.kospi_trade_value, volume: nxt.data.kospi_trade_volume, issues: nxt.data.issue_kospi_count },
        { market: "KOSDAQ", value: nxt.data.kosdaq_trade_value, volume: nxt.data.kosdaq_trade_volume, issues: nxt.data.issue_kosdaq_count },
      ]
    : [];
  const nxtCols = [
    { key: "market", label: "Market" },
    { key: "value", label: "거래대금", numeric: true, format: formatEok },
    { key: "volume", label: "거래량", numeric: true, format: formatNumber },
    { key: "issues", label: "종목수", numeric: true, format: formatNumber },
  ];
  $("extra").innerHTML = `
    <div class="sectionHeader"><div><span class="eyebrow">Extra</span><h2>보조 지표</h2></div><span class="dateBadge">Liquidity / NXT</span></div>
    <div class="twoCol">
      ${tablePanel("시장 유동성", liquidity?.data?.lower || [], lowerCols)}
      ${tablePanel("NXT 거래대금", nxtRows, nxtCols, nxt?.data?.trade_time || "")}
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
  $("selectedDateLabel").textContent = currentDate || "-";
  $("briefTitle").textContent = currentDate === appIndex?.latest_date ? "오늘 요약" : "선택일 요약";
  await loadCurrentPayloads();
  loadMemo();
  renderSummary();
  renderAlerts();
  renderUsMarket();
  renderFlow();
  renderIpo();
  renderExtra();
}

async function init() {
  appIndex = await fetchJson(`${DATA_ROOT}/index.json`);
  $("lastUpdated").textContent = appIndex.generated_at ? `Updated ${appIndex.generated_at}` : "아직 생성된 데이터가 없습니다";
  currentDate = appIndex.latest_date || availableDates()[0] || new Date().toISOString().slice(0, 10);
  $("dateInput").value = currentDate;
  await renderAll();
}

$("dateInput").addEventListener("change", async (event) => {
  currentDate = event.target.value;
  await renderAll();
});

$("todayButton").addEventListener("click", async () => {
  currentDate = appIndex?.latest_date || new Date().toISOString().slice(0, 10);
  $("dateInput").value = currentDate;
  await renderAll();
});

$("memoBox").addEventListener("input", saveMemo);

init().catch((error) => {
  $("summaryCards").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
});
