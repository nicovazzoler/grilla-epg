'use strict';

// Arma un elemento. Los textos van siempre como texto: lo que viene de una grilla nunca se interpreta como HTML.
function el(tag, attrs = {}, ...hijos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (k === 'class') n.className = v;
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const h of hijos.flat(Infinity)) {
    if (h === null || h === undefined || h === false) continue;
    n.append(h instanceof Node ? h : document.createTextNode(String(h)));
  }
  return n;
}

const $ = (sel) => document.querySelector(sel);
const VISTAS = ['login', 'subir', 'corrida', 'corridas', 'historial', 'diccionario'];
const COLUMNAS_DEL_NOMBRE = ['NRO TEMP', 'TIT TEMP', 'AÑO', 'NRO CAP', 'TIT CAP'];
const TIPOS = ['', 'programa', 'pelicula', 'evento'];
let usuario = null;
let senales = [];

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, { credentials: 'same-origin', ...opciones });
  if (r.status === 401 && ruta !== '/api/login') {
    mostrar('login');
    throw new Error('sin sesión');
  }
  const cuerpo = (r.headers.get('content-type') || '').includes('json') ? await r.json() : null;
  if (!r.ok && ![409, 422].includes(r.status)) throw new Error((cuerpo && cuerpo.detail) || `error ${r.status}`);
  return { status: r.status, cuerpo };
}

const postJSON = (ruta, datos) =>
  api(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) });

function mostrar(vista) {
  for (const v of VISTAS) $(`#v-${v}`).hidden = v !== vista;
  $('#menu').hidden = vista === 'login';
  for (const a of document.querySelectorAll('#menu a')) {
    a.toggleAttribute('aria-current', location.hash.startsWith(a.getAttribute('href')));
    if (a.hasAttribute('aria-current')) a.setAttribute('aria-current', 'page');
  }
}

function prompt(comando) {
  return el('p', { class: 'prompt' }, `${usuario}@grilla-epg:~$ ${comando}`);
}

function error(destino, e) {
  destino.replaceChildren(el('p', { class: 'error' }, String(e.message || e)));
}

// ---------- login ----------

$('#f-login').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const datos = Object.fromEntries(new FormData(ev.target));
  const { status, cuerpo } = await postJSON('/api/login', datos).catch((e) => ({ status: 0, cuerpo: { detail: e.message } }));
  const aviso = $('#login-error');
  if (status !== 200) {
    aviso.hidden = false;
    aviso.textContent = (cuerpo && cuerpo.detail) || 'No se pudo entrar.';
    return;
  }
  aviso.hidden = true;
  await arrancar();
});

// ---------- subir ----------

const subida = { archivos: [], horas: {} };

function listarArchivos() {
  $('#lista-archivos').replaceChildren(...subida.archivos.map((a) => el('li', {}, a.name)));
  $('#procesar').disabled = !subida.archivos.length;
}

function agregarArchivos(lista) {
  subida.archivos = [...lista];
  subida.horas = {};
  $('#estado-subida').replaceChildren();
  listarArchivos();
}

$('#elegir').addEventListener('click', () => $('#f-archivos').click());
$('#f-archivos').addEventListener('change', (ev) => agregarArchivos(ev.target.files));
const zona = $('#zona');
zona.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') $('#f-archivos').click(); });
zona.addEventListener('dragover', (ev) => { ev.preventDefault(); zona.classList.add('encima'); });
zona.addEventListener('dragleave', () => zona.classList.remove('encima'));
zona.addEventListener('drop', (ev) => {
  ev.preventDefault();
  zona.classList.remove('encima');
  agregarArchivos(ev.dataTransfer.files);
});
$('#procesar').addEventListener('click', procesar);

