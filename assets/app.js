/* Recipes — a static SPA over one JSON bundle. No framework, no build step.
   Everything below runs from the hash: #/ for the list, #/r/<slug> for a
   recipe, with filters carried in the query so any view can be linked. */

const DATA_URL = "data/recipes.json";
const SPRITE_URL = "assets/icons.svg";

const GROUPS = [
  { key: "cuisine", label: "Cuisine" },
  { key: "course", label: "Course" },
  { key: "protein", label: "Protein" },
  { key: "diet", label: "Diet" },
  { key: "method", label: "Method" },
];

// Tag values are single words in the vault; spell them out for reading.
const LABELS = {
  aigenerated: "ai written", mealprep: "meal prep", loweffort: "low effort",
  slowcook: "slow cook", single: "single serving",
};

const $ = (sel, root = document) => root.querySelector(sel);
const el = (id) => document.getElementById(id);
const label = (value) => LABELS[value] || value;

let DATA = null;
let BY_SLUG = new Map();
let SLUG_OF_TITLE = new Map();
let SPRITE_IDS = new Set();
let listScroll = 0;

const state = { q: "", filters: new Map(), servings: new Map() };

/* ============================== utilities ============================== */

const escapeHTML = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const titleCase = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function icon(name, cls = "ico") {
  if (!SPRITE_IDS.has("i-" + name)) return "";
  return `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

function store(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch { return fallback; }
}

function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
}

/* ========================= quantity scaling =========================

   Only the leading quantity of an amount is scaled. "2 cans, 14 oz/414 mL
   each" should double the cans, not the can size, and "73-75°F" must never
   move at all. Scaling just the first number is the reading a cook expects,
   and it fails safe on everything written loosely.                        */

const VULGAR = { "¼": 0.25, "½": 0.5, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3,
                 "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875 };
const NEAR = [[1, ""], [0.25, "¼"], [1 / 3, "⅓"], [0.5, "½"], [2 / 3, "⅔"], [0.75, "¾"]];
const LEAD_QTY = new RegExp(
  "^(\\s*[~≈]?\\s*)(" +
  "(?:\\d+(?:[.,]\\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞])(?:\\s+[¼½¾⅓⅔⅛⅜⅝⅞]|\\s*/\\s*\\d+)?" +
  ")(\\s*(?:-|–|—|to)\\s*(?:\\d+(?:[.,]\\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞]))?");

function toNumber(token) {
  token = token.trim();
  if (VULGAR[token] !== undefined) return VULGAR[token];
  const mixed = token.match(/^(\d+)\s+([¼½¾⅓⅔⅛⅜⅝⅞])$/);
  if (mixed) return parseInt(mixed[1], 10) + VULGAR[mixed[2]];
  const frac = token.match(/^(\d+)\s*\/\s*(\d+)$/);
  if (frac) return parseInt(frac[1], 10) / parseInt(frac[2], 10);
  const n = parseFloat(token.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

function formatQty(n) {
  if (n >= 10) return String(Math.round(n));
  const whole = Math.floor(n + 1e-9);
  const rest = n - whole;
  for (const [value, glyph] of NEAR) {
    if (Math.abs(rest - value) < 0.04) {
      if (!glyph) return String(whole + 1);
      return whole ? `${whole}${glyph}` : glyph;
    }
  }
  if (Math.abs(rest) < 0.04) return String(whole);
  return String(Math.round(n * 100) / 100);
}

function scaleAmount(amount, factor) {
  if (!amount || factor === 1) return { text: amount, scaled: false };
  if (/^[^0-9¼½¾⅓⅔⅛⅜⅝⅞]*°/.test(amount)) return { text: amount, scaled: false };
  const m = amount.match(LEAD_QTY);
  if (!m || !m[2]) return { text: amount, scaled: false };
  const base = toNumber(m[2]);
  if (base === null || base === 0) return { text: amount, scaled: false };

  let out = m[1] + formatQty(base * factor);
  if (m[3]) {
    const hi = toNumber(m[3].replace(/^[\s\-–—]*(to)?\s*/, ""));
    out += hi === null ? m[3] : "–" + formatQty(hi * factor);
  }
  return { text: out + amount.slice(m[0].length), scaled: true };
}

/* ====================== minimal markdown rendering ======================

   Only the subset the vault actually uses: headings, lists, tables, fenced
   code, wikilinks, and inline emphasis. Input is escaped first, so nothing
   below can inject markup.                                                */

function inline(text) {
  let s = escapeHTML(text);
  s = s.replace(/`([^`]+)`/g, (_, code) => `<code>${code}</code>`);
  s = s.replace(/\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]/g, (_, target, alias) => {
    const label = escapeHTML(alias || target);
    const slug = SLUG_OF_TITLE.get(target.trim());
    return slug ? `<a class="wikilink" href="#/r/${slug}">${label}</a>` : label;
  });
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (_, label, href) =>
      `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  return s;
}

function markdown(src) {
  const lines = String(src).replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^```/.test(line)) {
      const lang = line.slice(3).trim();
      const body = [];
      for (i++; i < lines.length && !/^```/.test(lines[i]); i++) body.push(lines[i]);
      i++;
      const caption = lang ? `${lang} block — runs in Obsidian` : "Code";
      out.push(`<details><summary>${escapeHTML(caption)}</summary>` +
               `<pre><code>${escapeHTML(body.join("\n"))}</code></pre></details>`);
      continue;
    }

    if (/^\|.*\|\s*$/.test(line) && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      const cells = (row) => row.replace(/^\||\|\s*$/g, "").split("|").map((c) => c.trim());
      const head = cells(line);
      i += 2;
      const body = [];
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) body.push(cells(lines[i++]));
      out.push("<table><thead><tr>" +
        head.map((c) => `<th>${inline(c)}</th>`).join("") +
        "</tr></thead><tbody>" +
        body.map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") +
        "</tbody></table>");
      continue;
    }

    const heading = line.match(/^#{3,6}\s+(.*)$/);
    if (heading) { out.push(`<h3>${inline(heading[1])}</h3>`); i++; continue; }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\s*[-*]\s+(\[[ xX]\]\s*)?/, ""))}</li>`);
        i++;
      }
      out.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        i++;
      }
      out.push(`<ol class="prose-ol">${items.join("")}</ol>`);
      continue;
    }

    if (!line.trim()) { i++; continue; }

    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(\s*[-*]\s|\s*\d+\.\s|#{3,6}\s|\||```)/.test(lines[i])) {
      para.push(lines[i++]);
    }
    out.push(`<p>${inline(para.join(" "))}</p>`);
  }
  return out.join("");
}

