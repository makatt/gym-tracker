"use strict";

/* ---------- state ---------- */
const state = { tgId: localStorage.getItem("gym_tgid") || "", tab: "overview" };
const $ = (s) => document.querySelector(s);
const content = $("#content");

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 1) => (n == null ? "—" : (Math.round(n * 10 ** d) / 10 ** d).toLocaleString("ru-RU"));
const sign = (n) => (n > 0 ? "+" : "") + fmt(n);

async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

/* ---------- svg line chart ---------- */
function lineChart(series, { color = "var(--accent)", height = 180 } = {}) {
  const W = 600, H = height, PAD = 10;
  const vals = series.map((s) => s.y).filter((v) => v != null);
  if (vals.length === 0) return '<div class="empty">Нет данных</div>';
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const n = series.length;
  const stepX = n > 1 ? (W - PAD * 2) / (n - 1) : 0;
  const X = (i) => PAD + i * stepX;
  const Y = (v) => PAD + (H - PAD * 2) * (1 - (v - min) / range);

  const pts = series.map((s, i) => [X(i), Y(s.y)]);
  const poly = pts.map((p) => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const dots = pts.map((p, i) => {
    const label = series[i].label;
    const ttl = `${label}: ${fmt(series[i].y)}`;
    return `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3.2" fill="${color}"><title>${esc(ttl)}</title></circle>`;
  }).join("");

  const grid = [0, 0.5, 1].map((t) => {
    const y = (PAD + (H - PAD * 2) * t).toFixed(1);
    const val = (max - range * t);
    return `<line x1="${PAD}" y1="${y}" x2="${W - PAD}" y2="${y}" stroke="var(--border)" stroke-width="1"/><text x="${PAD - 4}" y="${y}" text-anchor="end" font-size="9" fill="var(--text-faint)">${fmt(val, 0)}</text>`;
  }).join("");

  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img">
    ${grid}
    <polyline points="${poly}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    ${dots}
  </svg>`;
}

/* ---------- components ---------- */
function kpi(value, unit, label, delta, deltaUnit) {
  const d = delta == null ? "" : `<div class="delta ${delta > 0 ? "up" : delta < 0 ? "down" : "flat"}">${sign(delta)}${deltaUnit ?? ""}</div>`;
  return `<div class="card metric"><div class="value">${esc(value)}<span class="unit">${esc(unit ?? "")}</span></div><div class="label">${esc(label)}</div>${d}</div>`;
}

function card(title, inner) {
  return `<section class="card"><h3>${esc(title)}</h3>${inner}</section>`;
}

/* ---------- loaders ---------- */
const loaders = {
  async overview(tg) {
    const [body, kcal, workouts] = await Promise.all([
      get(`/api/body/progress/${tg}`),
      get(`/api/kcal/${tg}`).catch(() => null),
      get(`/api/workouts/${tg}`),
    ]);
    const latest = body.records ? body.latest : null;
    const lastW = workouts.workouts?.find((w) => !w.active);

    const wSeries = body.records ? body.history.slice().reverse().map((h) => ({ label: h.day, y: h.weight })) : [];
    const fSeries = body.records ? body.history.slice().reverse().filter((h) => h.fat != null).map((h) => ({ label: h.day, y: h.fat })) : [];

    let html = `<div class="grid cols-4">`;
    html += kpi(latest ? fmt(latest.weight) : "—", "кг", "Вес", body.weight_delta ?? null, " кг");
    html += kpi(latest?.fat != null ? fmt(latest.fat) : "—", "%", "Жир", body.fat_delta ?? null, "%");
    html += kpi(kcal ? fmt(kcal.target_kcal, 0) : "—", "ккал", "Цель калорий");
    html += kpi(lastW ? lastW.name ?? "—" : "—", "", `Тренировка ${lastW ? lastW.day : ""}`);
    html += `</div>`;

    html += `<div class="grid cols-2">`;
    html += card("Вес · динамика", lineChart(wSeries));
    html += card("Жир · динамика", lineChart(fSeries, { color: "var(--warn)" }));
    html += `</div>`;

    if (kcal) {
      html += card("КБЖУ на день", macrosHtml(kcal));
    }
    return html;
  },

  async body(tg) {
    const [body, kcal] = await Promise.all([
      get(`/api/body/progress/${tg}`),
      get(`/api/kcal/${tg}`).catch(() => null),
    ]);
    const latest = body.records ? body.latest : null;
    const wSeries = body.records ? body.history.slice().reverse().map((h) => ({ label: h.day, y: h.weight })) : [];
    const fSeries = body.records ? body.history.slice().reverse().filter((h) => h.fat != null).map((h) => ({ label: h.day, y: h.fat })) : [];

    let html = `<div class="grid cols-4">`;
    html += kpi(latest ? fmt(latest.weight) : "—", "кг", "Вес", body.weight_delta ?? null, " кг");
    html += kpi(latest?.fat != null ? fmt(latest.fat) : "—", "%", "Жир", body.fat_delta ?? null, "%");
    html += kpi(kcal ? fmt(kcal.bmr, 0) : "—", "", "BMR");
    html += kpi(kcal ? fmt(kcal.tdee, 0) : "—", "", "TDEE");
    html += `</div>`;

    if (kcal) {
      html += `<div class="grid cols-2">${card("КБЖУ на день", macrosHtml(kcal))}${card("Профиль", rowsHtml([
        ["Пол", kcal.sex === "male" ? "муж" : "жен"],
        ["Возраст", kcal.age],
        ["Вес", fmt(kcal.weight) + " кг"],
        ["Цель", { cut: "сушка", maintain: "поддержание", bulk: "набор" }[kcal.goal] ?? kcal.goal],
      ]))}</div>`;
    }

    html += `<div class="grid cols-2">${card("Вес", lineChart(wSeries))}${card("Жир", lineChart(fSeries, { color: "var(--warn)" }))}</div>`;

    if (body.records) {
      html += card("История замеров", `<table><thead><tr><th>Дата</th><th class="num">Вес</th><th class="num">Жир</th><th class="num">Мышцы</th></tr></thead><tbody>` +
        body.history.slice(0, 12).map((h) =>
          `<tr><td>${esc(h.day)}</td><td class="num">${fmt(h.weight)} кг</td><td class="num">${h.fat != null ? fmt(h.fat) + "%" : "—"}</td><td class="num">${h.muscle != null ? fmt(h.muscle) + " кг" : "—"}</td></tr>`).join("") +
        `</tbody></table>`);
    }
    return html;
  },

  async strength(tg) {
    const { exercises } = await get(`/api/exercises/${tg}`);
    if (!exercises.length) return '<div class="empty">Упражнений пока нет — добавь через бота: жим 80x2</div>';

    const chips = exercises.map((e) => `<button class="chip" data-ex="${esc(e)}">${esc(e)}</button>`).join(" ");
    let html = `<div class="card"><h3>Упражнения</h3><div style="display:flex;flex-wrap:wrap;gap:8px">${chips}</div></div>`;
    html += `<div id="strength-detail">${card("Выбери упражнение", '<div class="empty">Нажми на упражнение выше</div>')}</div>`;

    // выбрать первое по умолчанию
    setTimeout(() => strengthDetail(tg, exercises[0]), 0);
    return html;
  },

  async workouts(tg) {
    const { workouts } = await get(`/api/workouts/${tg}`);
    if (!workouts.length) return '<div class="empty">Тренировок пока нет — начни в боте: /workout</div>';
    return card("История тренировок", `<table><thead><tr><th>Дата</th><th>День</th><th class="num">Подходов</th><th></th></tr></thead><tbody>` +
      workouts.map((w) =>
        `<tr><td>${esc(w.day)}</td><td>${esc(w.name ?? "—")}</td><td class="num">${w.count}</td><td>${w.active ? '<span class="tag active">активна</span>' : ""}</td></tr>`).join("") +
      `</tbody></table>`);
  },

  async nutrition(tg) {
    const [week, month] = await Promise.all([
      get(`/api/summary/${tg}?days=7`),
      get(`/api/summary/${tg}?days=30`),
    ]);
    const goal = week.goal;
    const deltaKcal = (s) => s.diff_vs_goal ? s.diff_vs_goal.calories : null;

    let html = `<div class="grid cols-2">`;
    html += card("Неделя", nutritionSummary(week, deltaKcal(week)));
    html += card("Месяц", nutritionSummary(month, deltaKcal(month)));
    html += `</div>`;

    if (goal) {
      html += card("Норма", rowsHtml([
        ["Калории", fmt(goal.calories, 0) + " ккал"],
        ["Белки", fmt(goal.protein) + " г"],
        ["Жиры", fmt(goal.fat) + " г"],
        ["Углеводы", fmt(goal.carbs) + " г"],
      ]));
    }
    return html;
  },
};

function nutritionSummary(s, delta) {
  const avg = s.daily_avg;
  const d = delta == null ? "" : `<div class="delta ${delta > 0 ? "down" : delta < 0 ? "up" : "flat"}">${sign(delta, 0)} ккал vs норма</div>`;
  return `<div class="rows">
    ${row("Записей", s.days_recorded + " / " + s.period_days)}
    ${row("Ккал/день", fmt(avg.calories, 0))}
    ${row("Белки", fmt(avg.protein) + " г")}
    ${row("Жиры", fmt(avg.fat) + " г")}
    ${row("Углеводы", fmt(avg.carbs) + " г")}
    ${d}
  </div>`;
}

function macrosHtml(k) {
  const max = Math.max(k.protein, k.fat, k.carbs, 1);
  const bar = (name, g) => `<div class="macro"><div class="top"><span>${name}</span><b>${fmt(g)} г</b></div><div class="bar"><i style="width:${(g / max) * 100}%"></i></div></div>`;
  return `<div class="macros">
    <div class="metric" style="margin-bottom:14px"><div class="value">${fmt(k.target_kcal, 0)}<span class="unit">ккал</span></div><div class="label">цель · ${esc(k.goal)}</div></div>
    ${bar("Белки", k.protein)}${bar("Жиры", k.fat)}${bar("Углеводы", k.carbs)}
  </div>`;
}

const rowsHtml = (rows) => `<div class="rows">${rows.map(([k, v]) => row(k, v)).join("")}</div>`;
const row = (k, v) => `<div class="row"><span class="k">${esc(k)}</span><span class="v"><strong>${esc(v)}</strong></span></div>`;

async function strengthDetail(tg, ex) {
  const el = $("#strength-detail");
  if (!el) return;
  try {
    const p = await get(`/api/strength/progress/${tg}/${encodeURIComponent(ex)}`);
    const series = p.history.map((h) => ({ label: h.day, y: h.e1rm }));
    el.innerHTML = card(ex, `<div class="grid cols-4">
      ${kpi(p.best_e1rm, "кг", "Лучший 1ПМ")}
      ${kpi(p.first_e1rm, "кг", "Старт 1ПМ")}
      ${kpi(p.delta_e1rm, "кг", "Прирост", p.delta_e1rm)}
      ${kpi(p.records, "", "Записей")}
    </div>` + card("1ПМ · динамика", lineChart(series)) +
      `<table><thead><tr><th>Дата</th><th class="num">Вес</th><th class="num">Повторы</th><th class="num">1ПМ</th></tr></thead><tbody>` +
      p.history.slice().reverse().map((h) => `<tr><td>${esc(h.day)}</td><td class="num">${fmt(h.weight)} кг</td><td class="num">${h.reps}</td><td class="num">${fmt(h.e1rm)}</td></tr>`).join("") +
      `</tbody></table>`);
  } catch (e) {
    el.innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

/* ---------- render ---------- */
async function render() {
  const tg = state.tgId;
  if (!tg) {
    content.innerHTML = '<div class="empty">Введи свой Telegram ID вверху, чтобы увидеть данные.<br><span style="font-family:var(--mono)">Твой ID: 802509605</span></div>';
    return;
  }
  content.innerHTML = '<div class="empty">Загрузка…</div>';
  try {
    content.innerHTML = await loaders[state.tab](tg);
  } catch (e) {
    content.innerHTML = `<div class="error">Не удалось загрузить: ${esc(e.message)}</div>`;
  }
}

/* ---------- events ---------- */
$("#tgid").value = state.tgId;
$("#tgid").addEventListener("input", (e) => {
  state.tgId = e.target.value.trim();
  localStorage.setItem("gym_tgid", state.tgId);
  render();
});

$("#tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (!btn) return;
  state.tab = btn.dataset.tab;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b === btn));
  render();
});

document.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip[data-ex]");
  if (chip) {
    document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c === chip));
    strengthDetail(state.tgId, chip.dataset.ex);
  }
});

render();