async function procesar() {
  const estado = $('#estado-subida');
  const datos = new FormData();
  for (const a of subida.archivos) datos.append('archivos', a);
  datos.append('senal', $('#f-senal').value);
  datos.append('semanal', $('#f-semanal').checked ? 'true' : 'false');
  datos.append('horas', JSON.stringify(subida.horas));
  $('#procesar').disabled = true;
  estado.replaceChildren(el('p', { class: 'tenue' }, 'leyendo las grillas y consultando lo nuevo... puede tardar unos segundos'));
  try {
    const { status, cuerpo } = await api('/api/corridas', { method: 'POST', body: datos });
    if (status === 200) {
      location.hash = `#corrida/${cuerpo.id}`;
      return;
    }
    if (status === 409) return preguntarHora(cuerpo);
    if (cuerpo && cuerpo.pregunta === 'senal') {
      estado.replaceChildren(el('p', { class: 'alerta' }, `? ${cuerpo.mensaje}`));
      $('#f-senal').focus();
      return;
    }
    estado.replaceChildren(el('p', { class: 'error' }, (cuerpo && cuerpo.detail) || 'No se pudo procesar.'));
  } catch (e) {
    error(estado, e);
  } finally {
    $('#procesar').disabled = !subida.archivos.length;
  }
}

function preguntarHora(f) {
  const estado = $('#estado-subida');
  const filas = f.filas.map((x) => {
    const campo = f.corrige_horas && x.fila
      ? el('input', { size: 5, placeholder: x.hora, 'aria-label': `hora buena de ${x.ref}`, 'data-fila': x.fila })
      : null;
    return el('p', {}, `  ${x.ref}  ${x.dia} ${x.hora}  ${x.nombre}  `, campo ? ['→ ', campo] : '');
  });
  const salida = [el('p', { class: 'alerta' }, `? FRENADO: horarios fuera de orden. Una de las dos horas está mal en la grilla.`), ...filas];
  if (f.corrige_horas) {
    salida.push(el('p', { class: 'tenue' }, 'Poné la hora buena en la fila que esté mal y volvé a procesar.'));
    salida.push(el('button', {
      class: 'btn lleno', onclick: () => {
        for (const c of estado.querySelectorAll('input[data-fila]')) {
          if (c.value.trim()) subida.horas[c.dataset.fila] = c.value.trim();
        }
        procesar();
      },
    }, 'procesar con la hora corregida'));
  } else {
    salida.push(el('p', { class: 'tenue' }, 'Corregí la grilla y volvé a subirla.'));
  }
  estado.replaceChildren(...salida);
  const primero = estado.querySelector('input');
  if (primero) primero.focus();
}

// ---------- corrida ----------

function barras(capas) {
  const max = Math.max(1, ...Object.values(capas));
  return el('div', { class: 'barras' }, Object.entries(capas).map(([capa, n]) =>
    el('div', {}, el('span', { class: 'tenue' }, capa), el('span', { class: 'barra-capa' }, '█'.repeat(Math.round((n / max) * 40)) || (n ? '▏' : '')),
      el('span', { class: 'cuenta' }, n))));
}

async function verCorrida(id, enfocar = null) {
  const v = $('#v-corrida');
  mostrar('corrida');
  let c;
  try {
    c = (await api(`/api/corridas/${id}`)).cuerpo;
  } catch (e) {
    return error(v, e);
  }
  const faltan = c.pendientes.filter((p) => p.estado !== 'aprobado');
  const listos = c.pendientes.filter((p) => p.estado === 'aprobado');
  const parecidos = faltan.filter((p) => p.capa === 'parecido');
  const nombreSenal = (senales.find((s) => s.id === c.senal) || {}).nombre || c.senal;

  v.replaceChildren(
    prompt(`cat corrida/${c.id}`),
    el('p', {}, `${nombreSenal} · ${c.archivos.join(', ')}`, c.semanal ? ' · semanal' : ''),
    el('p', { class: 'tenue' }, `${c.epg.filas.length} programas · ${c.epg.dias} días · ${c.epg.minutos} min`),
    barras(c.capas),
    c.problema_modelo ? el('p', { class: 'alerta' }, `! ${c.problema_modelo}`) : null,
    c.epg.errores.length
      ? el('div', {}, el('p', { class: 'error' }, `${c.epg.errores.length} errores de formato (el sistema los rechazaría):`),
        c.epg.errores.slice(0, 30).map((e) => el('p', { class: 'error' }, `  ${e}`)))
      : el('p', { class: 'tenue' }, '0 errores de formato'),
    c.epg.avisos.map((a) => el('p', { class: 'alerta' }, `aviso: ${a}`)),
    el('div', { class: 'acciones' },
      el('a', { class: 'btn lleno', href: `/api/corridas/${c.id}/excel` }, 'descargar .xlsx'),
      parecidos.length ? el('button', {
        class: 'btn', onclick: async () => {
          await api(`/api/corridas/${c.id}/aprobar-parecidos`, { method: 'POST' });
          verCorrida(c.id);
        },
      }, `aceptar los ${parecidos.length} de parecido`) : null),
    el('h2', {}, faltan.length ? `revisar ${faltan.length}` : 'revisar: no queda nada'),
    faltan.length ? el('p', { class: 'ayuda' }, 'Enter acepta · Esc lo deja para después · las columnas vacías no se guardan') : null,
    el('ul', { class: 'pendientes' }, faltan.map((p) => pendiente(c, p))),
    listos.length ? el('details', { class: 'listos' },
      el('summary', {}, `${listos.length} ya en el diccionario`),
      el('ul', { class: 'pendientes' }, listos.map((p) => pendiente(c, p)))) : null,
    el('h2', {}, 'epg'),
    tablaEPG(c.epg),
  );
  const destino = (enfocar && v.querySelector(`[data-pend="${enfocar}"] input`)) || v.querySelector('.pend:not(.hecho) input');
  if (destino && enfocar !== null) destino.focus();
}