/* ============================ search + filter ============================ */

function buildIndex(recipes) {
  for (const r of recipes) {
    const parts = [r.title, r.summary, r.tags.join(" "), r.folder];
    for (const g of r.shopping) for (const it of g.items) parts.push(it.name);
    for (const g of r.steps) for (const s of g.steps) parts.push(s.name, s.text);
    for (const x of r.extras) parts.push(x.heading, x.md);
    r._hay = parts.join("  ").toLowerCase();
  }
}

function matches(recipe) {
  for (const [group, values] of state.filters) {
    if (!values.size) continue;
    const own = recipe.facets[group] || [];
    // OR inside a dimension, AND across them — "korean or thai, and quick".
    if (![...values].some((v) => own.includes(v))) return false;
  }
  if (!state.q) return true;
  return state.q.toLowerCase().split(/\s+/).filter(Boolean)
    .every((token) => recipe._hay.includes(token));
}

const filtered = () => DATA.recipes.filter(matches);

function activeCount() {
  let n = 0;
  for (const values of state.filters.values()) n += values.size;
  return n;
}

/* ============================== the hash ============================== */

function readHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  const params = new URLSearchParams(query);
  state.q = params.get("q") || "";
  state.filters = new Map();
  for (const { key } of GROUPS) {
    const value = params.get(key);
    state.filters.set(key, new Set(value ? value.split(",").filter(Boolean) : []));
  }
  return path;
}

