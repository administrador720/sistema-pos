// Aplicación: arranque, rutas, estructura general, bloqueo de pantalla
import { api, configurarApi, sesion } from './api.js';
import { store, esAdmin, pedirPin, cerrarSesionLocal, iniciarSesionCargada, refrescarTurno, setTema, toast } from './store.js';
import { registrar } from './components.js';
import { iniciales, hora } from './util.js';
import { Setup, Login } from './views/acceso.js';
import { Apertura, Cierre } from './views/turno.js';
import { Caja } from './views/caja.js';
import { Productos } from './views/productos.js';
import { Compras } from './views/compras.js';
import { Inventario } from './views/inventario.js';
import { Conteos } from './views/conteos.js';
import { Dashboard } from './views/dashboard.js';
import { Informes } from './views/informes.js';
import { Turnos } from './views/turnos.js';
import { Configuracion, Cuenta } from './views/config.js';

const { createApp, ref, computed, onMounted, onBeforeUnmount, watch } = Vue;

const VISTAS = { caja: Caja, apertura: Apertura, cierre: Cierre, productos: Productos, compras: Compras, inventario: Inventario,
  conteos: Conteos, dashboard: Dashboard, informes: Informes, turnos: Turnos, config: Configuracion, cuenta: Cuenta };
const TITULOS = { caja: 'Caja', apertura: 'Abrir caja', cierre: 'Cerrar caja', productos: 'Productos', compras: 'Compras', inventario: 'Inventario',
  conteos: 'Conteos de inventario', dashboard: 'Panel de control', informes: 'Informes', turnos: 'Cierres de caja', config: 'Configuración', cuenta: 'Mi cuenta' };
const SOLO_ADMIN = new Set(['productos', 'compras', 'inventario', 'dashboard', 'informes', 'turnos', 'config']);

function leerRuta() {
  const [, nombre = '', arg = ''] = (location.hash || '#/').split('/');
  store.ruta = { nombre, arg };
}