function pendiente(c, p) {
  const hecho = p.estado === 'aprobado';
  const prop = { ...p.propuesta };
  const titulo = el('input', { class: 'titulo-prop', value: prop['TIT PRINC'] || '', placeholder: p.crudo, 'aria-label': 'título' });
  const tipo = el('select', { 'aria-label': 'tipo' }, TIPOS.map((t) => el('option', { value: t, selected: (prop.TIPO || '') === t }, t || '—')));
  const extras = el('span', { class: 'campos' });
  const campos = {};
  const agregarCampo = (col, valor = '') => {
    if (campos[col]) return campos[col].focus();
    campos[col] = el('input', { size: col.startsWith('TIT') ? 18 : 5, value: valor, 'aria-label': col });
    extras.append(el('label', {}, `${col} `, campos[col]));
  };
  for (const col of COLUMNAS_DEL_NOMBRE) if (prop[col] !== undefined && prop[col] !== null) agregarCampo(col, prop[col]);
  const sumar = el('select', {
    'aria-label': 'sumar columna',
    onchange: (ev) => { if (ev.target.value) agregarCampo(ev.target.value); ev.target.value = ''; },
  }, el('option', { value: '' }, '+ columna'), COLUMNAS_DEL_NOMBRE.map((col) => el('option', { value: col }, col)));

  const siguiente = () => {
    const todos = [...document.querySelectorAll('.pend:not(.hecho)')];
    const i = todos.findIndex((n) => n.dataset.pend === String(p.id));
    return (todos[i + 1] || {}).dataset ? todos[i + 1].dataset.pend : null;
  };
  const aceptar = async () => {
    const reparto = { 'TIT PRINC': titulo.value.trim(), TIPO: tipo.value || undefined };
    for (const [col, campo] of Object.entries(campos)) if (campo.value.trim()) reparto[col] = campo.value.trim();
    if (!reparto['TIT PRINC']) return titulo.focus();
    const proximo = siguiente();
    try {
      await postJSON(`/api/pendientes/${p.id}/aprobar`, { reparto });
      verCorrida(c.id, proximo);
    } catch (e) {
      alertaEn(item, e);
    }
  };
  const despues = async () => {
    const proximo = siguiente();
    await api(`/api/pendientes/${p.id}/saltear`, { method: 'POST' });
    verCorrida(c.id, proximo);
  };
  const ctx = p.contexto || {};
  const item = el('li', {
    class: `pend${hecho ? ' hecho' : ''}`, 'data-pend': p.id,
    onkeydown: (ev) => {
      if (ev.key === 'Enter' && ev.target.tagName !== 'BUTTON') { ev.preventDefault(); aceptar(); }
      if (ev.key === 'Escape') { ev.preventDefault(); despues(); }
    },
  },
  el('div', {}, el('span', { class: 'crudo' }, p.crudo),
    el('span', { class: 'capa' }, hecho ? '✓ en el diccionario' : `${p.capa}${p.estado === 'salteado' ? ' · para después' : ''}`)),
  p.nota && !hecho ? el('div', { class: p.capa === 'modelo' ? 'alerta' : 'contexto' }, p.nota) : null,
  el('div', { class: 'contexto' },
    `${ctx.dia || ''} ${ctx.hora || ''}`, ctx.antes ? ` · antes: ${ctx.antes}` : '', ctx.despues ? ` · después: ${ctx.despues}` : '',
    ctx.veces > 1 ? ` · ${ctx.veces} veces` : ''),
  el('div', { class: 'campos' },
    el('label', {}, 'TIT PRINC ', titulo), el('label', {}, 'TIPO ', tipo), extras, sumar,
    el('button', { class: 'btn', onclick: aceptar }, 'aceptar'),
    el('button', { class: 'btn', onclick: despues }, 'después')));
  return item;
}