function hashFor(path) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  for (const { key } of GROUPS) {
    const values = state.filters.get(key);
    if (values && values.size) params.set(key, [...values].join(","));
  }
  const query = params.toString();
  return "#" + path + (query ? "?" + query : "");
}

const currentPath = () => (location.hash.replace(/^#/, "").split("?")[0] || "/");

const currentSlug = () =>
  currentPath().startsWith("/r/") ? decodeURIComponent(currentPath().slice(3)) : null;

/* Filter and query changes rewrite the hash in place — they're a refinement of
   the same view, not a new entry in the back stack. replaceState fires no
   hashchange, so re-render explicitly. */
function go(path, replace = false) {
  const next = hashFor(path);
  if (replace || next === location.hash) {
    history.replaceState(null, "", next);
    render();
  } else {
    location.hash = next;
  }
}

/* ============================== rendering ============================== */

/* A chip's count is how many recipes you'd get by adding it — so it ignores
   its own dimension but respects every other one. Otherwise the numbers
   contradict the list as soon as you pick anything. */
function countsExcluding(groupKey) {
  const tally = {};
  for (const r of DATA.recipes) {
    let ok = true;
    for (const [group, values] of state.filters) {
      if (group === groupKey || !values.size) continue;
      if (![...values].some((v) => (r.facets[group] || []).includes(v))) { ok = false; break; }
    }
    if (ok && state.q) {
      ok = state.q.toLowerCase().split(/\s+/).filter(Boolean)
        .every((token) => r._hay.includes(token));
    }
    if (!ok) continue;
    for (const v of r.facets[groupKey] || []) tally[v] = (tally[v] || 0) + 1;
  }
  return tally;
}

function renderFilters() {
  el("filter-groups").innerHTML = GROUPS.map(({ key, label: groupName }) => {
    const values = DATA.facets[key] || [];
    if (!values.length) return "";
    const counts = countsExcluding(key);
    const chips = values.map(({ value }) => {
      const on = state.filters.get(key).has(value);
      const n = counts[value] || 0;
      const glyph = key === "course" ? icon("course-" + value)
                  : key === "protein" ? icon("protein-" + value) : "";
      return `<button class="chip" type="button" role="switch" aria-pressed="${on}"
        data-group="${key}" data-value="${escapeHTML(value)}" data-empty="${!on && !n ? 1 : 0}"
        >${glyph}${escapeHTML(label(value))}<span class="chip-n">${n}</span></button>`;
    }).join("");
    return `<div class="fgroup"><div class="fgroup-name"><span class="eyebrow">${groupName}</span></div>
      <div class="chips">${chips}</div></div>`;
  }).join("");

  const n = activeCount();
  const pip = el("filter-count");
  pip.hidden = !n;
  pip.textContent = n;
  el("clear-filters").hidden = !n && !state.q;
}

function stubTags(r) {
  const bits = [];
  for (const v of r.facets.cuisine || []) bits.push(escapeHTML(v));
  for (const v of r.facets.course || []) bits.push(icon("course-" + v) + escapeHTML(v));
  for (const v of r.facets.protein || []) bits.push(icon("protein-" + v) + escapeHTML(label(v)));
  if ((r.facets.method || []).includes("quick")) bits.push("quick");
  return bits.map((b) => `<span>${b}</span>`).join("");
}

function renderList() {
  el("recipe-view").hidden = true;
  el("list-view").hidden = false;

  const results = filtered();
  const cuisines = state.filters.get("cuisine");
  const single = cuisines.size === 1 ? [...cuisines][0] : null;

  el("results-title").textContent = single ? titleCase(single) : "All recipes";
  document.title = single ? `${titleCase(single)} recipes` : "Recipes";

  const bits = [`${results.length} of ${DATA.count}`];
  if (state.q) bits.push(`matching “${state.q}”`);
  if (activeCount()) bits.push(`${activeCount()} filter${activeCount() > 1 ? "s" : ""}`);
  bits.push(`synced ${new Date(DATA.generated).toLocaleDateString(undefined,
    { day: "numeric", month: "short", year: "numeric" })}`);
  el("results-meta").textContent = bits.join(" · ");

  const hub = single && DATA.cuisines.find((c) => c.slug === single);
  const note = el("hub-note");
  note.hidden = !(hub && hub.notes);
  if (hub && hub.notes) note.textContent = hub.notes;

  el("empty").hidden = results.length > 0;
  el("results").innerHTML = results.map((r) => `
    <li class="stub">
      <a class="stub-link" href="#/r/${r.slug}">
        <span class="stub-no">${String(r.id).padStart(3, "0")}</span>
        <h2 class="stub-title">${escapeHTML(r.title)}</h2>
        <p class="stub-tags">${stubTags(r)}</p>
        ${r.summary ? `<p class="stub-sum">${escapeHTML(r.summary)}</p>` : ""}
      </a>
    </li>`).join("");
}

/* ------------------------------ one recipe ------------------------------ */

const doneKey = (slug) => "recipes:done:" + slug;

function readDone(slug) { return new Set(store(doneKey(slug), [])); }

function toggleDone(slug, id, on) {
  const done = readDone(slug);
  if (on) done.add(id); else done.delete(id);
  save(doneKey(slug), [...done]);
}

function ingredientsHTML(r, factor, done) {
  return r.shopping.map((group, gi) => {
    const rows = group.items.map((item, ii) => {
      const id = `i${gi}-${ii}`;
      const { text, scaled } = scaleAmount(item.amount, factor);
      // Short amounts keep the receipt leader; long ones stack on narrow screens.
      const shape = !text ? " is-bare" : text.length > 18 ? " is-long" : "";
      return `<button class="ing${shape}" type="button" role="switch"
          aria-pressed="${done.has(id)}" data-done="${id}">
        <span class="ing-box" aria-hidden="true">✓</span>
        <span class="ing-name"><span>${escapeHTML(item.name)}</span></span>
        ${text ? `<span class="ing-amt${scaled ? " is-scaled" : ""}">${escapeHTML(text)}</span>` : ""}
      </button>`;
    }).join("");
    const head = group.section
      ? `<h3 class="subsection">${escapeHTML(group.section)}</h3>` : "";
    return head + `<div class="ings">${rows}</div>`;
  }).join("");
}

function stepsHTML(r, done) {
  return r.steps.map((group, gi) => {
    const head = group.section
      ? `<h3 class="subsection">${escapeHTML(group.section)}</h3>` : "";
    const items = group.steps.map((s, si) => {
      const id = `s${gi}-${si}`;
      const sub = s.sub && s.sub.length
        ? `<ul class="step-sub">${s.sub.map((x) => `<li>${inline(x)}</li>`).join("")}</ul>` : "";
      return `<li><button class="step" type="button" role="switch"
          aria-pressed="${done.has(id)}" data-done="${id}">
        <span class="step-body">
          ${s.name ? `<strong class="step-name">${escapeHTML(s.name)}</strong>` : ""}
          ${inline(s.md)}${sub}
        </span></button></li>`;
    }).join("");
    return head + `<ol class="steps">${items}</ol>`;
  }).join("");
}

function renderRecipe(slug) {
  const r = BY_SLUG.get(slug);
  if (!r) { go("/", true); return; }

  el("list-view").hidden = true;
  const view = el("recipe-view");
  view.hidden = false;
  document.title = `${r.title} — Recipes`;

  const base = r.servings;
  const target = state.servings.get(slug) || base;
  const factor = base ? target / base : 1;
  const done = readDone(slug);

  const stats = [
    ["Prep", r.times.prep], ["Cook", r.times.cook],
    ["Total", r.times.total], ["Yield", r.times.yield],
  ].filter(([, v]) => v).map(([k, v]) =>
    `<div class="stat"><div class="eyebrow">${k}</div><div class="stat-v">${escapeHTML(v)}</div></div>`
  ).join("");

  const chips = r.tags.map((t) => {
    const [prefix, value] = t.includes("/") ? t.split("/") : [null, t];
    const group = { cuisine: "cuisine", type: "course", protein: "protein", diet: "diet" }[prefix]
      || (prefix ? null : "method");
    const text = escapeHTML(label(value));
    const glyph = group === "course" ? icon("course-" + value)
                : group === "protein" ? icon("protein-" + value) : "";
    return group
      ? `<button class="chip" type="button" data-jump="${group}:${escapeHTML(value)}">${glyph}${text}</button>`
      : `<span class="chip">${text}</span>`;
  }).join("");

  const scaler = base ? `
    <div class="scaler" role="group" aria-label="Scale the quantities">
      <button class="scaler-btn" type="button" data-scale="-1" aria-label="Fewer servings"
        ${target <= 1 ? "disabled" : ""}>−</button>
      <span class="scaler-v">Serves <b>${target}</b>${factor !== 1 ? ` (${factor.toFixed(2).replace(/\.?0+$/, "")}×)` : ""}</span>
      <button class="scaler-btn" type="button" data-scale="1" aria-label="More servings"
        ${target >= base * 8 ? "disabled" : ""}>+</button>
    </div>` : "";

  const pairs = r.pairs.length ? `
    <section class="section">
      <h2 class="section-name">${icon("salt")}Pairs well with</h2>
      <div class="pairs">${r.pairs.map((p) => p.slug
        ? `<a class="pair" href="#/r/${p.slug}"><div class="pair-t">${escapeHTML(p.title)}</div>
             ${p.note ? `<div class="pair-n">${escapeHTML(p.note)}</div>` : ""}</a>`
        : `<div class="pair"><div class="pair-t">${escapeHTML(p.title)}</div>
             <div class="pair-n">Not in the collection yet</div></div>`).join("")}</div>
    </section>` : "";

  const extras = r.extras.map((x) => `
    <section class="section">
      <h2 class="section-name">${escapeHTML(x.heading)}</h2>
      <div class="prose">${markdown(x.md)}</div>
    </section>`).join("");

  view.innerHTML = `
    <a class="back" href="${hashFor("/")}">← All recipes</a>
    <div class="ticket">
      <div class="ticket-no">No. ${String(r.id).padStart(3, "0")}</div>
      <h1 class="ticket-title">${escapeHTML(r.title)}</h1>
      <div class="ticket-tags">${chips}</div>
      ${r.summary ? `<p class="ticket-sum">${escapeHTML(r.summary)}</p>` : ""}
      ${stats ? `<div class="stats">${stats}</div>` : ""}
      <div class="ticket-tools">
        ${r.steps.length ? `<button class="btn btn-solid" data-cook="1">${icon("cook")}Cook mode</button>` : ""}
        ${scaler}
      </div>

      ${r.shopping.length ? `<section class="section">
        <h2 class="section-name">${icon("basket")}Shopping list</h2>
        ${ingredientsHTML(r, factor, done)}
        ${factor !== 1 ? `<p class="cook-hint">Scaled quantities are shown in red. Only the leading number of each amount is scaled.</p>` : ""}
      </section>` : ""}

      ${r.steps.length ? `<section class="section">
        <h2 class="section-name">${icon("list")}Method</h2>
        ${stepsHTML(r, done)}
      </section>` : ""}

      ${pairs}
      ${extras}

      <div class="ticket-foot">
        From ${escapeHTML(r.folder ? r.folder + "/" : "")}${escapeHTML(r.title)}.md
      </div>
    </div>`;
}

/* ============================== cook mode ============================== */

let wakeLock = null;

async function acquireWakeLock() {
  if (!("wakeLock" in navigator)) return false;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
    wakeLock.addEventListener("release", () => { wakeLock = null; });
    return true;
  } catch { return false; }
}

function releaseWakeLock() {
  if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
}

document.addEventListener("visibilitychange", () => {
  const cook = el("cook");
  if (document.visibilityState === "visible" && !cook.hidden && !wakeLock) acquireWakeLock();
});

function cookProgress(slug, total) {
  const done = readDone(slug);
  let n = 0;
  for (const id of done) if (id.startsWith("s")) n++;
  return `${Math.min(n, total)} / ${total}`;
}

async function openCook(slug) {
  const r = BY_SLUG.get(slug);
  if (!r) return;
  const done = readDone(slug);
  const target = state.servings.get(slug) || r.servings;
  const factor = r.servings ? target / r.servings : 1;
  const total = r.steps.reduce((n, g) => n + g.steps.length, 0);

  const cook = el("cook");
  cook.hidden = false;
  cook.dataset.slug = slug;
  cook.innerHTML = `
    <div class="cook-bar">
      <button class="btn btn-ghost" type="button" data-close-cook="1">Done</button>
      <span class="cook-name">${escapeHTML(r.title)}</span>
      <span class="cook-progress" id="cook-progress">${cookProgress(slug, total)}</span>
    </div>
    <div class="cook-inner">
      ${r.shopping.length ? `<section class="section">
        <h2 class="section-name">${icon("basket")}Mise en place</h2>
        ${ingredientsHTML(r, factor, done)}</section>` : ""}
      <section class="section">
        <h2 class="section-name">${icon("list")}Method</h2>
        ${stepsHTML(r, done)}
      </section>
      <p class="cook-hint" id="cook-lock">Tap any line to strike it out.</p>
    </div>`;
  document.body.style.overflow = "hidden";

  const held = await acquireWakeLock();
  const hint = el("cook-lock");
  if (hint) {
    hint.innerHTML = held
      ? `<span class="cook-lock">Screen will stay awake.</span> Tap any line to strike it out.`
      : `Tap any line to strike it out. This browser won't hold the screen awake — set your screen timeout longer.`;
  }
}

function closeCook() {
  const cook = el("cook");
  cook.hidden = true;
  cook.innerHTML = "";
  document.body.style.overflow = "";
  releaseWakeLock();
}

/* ============================== surprise me ============================== */

function shuffle() {
  const pool = filtered();
  if (!pool.length) return;
  const pick = pool[Math.floor(Math.random() * pool.length)];
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || pool.length < 3) { location.hash = `#/r/${pick.slug}`; return; }

  const overlay = el("spin");
  const label = el("spin-text");
  overlay.hidden = false;
  let ticks = 0;
  const timer = setInterval(() => {
    label.textContent = pool[Math.floor(Math.random() * pool.length)].title;
    if (++ticks >= 9) {
      clearInterval(timer);
      label.textContent = pick.title;
      setTimeout(() => { overlay.hidden = true; location.hash = `#/r/${pick.slug}`; }, 260);
    }
  }, 65);
}

