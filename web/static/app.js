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
const VISTAS = ['login', 'subir', 'corrida', 'corridas', 'diccionario'];
const COLUMNAS_DEL_NOMBRE = ['NRO TEMP', 'TIT TEMP', 'AÑO', 'NRO CAP', 'TIT CAP'];
const TIPOS = ['', 'programa', 'pelicula', 'evento'];
const CAPAS = ['diccionario', 'patrón', 'parecido', 'modelo', 'sin propuesta'];
// Igual que CON_SEPARADOR de procesar.py: "PROGRAMA | lo que cambia".
const CON_SEPARADOR = /^(.+?)\s*(\||:|\s-\s)\s*(.+)$/;
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

// Las fechas llegan en UTC; el navegador las muestra en la hora de quien mira.
const fecha = (iso, conHora = true) => new Date(iso).toLocaleString('es-AR', {
  day: '2-digit', month: '2-digit', ...(conHora ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}),
});

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

// replaceChildren convierte null en el texto "null" y no aplana listas: esto sí.
function poner(nodo, ...hijos) {
  nodo.replaceChildren(...hijos.flat(Infinity).filter((h) => h !== null && h !== undefined && h !== false));
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
  poner(estado, salida);
  const primero = estado.querySelector('input');
  if (primero) primero.focus();
}

// ---------- corrida ----------

const nombreDe = (id) => (senales.find((s) => s.id === id) || {}).nombre || id;
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

function barras(capas) {
  const lista = CAPAS.filter((c) => capas[c]);
  const max = Math.max(1, ...lista.map((c) => capas[c]));
  return el('div', { class: 'barras' }, lista.map((capa) =>
    el('div', {}, el('span', { class: 'tenue' }, capa),
      el('span', { class: 'barra-capa' }, '█'.repeat(Math.round((capas[capa] / max) * 40)) || (capas[capa] ? '▏' : '')),
      el('span', { class: 'cuenta' }, capas[capa]))));
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
  const conPropuesta = faltan.filter((p) => p.propuesta && p.propuesta['TIT PRINC']);
  const errores = c.epg.errores;

  poner(v, 
    prompt(`cat corrida/${c.id}`),
    el('div', { class: 'cabecera' },
      el('p', { class: 'titular' }, nombreDe(c.senal), c.semanal ? el('span', { class: 'tenue' }, '  semanal') : null),
      el('p', { class: 'tenue' }, c.archivos.join(' · ')),
      el('p', { class: 'tenue' }, `${plural(c.epg.filas.length, 'programa', 'programas')} · ${c.epg.dias} días`)),
    barras(c.capas),
    c.problema_modelo ? el('p', { class: 'alerta' }, `! ${c.problema_modelo}`) : null,
    errores.length ? el('div', { class: 'bloque' },
      el('p', { class: 'error' }, `${plural(errores.length, 'error', 'errores')} de formato: el sistema que recibe el EPG lo rechazaría`),
      errores.slice(0, 30).map((e) => el('p', { class: 'error sangria' }, e)),
      errores.length > 30 ? el('p', { class: 'error sangria' }, `y ${errores.length - 30} más`) : null) : null,
    c.epg.avisos.length ? el('div', { class: 'bloque' }, c.epg.avisos.map((a) => el('p', { class: 'alerta' }, `aviso: ${a}`))) : null,
    el('div', { class: 'acciones' },
      el('a', { class: 'btn lleno', href: `/api/corridas/${c.id}/excel` }, 'descargar .xlsx'),
      conPropuesta.length ? el('button', {
        class: 'btn', onclick: async () => {
          await api(`/api/corridas/${c.id}/aprobar-propuestas`, { method: 'POST' });
          verCorrida(c.id);
        },
      }, `aceptar ${conPropuesta.length === 1 ? 'la propuesta' : `las ${conPropuesta.length} propuestas`}`) : null),
    el('h2', {}, faltan.length ? `revisar ${faltan.length}` : 'revisar: no queda nada'),
    faltan.length ? el('p', { class: 'ayuda' }, 'Enter acepta · Esc lo deja para después · lo que quede sin aprobar sale marcado en REVISAR') : null,
    el('ul', { class: 'pendientes' }, faltan.map((p) => pendiente(c, p))),
    listos.length ? el('details', { class: 'listos' },
      el('summary', {}, `${plural(listos.length, 'ya está', 'ya están')} en el diccionario`),
      el('ul', { class: 'pendientes' }, listos.map((p) => pendiente(c, p)))) : null,
    el('h2', {}, 'epg'),
    tablaEPG(c.epg),
  );
  const destino = enfocar && v.querySelector(`[data-pend="${enfocar}"] .titulo-prop`);
  if (destino) destino.focus();
}

