// POS Móvil: arranque, rutas y estructura general
import { API_APP, estado, get } from './api.js';
import { Avisos, aviso, registrar } from './componentes.js';
import { Vincular, Entrar } from './vistas/acceso.js';
import { Inicio } from './vistas/inicio.js';
import { Consultar } from './vistas/consultar.js';
import { Conteo } from './vistas/conteo.js';
import { Compras } from './vistas/compras.js';
import { Venta } from './vistas/venta.js';
import { Panel } from './vistas/panel.js';

const { createApp, ref, computed, onMounted, onBeforeUnmount } = Vue;

const VISTAS = { '': Inicio, vincular: Vincular, entrar: Entrar, consultar: Consultar, conteo: Conteo, compras: Compras, venta: Venta, panel: Panel };

const Raiz = {
  components: { Avisos },
  setup() {
    const ruta = ref('');
    const leer = () => { ruta.value = (location.hash || '#/').replace(/^#\/?/, '').split('/')[0]; };
    // sin celular vinculado solo se ve «vincular»; sin sesión, «entrar»
    const nombre = computed(() => {
      if (!estado.llave || !estado.servidor) return 'vincular';
      if (!estado.sesion) return 'entrar';
      if (ruta.value === 'vincular' || ruta.value === 'entrar') return '';
      return VISTAS[ruta.value] ? ruta.value : '';
    });
    const vista = computed(() => VISTAS[nombre.value]);
    onMounted(async () => {
      leer(); window.addEventListener('hashchange', leer);
      if (estado.llave && estado.servidor) {   // ¿el programa del computador sigue siendo compatible?
        try { const i = await get('/api/movil/info', { silencioso: true }); if (i.api !== API_APP) aviso('Hay una versión distinta del programa. Actualice la app del celular.', 'warn', 9000); } catch (e) { /* sin conexión: se verá al usar */ }
      }
    });
    onBeforeUnmount(() => window.removeEventListener('hashchange', leer));
    return { vista, nombre };
  },
  template: `<component :is="vista" :key="nombre"/><Avisos/>`,
};

const app = createApp(Raiz);
registrar(app);
app.config.errorHandler = (err, inst, info) => { console.error('[POS Móvil]', info, err); aviso('Error en la pantalla: ' + (err.message || err), 'error', 7000); };
app.mount('#app');