/* =============================== events =============================== */

function onFilterChip(button) {
  const { group, value } = button.dataset;
  const values = state.filters.get(group);
  if (values.has(value)) values.delete(value); else values.add(value);
  // Changing a filter means you're browsing again, so leave any open recipe.
  go("/", !currentSlug());
}

document.addEventListener("click", (event) => {
  const chip = event.target.closest(".chip[data-group]");
  if (chip) { onFilterChip(chip); return; }

  const jump = event.target.closest("[data-jump]");
  if (jump) {
    const [group, value] = jump.dataset.jump.split(":");
    for (const values of state.filters.values()) values.clear();
    state.filters.get(group).add(value);
    state.q = "";
    el("q").value = "";
    go("/");
    return;
  }

  const toggle = event.target.closest("[data-done]");
  if (toggle) {
    const slug = el("cook").hidden ? currentSlug() : el("cook").dataset.slug;
    if (!slug) return;
    const on = toggle.getAttribute("aria-pressed") !== "true";
    toggle.setAttribute("aria-pressed", String(on));
    toggleDone(slug, toggle.dataset.done, on);
    // Mirror the change into whichever copy of the recipe is also on screen.
    for (const twin of document.querySelectorAll(`[data-done="${toggle.dataset.done}"]`)) {
      twin.setAttribute("aria-pressed", String(on));
    }
    const progress = el("cook-progress");
    if (progress) {
      const r = BY_SLUG.get(slug);
      progress.textContent = cookProgress(slug, r.steps.reduce((n, g) => n + g.steps.length, 0));
    }
    return;
  }

  const scale = event.target.closest("[data-scale]");
  if (scale) {
    const slug = currentSlug();
    const r = slug && BY_SLUG.get(slug);
    if (!r || !r.servings) return;
    const next = (state.servings.get(slug) || r.servings) + Number(scale.dataset.scale);
    state.servings.set(slug, Math.max(1, Math.min(next, r.servings * 8)));
    renderRecipe(slug);
    return;
  }

  if (event.target.closest("[data-cook]")) {
    const slug = currentSlug();
    if (slug) openCook(slug);
    return;
  }
  if (event.target.closest("[data-close-cook]")) { closeCook(); return; }
  if (event.target.closest("[data-action='reset']")) {
    state.q = "";
    el("q").value = "";
    for (const values of state.filters.values()) values.clear();
    go("/");
  }
});