const Raiz = {
  components: { Setup, Login },
  setup() {
    const listo = ref(false), lockPin = ref(''), lockError = ref(''), menu = ref(false);
    let ultimaActividad = Date.now(), temporizador = null;

    configurarApi({ pin: pedirPin, expirar: () => { if (store.usuario) { toast('La sesión expiró. Inicie sesión de nuevo.', 'warn'); cerrarSesionLocal(); } } });

    function irInicio() {
      if (esAdmin()) location.hash = store.turno ? '#/dashboard' : '#/dashboard';
      else location.hash = store.turno ? '#/caja' : '#/apertura';
    }
    async function alIngresar() { await iniciarSesionCargada(); irInicio(); }

    // pantalla efectiva: un cajero que escribe una dirección de administración vuelve a su pantalla
    const nombreRuta = computed(() => {
      let n = store.ruta.nombre;
      if (!n || !VISTAS[n] || (SOLO_ADMIN.has(n) && !esAdmin())) n = esAdmin() ? 'dashboard' : (store.turno ? 'caja' : 'apertura');
      return n;
    });
    const vista = computed(() => VISTAS[nombreRuta.value]);
    const claveVista = computed(() => nombreRuta.value + '/' + store.ruta.arg);
    const titulo = computed(() => TITULOS[nombreRuta.value]);

    watch(nombreRuta, n => {
      store.mini = n === 'caja'; menu.value = false;
      if (store.usuario && store.ruta.nombre !== n) history.replaceState(null, '', '#/' + n);
    }, { immediate: true });

    const nav = computed(() => {
      const items = [{ grupo: 'Operación' },
        { r: 'caja', t: 'Caja', i: 'carrito' },
        store.turno ? { r: 'cierre', t: 'Cerrar caja', i: 'candado' } : { r: 'apertura', t: 'Abrir caja', i: 'caja' }];
      if (esAdmin()) {
        items.push({ grupo: 'Administración' },
          { r: 'dashboard', t: 'Panel de control', i: 'tablero' }, { r: 'productos', t: 'Productos', i: 'caja_prod' },
          { r: 'compras', t: 'Compras', i: 'camion' }, { r: 'inventario', t: 'Inventario', i: 'lista', badge: store.alertas },
          { r: 'conteos', t: 'Conteos', i: 'conteo' }, { r: 'informes', t: 'Informes', i: 'informe' },
          { r: 'turnos', t: 'Cierres de caja', i: 'recibo' }, { r: 'config', t: 'Configuración', i: 'ajustes' });
      } else {
        items.push({ r: 'conteos', t: 'Conteo de inventario', i: 'conteo' });
      }
      return items;
    });

    // ── bloqueo por inactividad
    const marcar = () => { ultimaActividad = Date.now(); };
    function revisarInactividad() {
      if (!store.usuario || store.bloqueado) return;
      const min = parseInt(store.config.bloqueo_minutos || '0', 10);
      if (min > 0 && Date.now() - ultimaActividad > min * 60000) bloquear();
    }
    function bloquear() { store.bloqueado = true; lockPin.value = ''; lockError.value = ''; menu.value = false; }
    async function desbloquear() {
      try { await api.post('/api/auth/verificar', { secreto: lockPin.value }); store.bloqueado = false; marcar(); }
      catch (e) { lockError.value = e.message; lockPin.value = ''; }
    }
    function salir() { api.post('/api/auth/logout').catch(() => {}); cerrarSesionLocal(); }

    onMounted(async () => {
      leerRuta(); window.addEventListener('hashchange', leerRuta);
      for (const ev of ['mousemove', 'keydown', 'click', 'touchstart']) window.addEventListener(ev, marcar, { passive: true });
      temporizador = setInterval(revisarInactividad, 15000);
      document.addEventListener('click', e => { if (!e.target.closest('.menu-wrap')) menu.value = false; });
      try {
        const est = await (await fetch('/api/setup/estado')).json();
        store.configurado = est.configurado; store.version = est.version || '';
        if (est.configurado && sesion.token) {
          try { await iniciarSesionCargada(); } catch (e) { sesion.limpiar(); }
        }
      } catch (e) { toast('No se pudo conectar con el sistema.', 'error'); }
      listo.value = true;
    });
    onBeforeUnmount(() => { clearInterval(temporizador); window.removeEventListener('hashchange', leerRuta); });

    return { store, listo, vista, claveVista, titulo, nav, nombreRuta, esAdmin, alIngresar, bloquear, desbloquear, lockPin, lockError, menu,
      salir, setTema, iniciales, hora, irInicio, logo: computed(() => store.config.negocio_logo) };
  },
  template: `
    <div v-if="!listo" class="auth"><div class="muted">Cargando…</div></div>
    <Setup v-else-if="!store.configurado" @listo="alIngresar"/>
    <Login v-else-if="!store.usuario" @listo="alIngresar"/>
    <div v-else class="app" :class="{ mini: store.mini }">
      <aside class="sidebar">
        <div class="brand">
          <div class="logo"><img v-if="logo" :src="logo" alt=""><Icono v-else n="tienda" class="ico lg"/></div>
          <div><b>{{ store.config.negocio_nombre || 'Mi Supermercado' }}</b><span>Punto de venta</span></div>
        </div>
        <nav class="nav">
          <template v-for="(it, i) in nav" :key="i">
            <div class="nav-group" v-if="it.grupo">{{ it.grupo }}</div>
            <a v-else :href="'#/' + it.r" :class="{ on: nombreRuta === it.r }" :title="it.t">
              <Icono :n="it.i"/><span>{{ it.t }}</span><i class="badge" v-if="it.badge">{{ it.badge }}</i>
            </a>
          </template>
        </nav>
        <div class="side-foot">
          <button class="btn ghost block" style="justify-content:flex-start" @click="bloquear" title="Bloquear pantalla"><Icono n="candado"/><span class="txt">Bloquear</span></button>
          <div class="xs muted txt" style="padding:2px 12px" v-if="store.version">Versión {{ store.version }}</div>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <h1>{{ titulo }}</h1>
          <button class="turno-chip" :class="{ cerrado: !store.turno }" @click="store.turno ? (location.hash = '#/cierre') : (location.hash = '#/apertura')"
                  :title="store.turno ? 'Ir a cerrar la caja' : 'Abrir la caja'">
            <i></i>
            <span v-if="store.turno">Turno #{{ store.turno.id }} · {{ store.turno.usuario }} · desde {{ hora(store.turno.abierto_en) }}</span>
            <span v-else>Caja cerrada</span>
          </button>
          <button class="turno-chip nueva-version" v-if="esAdmin() && store.actualizacion" @click="store.pestanaConfig = 'actualizaciones'; location.hash = '#/config'" title="Hay una versión nueva del programa">
            <Icono n="subir"/><span>Versión {{ store.actualizacion.version_nueva }} disponible</span>
          </button>
          <button class="btn ghost icon" @click="setTema(store.tema === 'oscuro' ? 'claro' : 'oscuro')" :title="store.tema === 'oscuro' ? 'Tema claro' : 'Tema oscuro'">
            <Icono :n="store.tema === 'oscuro' ? 'sol' : 'luna'"/>
          </button>
          <div class="menu-wrap" style="position:relative">
            <button class="row btn ghost" style="padding:0 6px" @click.stop="menu = !menu">
              <span class="avatar">{{ iniciales(store.usuario.nombre) }}</span>
              <span class="small" style="text-align:left;line-height:1.2"><b>{{ store.usuario.nombre }}</b><br><span class="muted xs">{{ store.usuario.rol === 'admin' ? 'Administrador' : 'Cajero' }}</span></span>
            </button>
            <div class="menu" v-if="menu">
              <button @click="location.hash = '#/cuenta'"><Icono n="usuario"/> Mi cuenta</button>
              <button @click="bloquear"><Icono n="candado"/> Bloquear pantalla</button>
              <hr><button @click="salir"><Icono n="salir"/> Cerrar sesión</button>
            </div>
          </div>
        </header>
        <component :is="vista" :key="claveVista"/>
      </div>
    </div>

    <div class="lock" v-if="store.bloqueado && store.usuario">
      <div class="card" style="width:380px;text-align:center">
        <div class="avatar" style="width:56px;height:56px;margin:0 auto 14px;font-size:18px">{{ iniciales(store.usuario.nombre) }}</div>
        <h2>{{ store.usuario.nombre }}</h2>
        <p class="muted small" style="margin:4px 0 18px">Pantalla bloqueada. Digite su PIN para continuar.</p>
        <input class="input lg center" type="password" inputmode="numeric" v-model="lockPin" placeholder="PIN" autofocus style="letter-spacing:.3em" @keydown.enter="desbloquear">
        <p class="err-text" style="margin-top:8px" v-if="lockError">{{ lockError }}</p>
        <div class="stack sm" style="margin-top:16px">
          <button class="btn primary lg block" @click="desbloquear" :disabled="!lockPin">Desbloquear</button>
          <button class="btn ghost block" @click="salir">Cambiar de usuario</button>
        </div>
      </div>
    </div>

    <DialogoPin/><DialogoConfirmar/><DialogoTexto/><VisorPdf/><Avisos/>`,
};

const app = createApp(Raiz);
registrar(app);
app.config.globalProperties.location = location;
app.config.errorHandler = (err, inst, info) => { console.error('[POS]', info, err); toast('Error en la pantalla: ' + (err.message || err), 'error', 8000); };
app.mount('#app');