function pendiente(c, p) {
  const hecho = p.estado === 'aprobado';
  const prop = { ...p.propuesta };
  const titulo = el('input', { class: 'titulo-prop', value: prop['TIT PRINC'] || '', placeholder: p.crudo, 'aria-label': 'TIT PRINC' });
  const tipo = el('select', { 'aria-label': 'TIPO' }, TIPOS.map((t) => el('option', { value: t, selected: (prop.TIPO || '') === t }, t || '—')));
  const extras = el('span', { class: 'extras' });
  const campos = {};
  const agregarCampo = (col, valor = '') => {
    if (campos[col]) return campos[col].focus();
    campos[col] = el('input', { size: col.startsWith('TIT') ? 22 : 4, value: valor, 'aria-label': col });
    extras.append(el('label', {}, `${col} `, campos[col]));
    return null;
  };
  for (const col of COLUMNAS_DEL_NOMBRE) if (prop[col] !== undefined && prop[col] !== null) agregarCampo(col, prop[col]);
  const sumar = el('select', {
    'aria-label': 'sumar una columna',
    onchange: (ev) => { if (ev.target.value) agregarCampo(ev.target.value); ev.target.value = ''; },
  }, el('option', { value: '' }, '+ columna'), COLUMNAS_DEL_NOMBRE.map((col) => el('option', { value: col }, col)));

  const separado = p.crudo.match(CON_SEPARADOR);
  const clave = separado ? `${separado[1].trim()} ${separado[2].trim()}` : null;
  const patron = clave ? el('input', { type: 'checkbox', checked: prop.PATRON === true }) : null;

  const siguiente = () => {
    const todos = [...document.querySelectorAll('.pendientes:not(.listos *) > .pend:not(.hecho)')];
    const i = todos.findIndex((n) => n.dataset.pend === String(p.id));
    return todos[i + 1] ? todos[i + 1].dataset.pend : null;
  };
  const aceptar = async () => {
    const reparto = { 'TIT PRINC': titulo.value.trim(), TIPO: tipo.value || undefined };
    for (const [col, campo] of Object.entries(campos)) if (campo.value.trim()) reparto[col] = campo.value.trim();
    if (!reparto['TIT PRINC']) return titulo.focus();
    const proximo = siguiente();
    try {
      await postJSON(`/api/pendientes/${p.id}/aprobar`, { reparto, patron: Boolean(patron && patron.checked) });
      verCorrida(c.id, proximo);
    } catch (e) {
      alertaEn(item, e);
    }
    return null;
  };
  const despues = async () => {
    const proximo = siguiente();
    await api(`/api/pendientes/${p.id}/saltear`, { method: 'POST' });
    verCorrida(c.id, proximo);
  };
  const ctx = p.contexto || {};
  const lugar = [`${ctx.dia || ''} ${ctx.hora || ''}`.trim(), ctx.antes && `antes: ${ctx.antes}`,
    ctx.despues && `después: ${ctx.despues}`, ctx.veces > 1 && `${ctx.veces} veces`].filter(Boolean).join(' · ');
  const item = el('li', {
    class: `pend${hecho ? ' hecho' : ''}`, 'data-pend': p.id,
    onkeydown: (ev) => {
      if (hecho) return;
      if (ev.key === 'Enter' && !['BUTTON', 'SELECT'].includes(ev.target.tagName) && ev.target.type !== 'checkbox') {
        ev.preventDefault();
        aceptar();
      }
      if (ev.key === 'Escape') { ev.preventDefault(); despues(); }
    },
  },
  el('p', {}, el('span', { class: 'crudo' }, p.crudo),
    el('span', { class: 'capa' }, hecho ? '✓ en el diccionario' : `${p.capa}${p.estado === 'salteado' ? ' · para después' : ''}`)),
  el('p', { class: 'contexto' }, lugar),
  p.nota && !hecho ? el('p', { class: p.capa === 'parecido' ? 'contexto' : 'alerta' }, p.nota) : null,
  hecho ? null : el('div', { class: 'campos' },
    el('label', {}, 'TIT PRINC ', titulo), el('label', {}, 'TIPO ', tipo), extras, sumar,
    el('span', { class: 'botones' },
      el('button', { class: 'btn', onclick: aceptar }, 'aceptar'),
      el('button', { class: 'btn', onclick: despues }, 'después'))),
  hecho || !patron ? null : el('p', {},
    el('label', { class: 'tilde' }, patron, `usar para todo lo que empiece con «${clave}»`)));
  return item;
}