el("q").addEventListener("input", (event) => {
  state.q = event.target.value.trim();
  if (currentSlug()) { location.hash = hashFor("/"); return; }
  // Stay put and repaint in place, so the caret and focus survive each keystroke.
  history.replaceState(null, "", hashFor("/"));
  renderFilters();
  renderList();
});

el("filter-toggle").addEventListener("click", (event) => {
  const open = el("filters").classList.toggle("is-open");
  event.currentTarget.setAttribute("aria-expanded", String(open));
});

el("clear-filters").addEventListener("click", () => {
  state.q = "";
  el("q").value = "";
  for (const values of state.filters.values()) values.clear();
  go("/");
  render();
});

el("shuffle").addEventListener("click", shuffle);

el("theme").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "ink" ? "paper" : "ink";
  applyTheme(next);
  save("recipes:theme", next);
});

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  el("theme-label").textContent = theme === "ink" ? "Paper" : "Ink";
  el("theme").setAttribute("aria-label",
    theme === "ink" ? "Switch to the paper theme" : "Switch to the ink theme");
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === "ink" ? "#16130F" : "#EDE6D8";
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!el("cook").hidden) { closeCook(); return; }
    if (document.activeElement === el("q")) el("q").blur();
    return;
  }
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  if (event.key === "/" && !typing) { event.preventDefault(); el("q").focus(); }
});