function alertaEn(nodo, e) {
  nodo.append(el('div', { class: 'error' }, String(e.message || e)));
}

function tablaEPG(epg) {
  const iRevisar = epg.columnas.indexOf('REVISAR');
  const filtro = el('input', { placeholder: 'grep', 'aria-label': 'filtrar el epg', size: 24 });
  const cuerpo = el('tbody');
  const dibujar = () => {
    const q = filtro.value.trim().toLowerCase();
    const filas = q ? epg.filas.filter((f) => f.join(' ').toLowerCase().includes(q)) : epg.filas;
    cuerpo.replaceChildren(...filas.map((f) => el('tr', { class: iRevisar >= 0 && f[iRevisar] ? 'revisar' : null },
      f.map((v, i) => el('td', { class: typeof v === 'number' && i !== 0 ? 'num' : null }, v ?? '')))));
  };
  filtro.addEventListener('input', dibujar);
  dibujar();
  return el('div', {}, el('p', {}, filtro),
    el('div', { class: 'tabla-scroll' },
      el('table', {}, el('thead', {}, el('tr', {}, epg.columnas.map((col) => el('th', {}, col)))), cuerpo)));
}

// ---------- corridas ----------

async function verCorridas() {
  const v = $('#v-corridas');
  mostrar('corridas');
  try {
    const lista = (await api('/api/corridas')).cuerpo;
    v.replaceChildren(prompt('ls corridas/'),
      lista.length ? el('ul', { class: 'lista' }, lista.map((c) => el('li', {},
        el('a', { href: `#corrida/${c.id}` },
          `#${c.id}  ${c.creada.replace('T', ' ')}  ${c.senal}  ${c.archivos.length} grilla${c.archivos.length > 1 ? 's' : ''}`,
          c.semanal ? '  semanal' : ''),
        c.faltan ? el('span', { class: 'alerta' }, `  faltan ${c.faltan}`) : el('span', { class: 'tenue' }, '  al día'))))
        : el('p', { class: 'tenue' }, 'Todavía no procesaste ninguna grilla. Se guardan 30 días.'));
  } catch (e) {
    error(v, e);
  }
}

// ---------- historial ----------

async function verHistorial() {
  const v = $('#v-historial');
  mostrar('historial');
  try {
    const h = (await api('/api/historial')).cuerpo;
    const ancho = 40;
    const lineas = h.corridas.slice().reverse().map((c) => {
      const total = Object.values(c.capas).reduce((a, b) => a + b, 0) || 1;
      const seg = (n, ch) => ch.repeat(Math.round((n / total) * ancho));
      return `${c.creada.slice(5, 10).split('-').reverse().join('/')}  ${c.senal.padEnd(10)} `
        + seg(c.capas.diccionario || 0, '█') + seg(c.capas.parecido || 0, '▓')
        + seg((c.capas.modelo || 0) + (c.capas['sin propuesta'] || 0), '░')
        + `  ${(c.capas.modelo || 0) + (c.capas['sin propuesta'] || 0)} al modelo`;
    });
    v.replaceChildren(prompt('./historial'),
      el('p', {}, `grillas procesadas: ${h.grillas} · nombres en el diccionario: ${h.nombres_aprobados} · ~${h.horas_ahorradas} h ahorradas`),
      el('p', { class: 'tenue' }, '█ diccionario   ▓ parecido   ░ modelo: cuanto más corta la parte clara, menos trabaja el modelo'),
      lineas.length ? el('pre', { class: 'grafico' }, lineas.join('\n'))
        : el('p', { class: 'tenue' }, 'Sin corridas todavía.'));
  } catch (e) {
    error(v, e);
  }
}