function alertaEn(nodo, e) {
  nodo.append(el('p', { class: 'error' }, String(e.message || e)));
}

function tablaEPG(epg) {
  const iRevisar = epg.columnas.indexOf('REVISAR');
  const filtro = el('input', { placeholder: 'grep', 'aria-label': 'filtrar el epg', size: 24 });
  const cuenta = el('span', { class: 'tenue' });
  const cuerpo = el('tbody');
  const dibujar = () => {
    const q = filtro.value.trim().toLowerCase();
    const filas = q ? epg.filas.filter((f) => f.join(' ').toLowerCase().includes(q)) : epg.filas;
    cuenta.textContent = q ? `  ${filas.length} de ${epg.filas.length}` : '';
    cuerpo.replaceChildren(...filas.map((f) => el('tr', { class: iRevisar >= 0 && f[iRevisar] ? 'revisar' : null },
      f.map((val, i) => el('td', { class: typeof val === 'number' && i !== 0 ? 'num' : null }, val ?? '')))));
  };
  filtro.addEventListener('input', dibujar);
  dibujar();
  return el('div', {}, el('p', {}, filtro, cuenta),
    el('div', { class: 'tabla-scroll' },
      el('table', {}, el('thead', {}, el('tr', {}, epg.columnas.map((col) => el('th', {}, col)))), cuerpo)));
}

// ---------- corridas ----------

function miniBarra(capas, ancho = 24) {
  const total = Object.values(capas).reduce((a, b) => a + b, 0) || 1;
  const seg = (n, ch) => ch.repeat(Math.round((n / total) * ancho));
  const alModelo = (capas.modelo || 0) + (capas['sin propuesta'] || 0);
  return seg((capas.diccionario || 0) + (capas['patrón'] || 0), '█') + seg(capas.parecido || 0, '▓') + seg(alModelo, '░');
}

async function verCorridas() {
  const v = $('#v-corridas');
  mostrar('corridas');
  try {
    const [lista, h] = await Promise.all([api('/api/corridas'), api('/api/historial')]).then((r) => r.map((x) => x.cuerpo));
    poner(v, prompt('ls corridas/'),
      lista.length ? [
        el('p', {}, `${plural(h.grillas, 'grilla procesada', 'grillas procesadas')} · ~${h.horas_ahorradas} h ahorradas · `
          + `${h.nombres_aprobados} nombres en el diccionario`),
        el('p', { class: 'tenue' }, '█ ya conocido   ▓ parecido   ░ al modelo · cuanto más corta la parte clara, menos trabaja el modelo'),
        el('div', { class: 'corridas' }, lista.map((c) => [
          el('a', { href: `#corrida/${c.id}` }, `#${c.id}`),
          el('span', { class: 'tenue' }, fecha(c.creada)),
          el('a', { href: `#corrida/${c.id}` }, nombreDe(c.senal), c.semanal ? ' · semanal' : ''),
          el('span', { class: 'grafico' }, miniBarra(c.capas)),
          c.faltan ? el('span', { class: 'alerta' }, `faltan ${c.faltan}`) : el('span', { class: 'tenue' }, 'al día'),
        ])),
      ] : el('p', { class: 'tenue' }, 'Todavía no procesaste ninguna grilla. Las corridas se guardan 30 días.'));
  } catch (e) {
    error(v, e);
  }
}

// ---------- diccionario ----------

function descripcionResto(resto) {
  const como = { nombre: 'como nombre propio', 'tal cual': 'tal cual viene', modelo: 'lo escribe el modelo' }[resto.estilo];
  return `patrón · lo que sigue va a ${resto.columna}, ${como}`;
}

