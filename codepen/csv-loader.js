const NUK_COURSE_CSV_URL =
  "https://raw.githubusercontent.com/114961062-lab/NUKCourseData/main/data/nuk_courses_1151.csv";

async function loadNukCourseCsv() {
  const response = await fetch(
    `${NUK_COURSE_CSV_URL}?v=${Date.now()}`,
    { cache: "no-store" }
  );

  if (!response.ok) {
    throw new Error(`GitHub CSV讀取失敗：HTTP ${response.status}`);
  }

  const text = await response.text();
  const rows = parseNukCsv(text);

  if (!rows.length) {
    throw new Error("GitHub CSV沒有課程資料");
  }

  return rows.map(row => ({
    ...row,
    credits: Number(row.credits || 0),
    capacity: toNumberOrNull(row.capacity),
    confirmed: toNumberOrNull(row.confirmed),
    enrolled: toNumberOrNull(row.enrolled),
    remaining: toNumberOrNull(row.remaining),
    schedule: safeJson(row.scheduleJson, [])
  }));
}

function toNumberOrNull(value) {
  if (value === "" || value == null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function safeJson(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function parseNukCsv(csvText) {
  const text = String(csvText || "").replace(/^\uFEFF/, "");
  const table = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (quoted) {
      if (char === '"' && next === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      table.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }

  if (field || row.length) {
    row.push(field.replace(/\r$/, ""));
    table.push(row);
  }

  const headers = table.shift() || [];
  return table
    .filter(columns => columns.some(value => String(value).trim()))
    .map(columns => Object.fromEntries(
      headers.map((header, index) => [header.trim(), String(columns[index] ?? "").trim()])
    ));
}
