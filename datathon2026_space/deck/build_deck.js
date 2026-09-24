// Project HIGH GROUND - Theme 6.1 presentation deck (PowerPoint), built from the analysis outputs.
// Usage: cd deck && node build_deck.js      (reads deck_data.json written from data/metrics.json and tables/*.csv)
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa6");
const fs = require("fs");

const D = JSON.parse(fs.readFileSync("deck_data.json", "utf8"));
const M = D.M;
const NAVY = "0B1D3A", STEEL = "2F5D8C", GOLD = "D99A1E", RED = "C0392B", INK = "1B2433", MUTED = "5B6573",
  TINT = "EEF2F7", WHITE = "FFFFFF", GREEN = "2E7D32", AMBER = "E08A00", GREY = "9AA3AE";
const HEAD = "Cambria", BODY = "Calibri";
const TOTAL = 17;
const pct = (x, d = 0) => (x * 100).toFixed(d) + "%";
const fmt = (n) => Number(n).toLocaleString("en-US");

async function icon(Comp, color) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: 256 }));
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";            // 13.33 x 7.5 in
  pres.author = "Arjun Jayadev";
  pres.title = "Project High Ground - CDM Datathon-2026 Theme 6.1";
  const I = {};
  for (const [k, c] of Object.entries({ sat: fa.FaSatellite, flag: fa.FaFlag, burst: fa.FaBurst, eye: fa.FaEye, sun: fa.FaSun,
    chart: fa.FaChartLine, shield: fa.FaShieldHalved, earth: fa.FaEarthAsia, anchor: fa.FaAnchor, jet: fa.FaJetFighterUp,
    army: fa.FaPersonMilitaryRifle, db: fa.FaDatabase, fire: fa.FaFire, rocket: fa.FaRocket, user: fa.FaUserShield,
    dish: fa.FaSatelliteDish, bolt: fa.FaBolt, check: fa.FaCircleCheck })) {
    I[k] = await icon(c, WHITE);
  }

  const footer = (s, n, dark = false) => {
    const col = dark ? "AEB9C8" : MUTED;
    s.addText("PROJECT HIGH GROUND  ·  CDM Datathon-2026  ·  Theme 6.1", { x: 0.6, y: 7.0, w: 8, h: 0.3, fontFace: BODY, fontSize: 10, color: col, margin: 0, isTextBox: true });
    s.addText(`${n} / ${TOTAL}`, { x: 11.73, y: 7.0, w: 1.0, h: 0.3, fontFace: BODY, fontSize: 10, color: col, align: "right", margin: 0, isTextBox: true });
  };
  const heading = (s, eyebrow, title) => {
    s.addText(eyebrow.toUpperCase(), { x: 0.6, y: 0.4, w: 12, h: 0.3, fontFace: BODY, fontSize: 12, bold: true, color: GOLD, charSpacing: 2, margin: 0, isTextBox: true });
    s.addText(title, { x: 0.6, y: 0.72, w: 12.1, h: 0.75, fontFace: HEAD, fontSize: 28, bold: true, color: NAVY, margin: 0, isTextBox: true, valign: "top" });
  };
  const circle = (s, img, x, y, d, fill) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
    s.addImage({ data: img, x: x + d * 0.22, y: y + d * 0.22, w: d * 0.56, h: d * 0.56 });
  };
  const stat = (s, x, y, w, num, label, color = RED) => {
    s.addText(num, { x, y, w, h: 0.62, fontFace: HEAD, fontSize: 36, bold: true, color, margin: 0, isTextBox: true, valign: "bottom" });
    s.addText(label, { x, y: y + 0.66, w, h: 0.62, fontFace: BODY, fontSize: 13, color: MUTED, margin: 0, isTextBox: true, valign: "top" });
  };
  const card = (s, x, y, w, h, fill = TINT) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08 });
  const axis = { catAxisLabelColor: MUTED, valAxisLabelColor: MUTED, catAxisLabelFontFace: BODY, valAxisLabelFontFace: BODY,
    catAxisLabelFontSize: 10, valAxisLabelFontSize: 10, valGridLine: { color: "E3E6EA", size: 0.5 }, catGridLine: { style: "none" },
    titleFontFace: BODY, titleFontSize: 13, titleColor: INK, showTitle: true };

  // 1 ---------------------------------------------------------------- title
  let s = pres.addSlide();
  s.background = { color: NAVY };
  circle(s, I.sat, 0.6, 0.6, 0.9, STEEL);
  s.addText("CDM DATATHON-2026  ·  THEME 6.1  ·  CONTESTED AND CONGESTED", { x: 1.7, y: 0.78, w: 11, h: 0.5, fontFace: BODY, fontSize: 14, bold: true, color: GOLD, charSpacing: 2, margin: 0, isTextBox: true });
  s.addText("Project High Ground", { x: 0.6, y: 2.0, w: 12, h: 1.3, fontFace: HEAD, fontSize: 60, bold: true, color: WHITE, margin: 0, isTextBox: true });
  s.addText("The crowding of orbit, and what it means for India and the Indian Armed Forces", { x: 0.6, y: 3.35, w: 11.5, h: 0.9, fontFace: HEAD, fontSize: 24, italic: true, color: "D9DEE7", margin: 0, isTextBox: true });
  s.addText([{ text: "[Rank] Arjun Jayadev", options: { bold: true, color: WHITE, breakLine: true } },
    { text: "[Service No]  ·  [Unit / Formation]", options: { color: "AEB9C8", breakLine: true } },
    { text: "College of Defence Management  ·  2026", options: { color: "AEB9C8" } }],
    { x: 0.6, y: 5.0, w: 8, h: 1.2, fontFace: BODY, fontSize: 16, margin: 0, isTextBox: true, paraSpaceAfter: 4 });
  s.addNotes("Sir, my study takes the CDM satellite data and asks five questions: how crowded orbit has become, who owns it, how dangerous it is, who is building military eyes in it, and what India should do. About fifteen minutes, then questions.");

  // 2 ---------------------------------------------------------------- BLUF
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Bottom line up front", "Orbit is crowded, concentrated and contested");
  const bl = [["sat", `${M.active_mult.toFixed(0)}×`, `working satellites since 2014: ${fmt(M.active_2014)} to ${fmt(M.active_now)}`],
    ["burst", `×${M.risk_ratio.toFixed(0)}`, "collision-risk index in low orbit, against 2014"],
    ["eye", `${M.cn_isr_ops} : ${M.in_isr_ops}`, "state ISR and military satellites, China : India"]];
  bl.forEach(([ic, n, l], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 1.9, 3.8, 3.3);
    circle(s, I[ic], x + 0.35, 2.2, 0.75, NAVY);
    s.addText(n, { x: x + 0.35, y: 3.1, w: 3.2, h: 0.9, fontFace: HEAD, fontSize: 44, bold: true, color: RED, margin: 0, isTextBox: true });
    s.addText(l, { x: x + 0.35, y: 4.05, w: 3.2, h: 0.9, fontFace: BODY, fontSize: 15, color: INK, margin: 0, isTextBox: true, valign: "top" });
  });
  s.addText([{ text: "Decision sought: ", options: { bold: true, color: NAVY } },
    { text: "a four-month ORBITWATCH proof of concept at the Defence Space Agency, using the open catalogue and the pipeline already built.", options: { color: INK } }],
    { x: 0.6, y: 5.6, w: 12.1, h: 0.8, fontFace: BODY, fontSize: 17, margin: 0, isTextBox: true });
  footer(s, 2);
  s.addNotes(`Three numbers carry the study. Working satellites rose ${M.active_mult.toFixed(0)}-fold in twelve years. Collision risk in low orbit is about ten times the 2014 level. And China operates about ${M.cn_isr_ops} state intelligence and military satellites to India's ${M.in_isr_ops}. India's share of working satellites has fallen to ${M.in_share_now.toFixed(1)} percent. Everything that follows is the evidence, and at the end one decision.`);

  // 3 ---------------------------------------------------------------- question and data
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Defining the problem · data", "Five questions, seven sources of evidence");
  const qs = ["How crowded has orbit become since 2014?", "Whose satellites are they, and what are they for?", "Where is orbit crowded, and how dangerous is it?",
    "Who is building military eyes in orbit?", "What should India and its Armed Forces do?"];
  qs.forEach((q, i) => {
    circle(s, I.check, 0.6, 1.85 + i * 0.85, 0.5, NAVY);
    s.addText(q, { x: 1.25, y: 1.85 + i * 0.85, w: 5.2, h: 0.5, fontFace: BODY, fontSize: 16, color: INK, margin: 0, isTextBox: true, valign: "middle" });
  });
  const src = [["db", "CDM satellite census", `${fmt(M.cdm_n)} active satellites, Jan 2014`], ["sun", "CDM space weather", `${fmt(M.dst_n)} hours of Dst + sunspots`],
    ["fire", "CDM MODIS fires", `${(M.fires_n / 1e6).toFixed(2)} million detections, 2010-20`], ["sat", "Satellite catalogue (open)", `${fmt(M.satcat_n)} objects to ${M.satcat_last}`],
    ["earth", "UCS 2020 + UNOOSA (open)", "second census; launches by country"], ["dish", "Official and news", "ISRO, PIB, ESA, NOAA, 2024-26"]];
  src.forEach(([ic, t, d], i) => {
    const x = 6.9 + (i % 2) * 3.0, y = 1.85 + Math.floor(i / 2) * 1.45;
    card(s, x, y, 2.8, 1.3);
    circle(s, I[ic], x + 0.15, y + 0.15, 0.45, i < 3 ? RED : STEEL);
    s.addText(t, { x: x + 0.7, y: y + 0.12, w: 2.0, h: 0.5, fontFace: BODY, fontSize: 12.5, bold: true, color: NAVY, margin: 0, isTextBox: true, valign: "middle" });
    s.addText(d, { x: x + 0.15, y: y + 0.7, w: 2.55, h: 0.5, fontFace: BODY, fontSize: 11.5, color: MUTED, margin: 0, isTextBox: true, valign: "top" });
  });
  footer(s, 3);
  s.addNotes("The theme asks for insights into satellite proliferation and a prediction of the trajectory. I turned that into five questions a commander would ask. The CDM data give the 2014 baseline, space weather and a real example of what satellites see. The open catalogue brings the picture to September 2026. Every number is regenerated from raw data by one command.");

  // 4 ---------------------------------------------------------------- the crowd
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Finding 1 · the crowd", `${M.active_mult.toFixed(0)} times more working satellites in twelve years`);
  s.addChart(pres.charts.BAR, [{ name: "Working satellites", labels: D.censuses.map((c) => c[0]), values: D.censuses.map((c) => c[1]) }],
    { x: 0.6, y: 1.7, w: 4.6, h: 4.9, barDir: "col", chartColors: [STEEL], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12,
      dataLabelColor: INK, dataLabelFormatCode: "#,##0", valAxisLabelFormatCode: "#,##0", showLegend: false, title: "Working satellites, three censuses", ...axis });
  s.addChart(pres.charts.BAR, [{ name: "Other satellites", labels: D.years, values: D.pay_other }, { name: "Starlink", labels: D.years, values: D.pay_starlink }],
    { x: 5.4, y: 1.7, w: 7.3, h: 4.1, barDir: "col", barGrouping: "stacked", chartColors: [STEEL, RED], showLegend: true, legendPos: "t", legendFontSize: 10,
      valAxisLabelFormatCode: "#,##0", title: "Satellites launched per year (2026 to 21 Sep)", ...axis });
  s.addText(`Growth changed gear in ${M.growth_cps[0]}: ${M.cagr_2000_2013.toFixed(0)}% a year before, ${M.cagr_2019_2025.toFixed(0)}% after. One constellation now holds ${pct(M.starlink_share)} of working satellites.`,
    { x: 5.4, y: 5.95, w: 7.3, h: 0.75, fontFace: BODY, fontSize: 14, color: INK, margin: 0, isTextBox: true });
  footer(s, 4);
  s.addNotes(`Three independent counts: the CDM census of 2014, the UCS database of 2020, and today's catalogue. From ${fmt(M.active_2014)} to ${fmt(M.active_now)}. A change-point test puts the break around ${M.growth_cps[0]}, when the mega-constellations began. Satellites launched a year went from ${M.pay_2013} in 2013 to ${fmt(M.pay_2025)} in 2025. UN registrations match the catalogue almost exactly, so the count is sound.`);

  // 5 ---------------------------------------------------------------- owners
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Finding 2 · who owns orbit", "One country and one company own most of orbit");
  s.addChart(pres.charts.BAR, [{ name: "Jan 2014", labels: D.country, values: D.share14 }, { name: "Sep 2026", labels: D.country, values: D.share26 }],
    { x: 0.6, y: 1.7, w: 7.4, h: 5.0, barDir: "col", barGrouping: "clustered", chartColors: [GREY, NAVY], showValue: true, dataLabelPosition: "outEnd",
      dataLabelFontSize: 10, dataLabelColor: INK, dataLabelFormatCode: "0.0", showLegend: true, legendPos: "t", legendFontSize: 11,
      valAxisTitle: "% of working satellites", showValAxisTitle: true, valAxisTitleFontSize: 10, valAxisTitleColor: MUTED, title: "Share of working satellites by country (%)", ...axis });
  stat(s, 8.5, 1.9, 4.2, `${M.us_share_now.toFixed(0)}%`, `of working satellites are US-operated (${M.us_share_2014.toFixed(0)}% in 2014)`, NAVY);
  stat(s, 8.5, 3.45, 4.2, `${fmt(M.hhi_country_now)}`, `concentration index (HHI); above 2,500 = highly concentrated. 2014: ${fmt(M.hhi_country_2014)}`, NAVY);
  stat(s, 8.5, 5.0, 4.2, `${M.in_share_now.toFixed(1)}%`, `India's share: ${M.in_2014} satellites (2.8%) in 2014, ${M.in_now} today`);
  footer(s, 5);
  s.addNotes(`Control of orbit is concentrating. The USA went from ${M.us_share_2014.toFixed(0)} to ${M.us_share_now.toFixed(0)} percent of working satellites, mostly one company. China grew thirteen-fold in numbers but held its share near ten percent. India grew from ${M.in_2014} to ${M.in_now} satellites, but its share fell from 2.8 to ${M.in_share_now.toFixed(1)} percent. The concentration index is more than double the 'highly concentrated' threshold.`);

  // 6 ---------------------------------------------------------------- congestion
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Finding 3 · where it is crowded", `A live crowd, a dead crowd, and collision risk ×${M.risk_ratio.toFixed(0)}`);
  s.addChart(pres.charts.BAR, [{ name: "Working satellites", labels: D.shells, values: D.sh_active }, { name: "Debris", labels: D.shells, values: D.sh_debris },
    { name: "Dead satellites and rocket bodies", labels: D.shells, values: D.sh_other }],
    { x: 0.6, y: 1.7, w: 8.2, h: 5.0, barDir: "col", barGrouping: "stacked", barGapWidthPct: 20, chartColors: [STEEL, RED, GREY], showLegend: true, legendPos: "t",
      legendFontSize: 10, catAxisLabelFrequency: 4, valAxisLabelFormatCode: "#,##0", title: "Objects in low orbit by altitude (km, 25 km shells), Sep 2026", ...axis });
  stat(s, 9.2, 1.9, 3.6, fmt(M.band_now), `objects at 450-500 km, ${pct(M.band_active_share)} working (${M.band_2014} in 2014)`, STEEL);
  stat(s, 9.2, 3.45, 3.6, fmt(M.dead_now), `objects at 750-900 km, ${pct(M.dead_debris_share)} of them debris`, RED);
  stat(s, 9.2, 5.0, 3.6, `${M.geo_arc20}`, `GEO satellites in India's 40-110 E arc, ${pct(M.geo_arc_share20)} of the belt`, NAVY);
  footer(s, 6);
  s.addNotes(`Orbit is crowded in two places. The live crowd at 450 to 500 kilometres, almost all working satellites. The dead crowd at 750 to 900 kilometres, mostly debris from the 2007 Chinese test and the 2009 collision. Collisions grow with the square of the number of objects at each height, so the collision-risk index is about ${M.risk_ratio.toFixed(0)} times its 2014 level. Higher up, the geostationary arc India uses holds ${M.geo_arc20} satellites; China and the USA each have more there than India.`);

  // 7 ---------------------------------------------------------------- weapon debris
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Finding 4 · weapon tests", "Altitude decides how long weapon debris stays");
  s.addChart(pres.charts.BAR, [{ name: "Still in orbit %", labels: D.asat.map((a) => `${a[0]} (${a[1]})`), values: D.asat.map((a) => a[3]) }],
    { x: 0.6, y: 1.7, w: 7.6, h: 5.0, barDir: "bar", chartColors: [RED], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: INK,
      dataLabelFormatCode: "0.0", showLegend: false, valAxisMaxVal: 100, catAxisLabelFontSize: 10, title: "Share of catalogued debris still in orbit, Sep 2026 (%)", ...axis });
  const asatRows = [[{ text: "Event", options: { bold: true, color: WHITE, fill: { color: NAVY } } }, { text: "Pieces", options: { bold: true, color: WHITE, fill: { color: NAVY } } },
    { text: "Left", options: { bold: true, color: WHITE, fill: { color: NAVY } } }]].concat(D.asat.map((a) => [a[0], fmt(a[2]), `${a[3]}%`]));
  s.addTable(asatRows, { x: 8.5, y: 1.8, w: 4.2, colW: [2.5, 0.85, 0.85], fontFace: BODY, fontSize: 10.5, color: INK, border: { type: "solid", color: "D5DAE1", pt: 0.5 }, rowH: 0.36 });
  s.addText(`India's 2019 test at ~280 km: all ${M.shakti_pieces} pieces re-entered. China's 2007 test at ~865 km: ${M.fy1c_alive_pct.toFixed(0)}% still in orbit after 20 years.`,
    { x: 8.5, y: 4.85, w: 4.2, h: 1.4, fontFace: BODY, fontSize: 14, color: INK, margin: 0, isTextBox: true });
  footer(s, 7);
  s.addNotes("Six events, one lesson. China's 2007 test at high altitude made over three and a half thousand tracked pieces, and two thirds are still up nearly twenty years later. India's 2019 test was done low; every piece re-entered, most within half a year. Russia's 2021 test has almost cleared. A responsible test is a low one, and India can say so with data.");

  // 8 ---------------------------------------------------------------- the contest
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Finding 5 · the contest", "China and the USA build eyes by the hundred");
  s.addChart(pres.charts.BAR, [{ name: "Operational", labels: ["USA", "China", "Russia", "India", "India + SBS-III (2029)"],
    values: [M.us_isr_ops, M.cn_isr_ops, M.ru_isr_ops, M.in_isr_ops, M.in_isr_ops + 52] }],
    { x: 0.6, y: 1.7, w: 7.4, h: 5.0, barDir: "bar", chartColors: [NAVY], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: INK,
      showLegend: false, title: "Military, state-ISR and imaging satellites working, Sep 2026 (name-based lower bound)", ...axis });
  stat(s, 8.5, 1.9, 4.2, `${M.cn_isr_rate_2023_25.toFixed(0)} a year`, "Chinese state-ISR satellites launched, 2023-25 average (India: under one)");
  stat(s, 8.5, 3.45, 4.2, `${pct(M.sbs3_close)}`, "of today's China-India gap closed by SBS-III's 52 satellites (due 2029)");
  stat(s, 8.5, 5.0, 4.2, `${M.us_nnn_2024_26}`, "US national-security payloads launched since 2024", NAVY);
  footer(s, 8);
  s.addNotes(`Grouping satellites by official programme names gives a transparent lower bound. China operates about ${M.cn_isr_ops}, including ${M.yaogan_ops} Yaogan reconnaissance satellites, and adds about ${M.cn_isr_rate_2023_25.toFixed(0)} a year. India operates about ${M.in_isr_ops}. SBS-III is the right answer but closes only about ${pct(M.sbs3_close)} of today's gap. During Operation Sindoor ten Indian satellites worked round the clock: the need is proven, the capacity is thin.`);

  // 9 ---------------------------------------------------------------- space weather
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Finding 6 · the natural adversary", `Storm odds rise ~${M.storm_mult.toFixed(0)}-fold when the Sun is active`);
  s.addChart(pres.charts.BAR, [{ name: "Intense storms per 30 days", labels: D.storm_bands, values: D.storm_vals }],
    { x: 0.6, y: 1.7, w: 5.0, h: 5.0, barDir: "col", chartColors: [GOLD], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: INK,
      dataLabelFormatCode: "0.00", showLegend: false, catAxisTitle: "smoothed sunspot number", showCatAxisTitle: true, catAxisTitleFontSize: 10, catAxisTitleColor: MUTED,
      title: "Intense storms per 30 days (CDM Dst data)", ...axis });
  s.addChart(pres.charts.LINE, [{ name: "Re-entry rate %", labels: D.rr_years, values: D.rr_vals }],
    { x: 5.8, y: 1.7, w: 6.9, h: 3.3, chartColors: [STEEL], lineSize: 2, lineDataSymbol: "none", showLegend: false, catAxisLabelFrequency: 10,
      title: `Low-orbit debris re-entering per year (%): a ${M.reentry_period.toFixed(0)}-year cycle`, ...axis });
  s.addText([{ text: `${pct(M.p_intense_hi)} vs ${pct(M.p_intense_lo)}`, options: { bold: true, color: RED, breakLine: true } },
    { text: "chance of an intense storm in any 30 days, active vs quiet Sun. Storms killed 38 new Starlink satellites (Feb 2022); solar cycle 25 peaked in Oct 2024.", options: { color: INK } }],
    { x: 5.8, y: 5.2, w: 6.9, h: 1.5, fontFace: BODY, fontSize: 14, margin: 0, isTextBox: true, paraSpaceAfter: 4 });
  footer(s, 9);
  s.addNotes(`The Sun is the adversary nobody can deter. In the CDM records, when sunspots are high, the chance of an intense magnetic storm in a month is ${pct(M.p_intense_hi)}; when quiet, ${pct(M.p_intense_lo)}. A Poisson model gives ${M.storm_irr50} times the rate per 50 sunspots. A periodogram of debris re-entries finds a ${M.reentry_period.toFixed(0)}-year cycle on its own: the solar cycle heats the upper atmosphere and drags objects down.`);

  // 10 --------------------------------------------------------------- what eyes buy
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Finding 7 · what eyes in orbit buy", "Two satellites saw what one would have missed");
  s.addImage({ path: "f7_2_fire_map.png", x: 0.6, y: 1.75, w: 6.6, h: 6.6 * 1030 / 2585, sizing: { type: "contain", w: 6.6, h: 2.63 } });
  s.addText(`${(M.fires_n / 1e6).toFixed(2)} million fire and heat detections by NASA's Terra and Aqua over the USA, 2010-2020 (CDM data)`,
    { x: 0.6, y: 4.45, w: 6.6, h: 0.5, fontFace: BODY, fontSize: 11, italic: true, color: MUTED, margin: 0, isTextBox: true });
  s.addChart(pres.charts.DOUGHNUT, [{ name: "Fire-days", labels: D.prem.map((p) => p[0]), values: D.prem.map((p) => p[1]) }],
    { x: 7.5, y: 1.7, w: 5.2, h: 3.4, chartColors: [STEEL, GOLD, NAVY], showPercent: true, showLegend: true, legendPos: "r", legendFontSize: 11,
      dataLabelColor: WHITE, dataLabelFontSize: 11, holeSize: 55, title: "Who saw each fire-day (10 km grid)", showTitle: true, titleFontSize: 13, titleColor: INK, titleFontFace: BODY });
  stat(s, 0.6, 5.1, 3.8, pct(M.prem_single), "of fire-days seen by only one of the two satellites");
  stat(s, 4.6, 5.1, 3.8, pct(M.night_share), "of detections at night: thermal sensors see in the dark", NAVY);
  stat(s, 8.6, 5.1, 4.1, `${M.industrial_cells}`, "persistent industrial heat sources found (steel mills, smelters)", NAVY);
  footer(s, 10);
  s.addNotes(`Why take all this risk? Because of what satellites see. Terra passes in the morning, Aqua in the afternoon. On a ten-kilometre grid, ${pct(M.prem_single)} of fire-days were seen by only one of them: a single satellite would have missed nearly half. For the Services the lesson is direct: persistence comes from numbers, and revisit decides whether a mobilisation or a launcher is caught in time.`);

  // 11 --------------------------------------------------------------- trajectory
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Prediction · the trajectory to 2030", `About ${(M.sc_base / 1000).toFixed(0)},000 working satellites by 2030`);
  s.addChart(pres.charts.LINE, [{ name: "Payloads in orbit (catalogue)", labels: D.pop_years, values: D.pop_actual },
    { name: "Statistical trend (damped)", labels: D.pop_years, values: D.pop_fc }],
    { x: 0.6, y: 1.7, w: 6.6, h: 3.6, chartColors: [STEEL, RED], lineSize: 2.5, lineDataSymbol: "none", showLegend: true, legendPos: "t", legendFontSize: 10,
      catAxisLabelFrequency: 5, valAxisLabelFormatCode: "#,##0", title: "Satellites in orbit, 2000-2030", ...axis });
  s.addChart(pres.charts.BAR, [{ name: "Index", labels: D.risk.map((r) => r[0]), values: D.risk.map((r) => r[1]) }],
    { x: 7.4, y: 1.7, w: 5.3, h: 3.6, barDir: "col", chartColors: [NAVY], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: INK,
      dataLabelFormatCode: "0.0", showLegend: false, title: "Collision-risk index, low orbit (2014 = 1)", ...axis });
  const sc = [[{ text: "Scenario 2030", options: { bold: true, color: WHITE, fill: { color: NAVY } } }, ...["Starlink", "Kuiper", "Guowang", "Qianfan", "Others", "Total"].map((h) => ({ text: h, options: { bold: true, color: WHITE, fill: { color: NAVY } } }))]]
    .concat(D.scen.map((r) => r.map((v, i) => (i === 0 ? v : fmt(v)))));
  s.addTable(sc, { x: 0.6, y: 5.45, w: 12.1, fontFace: BODY, fontSize: 11, color: INK, border: { type: "solid", color: "D5DAE1", pt: 0.5 }, rowH: 0.3, align: "center" });
  footer(s, 11);
  s.addNotes(`Two routes agree. A damped-trend forecast reaches about ${fmt(M.fc_2030_mid)} satellites in orbit by 2030; tested on held-back years it erred by ${M.fc_bt_mape} percent. A bottom-up build from the announced constellations gives ${fmt(M.sc_low)}, ${fmt(M.sc_base)} or ${fmt(M.sc_high)} working satellites. The collision-risk index rises to about ${M.risk_2030_base.toFixed(0)} times the 2014 level in the base case. China's planned shells at 1,050 to 1,200 kilometres are the concern: debris there stays for centuries.`);

  // 12 --------------------------------------------------------------- how sure
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Inference · how sure are we", "Every finding survives an independent check");
  const rob = [[{ text: "Finding", options: { bold: true, color: WHITE, fill: { color: NAVY } } }, { text: "Result", options: { bold: true, color: WHITE, fill: { color: NAVY } } },
    { text: "Independent check", options: { bold: true, color: WHITE, fill: { color: NAVY } } }, { text: "Verdict", options: { bold: true, color: WHITE, fill: { color: NAVY } } }]]
    .concat(D.rob.map((r) => [r[0], r[1], r[2], { text: r[3], options: { bold: true, color: GREEN } }]));
  s.addTable(rob, { x: 0.6, y: 1.8, w: 12.1, colW: [2.0, 3.2, 5.1, 1.8], fontFace: BODY, fontSize: 12, color: INK, border: { type: "solid", color: "D5DAE1", pt: 0.5 }, valign: "middle" });
  footer(s, 12);
  s.addNotes("Before a commander acts, he asks how sure we are. Each headline was checked by a second source or a second method: UN registrations for growth, a second shell size for congestion, a sensitivity test for the intelligence count, two statistical tests for storms, and a back-test for the forecast. The intelligence count is a lower bound: covert satellites would only widen the gap.");

  // 13 --------------------------------------------------------------- impact
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Impact · India and the Armed Forces", "India depends on space, but holds less of it");
  const sco = [[{ text: "Measure", options: { bold: true, color: WHITE, fill: { color: NAVY } } }, ...["India", "China", "USA"].map((h) => ({ text: h, options: { bold: true, color: WHITE, fill: { color: NAVY } } }))]]
    .concat(D.score.map((r) => [r[0], ...r.slice(1).map((v) => (v === "-" ? "-" : fmt(v)))]));
  s.addTable(sco, { x: 0.6, y: 1.8, w: 6.2, colW: [3.5, 0.9, 0.9, 0.9], fontFace: BODY, fontSize: 12, color: INK, border: { type: "solid", color: "D5DAE1", pt: 0.5 }, rowH: 0.45 });
  const svc = [["anchor", "Navy", "Ocean surveillance rests on radar and AIS satellites; assume carrier groups are tracked."],
    ["jet", "Air Force", "Precision strike needs NavIC and fresh imagery; storms degrade GNSS and HF."],
    ["army", "Army", `Northern border under persistent ISR (${M.cn_isr_ops} Chinese satellites): concealment and deception.`],
    ["user", "Joint / DSA", "ORBITWATCH, SBS-III at pace, manoeuvrable storm-hardened satellites."]];
  svc.forEach(([ic, h, t], i) => {
    const y = 1.8 + i * 1.2;
    circle(s, I[ic], 7.2, y, 0.6, [NAVY, STEEL, "7B3B2E", GOLD][i]);
    s.addText(h, { x: 7.95, y, w: 4.7, h: 0.35, fontFace: BODY, fontSize: 15, bold: true, color: NAVY, margin: 0, isTextBox: true });
    s.addText(t, { x: 7.95, y: y + 0.36, w: 4.7, h: 0.7, fontFace: BODY, fontSize: 12.5, color: INK, margin: 0, isTextBox: true, valign: "top" });
  });
  s.addText(`Access to space is the bottleneck: China averaged about ${M.launch_ratio.toFixed(0)} times India's launch rate over 2021-25.`,
    { x: 0.6, y: 5.0, w: 6.2, h: 0.9, fontFace: BODY, fontSize: 14, color: INK, margin: 0, isTextBox: true });
  footer(s, 13);
  s.addNotes("For India the problem is structural: rising dependence on space for banking, navigation, communications and warning, a falling share of working satellites, and a launch rate far behind China's. For the Services: plan on being watched, and plan on losing some space services in war.");

  // 14 --------------------------------------------------------------- ORBITWATCH
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Warning · ORBITWATCH", `Seven indicators: ${M.ow_red} Red, ${M.ow_amber} Amber (Sep 2026)`);
  D.ow.forEach((r, i) => {
    const x = 0.6 + (i % 4) * 3.05, y = 1.85 + Math.floor(i / 4) * 2.45;
    const col = r[5] === "RED" ? RED : r[5] === "AMBER" ? AMBER : GREEN;
    card(s, x, y, 2.85, 2.2);
    s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + 0.22, w: 0.3, h: 0.3, fill: { color: col }, line: { color: col } });
    s.addText(r[5], { x: x + 0.6, y: y + 0.2, w: 2.0, h: 0.35, fontFace: BODY, fontSize: 12, bold: true, color: col, margin: 0, isTextBox: true, valign: "middle" });
    s.addText(String(r[2]), { x: x + 0.2, y: y + 0.62, w: 2.5, h: 0.55, fontFace: HEAD, fontSize: 24, bold: true, color: col, margin: 0, isTextBox: true });
    s.addText(r[0].slice(3), { x: x + 0.2, y: y + 1.2, w: 2.5, h: 0.9, fontFace: BODY, fontSize: 11, color: INK, margin: 0, isTextBox: true, valign: "top" });
  });
  s.addText("Each indicator has Amber and Red thresholds and an action on Red, updated from open data.", { x: 9.75, y: 4.3, w: 2.85, h: 2.2, fontFace: BODY, fontSize: 14, italic: true, color: MUTED, margin: 0, isTextBox: true, valign: "middle" });
  footer(s, 14);
  s.addNotes("The study becomes a standing monitor. Seven indicators, each with thresholds and an action on Red. Today six are Red: collision risk, growth rate, Chinese ISR build rate, India's share, storm odds, and crowding of our geostationary arc. The anti-satellite test indicator is Amber.");

  // 15 --------------------------------------------------------------- way forward
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Way forward", "Seven actions, each with a lead and a timeline");
  const acts = [["Stand up ORBITWATCH: weekly space picture and warning matrix", "DSA, ISRO NETRA", "4 months"],
    ["Accelerate SBS-III; buy commercial imagery and radar capacity", "DSA, NSIL, industry", "2026-29"],
    ["Manoeuvre capability, fuel and storm hardening on every new military satellite", "DSA, ISRO, DRDO", "From 2027"],
    ["Space-weather cell; drills for degraded GNSS and HF", "HQ IDS, IAF Met", "6 months"],
    ["Rapid reconstitution: SSLV slots and spare satellites on standby", "ISRO, NSIL, DSA", "2-3 years"],
    ["Protect GEO slots and ITU filings in the 40-110 E arc", "DoT, ISRO, DSA", "Ongoing"],
    ["Concealment and deception doctrine against persistent ISR", "Army, HQ IDS", "12 months"]];
  const hdr = ["Action", "Lead", "When"].map((h) => ({ text: h, options: { bold: true, color: WHITE, fill: { color: NAVY } } }));
  s.addTable([hdr].concat(acts), { x: 0.6, y: 1.8, w: 12.1, colW: [7.6, 2.8, 1.7], fontFace: BODY, fontSize: 14, color: INK, border: { type: "solid", color: "D5DAE1", pt: 0.5 }, rowH: 0.58, valign: "middle" });
  footer(s, 15);
  s.addNotes("Seven actions from the booklet, each with a lead, a timeline and a measure of success. The first costs almost nothing: the open catalogue and the pipeline already exist. The others build capacity and resilience.");

  // 16 --------------------------------------------------------------- technical build
  s = pres.addSlide();
  s.background = { color: WHITE };
  heading(s, "Technical skills", "Reproducible from raw data to decision");
  const tb = [["db", "Python pipeline", "10 stages, one command, deterministic: two runs give identical results for all headline numbers."],
    ["chart", "Methods", "Change-points, concentration index, kinetic-gas risk index, survival curves, Poisson regression, periodogram, damped-trend forecast with back-test."],
    ["dish", "Power BI", "Star schema: catalogue, 2014 census, storms, fires, calendar, plus the analysis tables; four dashboard pages."],
    ["rocket", "Outputs", "Booklet (PDF and Word), this deck, Power BI tables, annotated code."]];
  tb.forEach(([ic, h, t], i) => {
    const x = 0.6 + (i % 2) * 6.15, y = 1.85 + Math.floor(i / 2) * 2.4;
    card(s, x, y, 5.95, 2.15);
    circle(s, I[ic], x + 0.3, y + 0.3, 0.7, NAVY);
    s.addText(h, { x: x + 1.2, y: y + 0.3, w: 4.5, h: 0.5, fontFace: BODY, fontSize: 17, bold: true, color: NAVY, margin: 0, isTextBox: true, valign: "middle" });
    s.addText(t, { x: x + 1.2, y: y + 0.85, w: 4.5, h: 1.15, fontFace: BODY, fontSize: 13, color: INK, margin: 0, isTextBox: true, valign: "top" });
  });
  footer(s, 16);
  s.addNotes("For the technical criteria: everything is code. One command rebuilds every figure, table and number, and the Power BI dashboard uses the same tables. I can show the dashboard live if the panel wishes.");

  // 17 --------------------------------------------------------------- close
  s = pres.addSlide();
  s.background = { color: NAVY };
  s.addText("The high ground has become a crowd.", { x: 0.6, y: 1.3, w: 12.1, h: 1.2, fontFace: HEAD, fontSize: 44, bold: true, color: WHITE, margin: 0, isTextBox: true });
  card(s, 0.6, 3.0, 12.1, 2.1, "1C3157");
  s.addText("DECISION SOUGHT", { x: 0.95, y: 3.2, w: 11, h: 0.4, fontFace: BODY, fontSize: 13, bold: true, color: GOLD, charSpacing: 2, margin: 0, isTextBox: true });
  s.addText("Approve a four-month ORBITWATCH proof of concept at the Defence Space Agency, using the open catalogue and the pipeline already built. Continue only if it flags at least one actionable conjunction or threat event.",
    { x: 0.95, y: 3.65, w: 11.4, h: 1.3, fontFace: BODY, fontSize: 18, color: WHITE, margin: 0, isTextBox: true, valign: "top" });
  s.addText("Questions", { x: 0.6, y: 5.6, w: 6, h: 0.7, fontFace: HEAD, fontSize: 28, italic: true, color: "D9DEE7", margin: 0, isTextBox: true });
  footer(s, 17, true);
  s.addNotes("To close: in twelve years orbit became crowded, concentrated and contested, and India's share shrank while its dependence grew. The remedy is numbers, resilience and awareness. The ask is small and time-bound, with a clear stop test. Thank you, sir.");

  await pres.writeFile({ fileName: "Datathon2026_Theme6.1_Satellites_Presentation.pptx" });
  console.log("written");
})();