async function verDiccionario(senal) {
  const v = $('#v-diccionario');
  mostrar('diccionario');
  senal = senal || (senales[0] || {}).id;
  const actual = senales.find((s) => s.id === senal) || {};
  const selector = el('select', { 'aria-label': 'señal', onchange: (ev) => { location.hash = `#diccionario/${ev.target.value}`; } },
    senales.map((s) => el('option', { value: s.id, selected: s.id === senal }, s.nombre)));
  const nombre = el('input', { value: actual.nombre || '', size: 22, 'aria-label': 'nombre de la señal' });
  const guardarNombre = el('button', {
    class: 'btn chico', hidden: true, onclick: async () => {
      try {
        await api(`/api/senales/${senal}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nombre: nombre.value.trim() }),
        });
        senales = (await api('/api/senales')).cuerpo;
        llenarSenales();
        verDiccionario(senal);
      } catch (e) {
        alertaEn(v, e);
      }
    },
  }, 'guardar');
  nombre.addEventListener('input', () => { guardarNombre.hidden = !nombre.value.trim() || nombre.value.trim() === actual.nombre; });
  nombre.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && !guardarNombre.hidden) guardarNombre.click(); });

  const busqueda = el('input', { placeholder: 'grep', 'aria-label': 'buscar en el diccionario', size: 28 });
  const resultado = el('div');
  let espera;
  busqueda.addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(cargar, 250); });

  async function cargar() {
    try {
      const d = (await api(`/api/diccionario/${senal}?q=${encodeURIComponent(busqueda.value.trim())}`)).cuerpo;
      const grupos = new Map();
      for (const e of d.entradas) {
        const t = e.reparto['TIT PRINC'] || e.crudo;
        if (!grupos.has(t)) grupos.set(t, []);
        grupos.get(t).push(e);
      }
      const orden = [...grupos.keys()].sort((a, b) => a.localeCompare(b, 'es', { ignorePunctuation: true }));
      poner(resultado, 
        el('p', { class: 'tenue' }, `${plural(orden.length, 'programa', 'programas')} · ${plural(d.total, 'nombre', 'nombres')}`),
        el('div', { class: 'programas' }, orden.map((t) => programa(t, grupos.get(t)))));
    } catch (e) {
      error(resultado, e);
    }
  }

  function programa(tituloActual, entradas) {
    const titulo = el('input', { value: tituloActual, class: 'titulo-prog', 'aria-label': `título de ${tituloActual}` });
    const guardar = el('button', {
      class: 'btn chico', hidden: true, onclick: async () => {
        try {
          await api(`/api/diccionario/${senal}/programa`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ antes: tituloActual, despues: titulo.value.trim() }),
          });
          cargar();
        } catch (err) {
          alertaEn(grupo, err);
        }
      },
    }, entradas.length > 1 ? `guardar en los ${entradas.length}` : 'guardar');
    titulo.addEventListener('input', () => { guardar.hidden = !titulo.value.trim() || titulo.value.trim() === tituloActual; });
    titulo.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && !guardar.hidden) guardar.click(); });
    const filas = entradas.map((e) => {
        const otras = Object.entries(e.reparto).filter(([k]) => !['TIT PRINC', 'RESTO'].includes(k)).map(([k, val]) => `${k}: ${val}`);
        const borrar = el('button', {
          class: 'btn chico', onclick: async () => {
            if (!confirm(`¿Sacar "${e.crudo}" del diccionario? La próxima vez que venga se va a revisar de nuevo.`)) return;
            await api(`/api/diccionario/${senal}/${e.id}`, { method: 'DELETE' });
            cargar();
          },
        }, 'sacar');
        return [el('span', { class: 'crudo' }, e.reparto.RESTO ? `${e.crudo}…` : e.crudo),
          e.reparto.RESTO ? el('span', { class: 'alerta' }, descripcionResto(e.reparto.RESTO)) : null,
          otras.length ? el('span', { class: 'tenue' }, otras.join(' · ')) : null,
          borrar];
    });
    // Un programa con un solo nombre va en un renglón; con varios, los nombres van debajo del título.
    const grupo = entradas.length === 1
      ? el('div', { class: 'programa' }, el('p', { class: 'cabeza' }, titulo, guardar, filas[0]))
      : el('div', { class: 'programa' }, el('p', { class: 'cabeza' }, titulo, guardar),
        el('ul', { class: 'crudos' }, filas.map((f) => el('li', {}, f))));
    return grupo;
  }

  poner(v, prompt(`grep diccionario/${senal}`),
    el('div', { class: 'acciones' },
      el('label', {}, 'señal ', selector),
      el('label', {}, 'nombre ', nombre), guardarNombre),
    el('div', { class: 'acciones' }, busqueda,
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

function llenarSenales() {
  const elegida = $('#f-senal').value;
  $('#f-senal').replaceChildren(el('option', { value: '' }, 'reconocer por el archivo'),
    ...senales.map((s) => el('option', { value: s.id, selected: s.id === elegida }, s.nombre)));
}

function ruta() {
  if (!usuario) return mostrar('login');
  const [vista, arg] = location.hash.slice(1).split('/');
  if (vista === 'corrida' && arg) return verCorrida(arg);
  if (vista === 'corridas' || vista === 'historial') return verCorridas();
  if (vista === 'diccionario') return verDiccionario(arg);
  return mostrar('subir');
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
  llenarSenales();
  ticker();
  ruta();
}

const reloj = () => { $('#reloj').textContent = new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false }); };
reloj();
setInterval(reloj, 15000);
window.addEventListener('hashchange', () => { ruta(); if (usuario) ticker(); });
arrancar();