window.addEventListener("hashchange", render);

/* =============================== bootstrap =============================== */

function render() {
  const path = readHash();
  if (el("q").value !== state.q) el("q").value = state.q;
  renderFilters();

  const isRecipe = path.startsWith("/r/");
  $(".shell").classList.toggle("is-recipe", isRecipe);
  el("filters").hidden = isRecipe;
  el("filters").classList.remove("is-open");
  el("filter-toggle").setAttribute("aria-expanded", "false");

  if (isRecipe) {
    if (el("list-view").hidden === false) listScroll = window.scrollY;
    if (!el("cook").hidden) closeCook();
    renderRecipe(decodeURIComponent(path.slice(3)));
    window.scrollTo(0, 0);
  } else {
    const wasRecipe = el("recipe-view").hidden === false;
    renderList();
    if (wasRecipe) window.scrollTo(0, listScroll);
  }
}

async function boot() {
  applyTheme(store("recipes:theme", "ink"));

  const [data, sprite] = await Promise.all([
    fetch(DATA_URL, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${DATA_URL} returned ${r.status}`);
      return r.json();
    }),
    fetch(SPRITE_URL).then((r) => (r.ok ? r.text() : "")).catch(() => ""),
  ]);

  if (sprite) {
    el("sprite").innerHTML = sprite;
    for (const symbol of el("sprite").querySelectorAll("symbol")) SPRITE_IDS.add(symbol.id);
  }

  DATA = data;
  buildIndex(DATA.recipes);
  BY_SLUG = new Map(DATA.recipes.map((r) => [r.slug, r]));
  SLUG_OF_TITLE = new Map(DATA.recipes.map((r) => [r.title, r.slug]));
  el("brand-count").textContent = String(DATA.count).padStart(3, "0");

  render();
}

boot().catch((error) => {
  console.error(error);
  el("results").innerHTML =
    `<li class="stub"><p class="stub-sum">Couldn't load the recipe data (${escapeHTML(error.message)}).
     If you're opening index.html straight from disk, serve the folder over HTTP instead —
     <code>py -m http.server</code> in the project root.</p></li>`;
});

if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("sw.js").catch(() => {}));
}