// ---------- diccionario ----------

async function verDiccionario(senal) {
  const v = $('#v-diccionario');
  mostrar('diccionario');
  senal = senal || (senales[0] || {}).id;
  const selector = el('select', { 'aria-label': 'señal', onchange: (ev) => { location.hash = `#diccionario/${ev.target.value}`; } },
    senales.map((s) => el('option', { value: s.id, selected: s.id === senal }, s.nombre)));
  const busqueda = el('input', { placeholder: 'grep', 'aria-label': 'buscar en el diccionario', size: 28 });
  const resultado = el('div');
  let espera;
  busqueda.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(cargar, 250); });

  async function cargar() {
    try {
      const d = (await api(`/api/diccionario/${senal}?q=${encodeURIComponent(busqueda.value.trim())}`)).cuerpo;
      resultado.replaceChildren(
        el('p', { class: 'tenue' }, `${d.total} nombres${d.total > d.entradas.length ? ` · se muestran ${d.entradas.length}` : ''}`),
        el('div', { class: 'dicc' }, d.entradas.map(entrada)));
    } catch (e) {
      error(resultado, e);
    }
  }

  function entrada(e) {
    const titulo = el('input', { value: e.reparto['TIT PRINC'] || '', 'aria-label': `título de ${e.crudo}` });
    const resto = Object.entries(e.reparto).filter(([k]) => k !== 'TIT PRINC');
    const guardar = el('button', {
      class: 'btn chico', hidden: true, onclick: async () => {
        try {
          await api(`/api/diccionario/${senal}/${e.id}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reparto: { ...e.reparto, 'TIT PRINC': titulo.value.trim() } }),
          });
          guardar.hidden = true;
        } catch (err) {
          alertaEn(guardar.parentNode, err);
        }
      },
    }, 'guardar');
    titulo.addEventListener('input', () => { guardar.hidden = titulo.value.trim() === e.reparto['TIT PRINC']; });
    titulo.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && !guardar.hidden) guardar.click(); });
    const fila = [el('span', { class: 'crudo' }, e.crudo), titulo, el('span', {}, guardar)];
    if (resto.length) fila.push(el('span'), el('span', { class: 'extra' }, resto.map(([k, val]) => `${k}: ${val}`).join(' · ')), el('span'));
    return fila;
  }

  v.replaceChildren(prompt(`grep diccionario/${senal}`),
    el('p', { class: 'acciones' }, selector, busqueda,
      el('a', { class: 'btn', href: `/api/diccionario/${senal}/exportar` }, 'exportar .json')),
    resultado);
  cargar();
}

// ---------- arranque ----------

async function ticker() {
  try {
    const h = (await api('/api/historial')).cuerpo;
    const texto = `*** ${h.nombres_aprobados} nombres en el diccionario *** ${h.al_modelo_esta_semana} al modelo esta semana `
      + `*** ~${h.horas_ahorradas} h ahorradas *** ${h.grillas} grillas procesadas `;
    $('#ticker-texto').textContent = texto.repeat(3);
  } catch (e) { /* el ticker es de adorno: sin datos queda vacío */ }
}

function ruta() {
  if (!usuario) return mostrar('login');
  const [vista, arg] = location.hash.slice(1).split('/');
  if (vista === 'corrida' && arg) return verCorrida(arg);
  if (vista === 'corridas') return verCorridas();
  if (vista === 'historial') return verHistorial();
  if (vista === 'diccionario') return verDiccionario(arg);
  mostrar('subir');
}

async function arrancar() {
  try {
    usuario = (await api('/api/yo')).cuerpo.usuario;
  } catch (e) {
    return;
  }
  $('#quien').textContent = usuario;
  for (const n of document.querySelectorAll('.yo')) n.textContent = usuario;
  senales = (await api('/api/senales')).cuerpo;
  $('#f-senal').replaceChildren(el('option', { value: '' }, 'reconocer por el archivo'),
    ...senales.map((s) => el('option', { value: s.id }, s.nombre)));
  ticker();
  ruta();
}

setInterval(() => { $('#reloj').textContent = new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' }); }, 1000);
window.addEventListener('hashchange', () => { ruta(); if (usuario) ticker(); });
arrancar();
