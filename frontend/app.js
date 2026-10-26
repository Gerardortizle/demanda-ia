// Cliente de la API DEMANDA-IA. Si el frontend se publica en otro dominio,
// definir window.DEMANDA_API = "https://mi-backend" antes de cargar este archivo.
const API = (window.DEMANDA_API || "") + "/api/v1";
const $ = (id) => document.getElementById(id);
let catalogo = null;

async function pedir(ruta, opciones = {}) {
  const r = await fetch(API + ruta, { headers: { "Content-Type": "application/json" }, ...opciones });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = cuerpo.detail;
    const msg = Array.isArray(d) ? d.map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`).join(" | ") : d;
    throw new Error(msg || `Error HTTP ${r.status}`);
  }
  return cuerpo;
}

function isoMasDias(iso, n) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

async function iniciar() {
  try {
    const s = await pedir("/salud");
    $("estado").textContent = `API en línea · modelo v${s.modelo_version}`;
    $("estado").className = "estado ok";
    catalogo = await pedir("/catalogo");
    $("sucursal").innerHTML = catalogo.sucursales
      .map((x) => `<option value="${x.id}">${x.id} · ${x.ciudad}, ${x.estado} (${x.tipo})</option>`).join("");
    $("sku").innerHTML = catalogo.productos
      .map((p) => `<option value="${p.sku}">${p.nombre}</option>`).join("");
    $("fecha").value = new Date().toISOString().slice(0, 10);
  } catch (e) {
    $("estado").textContent = "Sin conexión con la API";
    $("estado").className = "estado mal";
    mostrarError("No se pudo contactar al backend: " + e.message);
  }
}

function mostrarError(msg) { $("error").textContent = msg; $("error").hidden = !msg; }

async function calcular(ev) {
  ev.preventDefault();
  mostrarError("");
  const sucursal = $("sucursal").value, sku = $("sku").value, fecha = $("fecha").value;
  const horizonte = Number($("horizonte").value), existencia = Number($("existencia").value);
  if (!fecha || !(horizonte >= 1 && horizonte <= 14) || !(existencia >= 0)) {
    mostrarError("Revisa la fecha, los días a cubrir (1 a 14) y la existencia (0 o más).");
    return;
  }
  $("btn").disabled = true; $("btn").textContent = "Calculando…";
  try {
    const hist = await pedir(`/historial?sucursal_id=${sucursal}&sku=${sku}&hasta=${isoMasDias(fecha, -1)}`);
    const cuerpo = {
      sucursal_id: sucursal, sku, fecha_inicio: fecha, horizonte_dias: horizonte,
      existencia_actual: existencia, historial_ventas: hist.ventas,
      dias_promocion: $("promo").checked ? [...Array(horizonte).keys()].map((i) => isoMasDias(fecha, i)) : [],
    };
    if ($("precio").value) cuerpo.precio = Number($("precio").value);
    const r = await pedir("/reabasto", { method: "POST", body: JSON.stringify(cuerpo) });
    pintar(hist, r);
  } catch (e) {
    mostrarError(e.message);
  } finally {
    $("btn").disabled = false; $("btn").textContent = "Calcular pedido";
  }
}

function pintar(hist, r) {
  $("vacio").hidden = true; $("salida").hidden = false;
  $("pedido").textContent = r.pedido_sugerido;
  $("esperada").textContent = r.demanda_esperada.toFixed(1) + " pz";
  $("seguridad").textContent = r.stock_seguridad.toFixed(1) + " pz";
  $("exist").textContent = r.existencia_actual + " pz";
  $("avisos").innerHTML = r.advertencias.map((a) => `<li>${a}</li>`).join("");
  $("tabla").innerHTML = r.dias
    .map((d) => `<tr><td>${d.fecha}</td><td>${d.p50.toFixed(1)}</td><td>${d.p90.toFixed(1)}</td></tr>`).join("");
  $("meta").textContent = `Modelo v${r.modelo_version} · ${r.sucursal_id} · ${r.sku} · horizonte ${r.horizonte_dias} días`;
  grafica(hist.ventas, r.dias);
}

function grafica(ventas, dias) {
  const svg = $("grafica"), W = 760, H = 260, m = { l: 34, r: 8, t: 10, b: 24 };
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const n = ventas.length + dias.length;
  const maxY = Math.max(1, ...ventas, ...dias.map((d) => d.p90)) * 1.1;
  const bw = (W - m.l - m.r) / n, y = (v) => H - m.b - (v / maxY) * (H - m.t - m.b);
  const css = getComputedStyle(document.documentElement);
  const c = (v) => css.getPropertyValue(v).trim();
  let s = "";
  for (let k = 0; k <= 4; k++) {
    const v = (maxY / 4) * k;
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="${c("--linea")}"/>`;
    s += `<text x="${m.l - 6}" y="${y(v) + 4}" font-size="11" text-anchor="end" fill="${c("--tenue")}">${Math.round(v)}</text>`;
  }
  ventas.forEach((v, i) => {
    s += `<rect x="${m.l + i * bw + 1}" y="${y(v)}" width="${bw - 2}" height="${H - m.b - y(v)}" fill="${c("--barra-hist")}"><title>${v} pz</title></rect>`;
  });
  dias.forEach((d, j) => {
    const x = m.l + (ventas.length + j) * bw + 1;
    s += `<rect x="${x}" y="${y(d.p90)}" width="${bw - 2}" height="${H - m.b - y(d.p90)}" fill="${c("--ambar-claro")}" stroke="${c("--ambar")}"><title>P90 ${d.p90}</title></rect>`;
    s += `<rect x="${x + bw * 0.2}" y="${y(d.p50)}" width="${bw * 0.6 - 2}" height="${H - m.b - y(d.p50)}" fill="${c("--verde")}"><title>${d.fecha}: P50 ${d.p50}</title></rect>`;
  });
  const xHoy = m.l + ventas.length * bw;
  s += `<line x1="${xHoy}" x2="${xHoy}" y1="${m.t}" y2="${H - m.b}" stroke="${c("--tinta")}" stroke-dasharray="4 3"/>`;
  s += `<text x="${xHoy + 4}" y="${m.t + 10}" font-size="11" fill="${c("--tinta")}">pronóstico</text>`;
  s += `<text x="${m.l}" y="${H - 6}" font-size="11" fill="${c("--tenue")}">hace 28 días</text>`;
  svg.innerHTML = s;
}

$("form").addEventListener("submit", calcular);
iniciar();
