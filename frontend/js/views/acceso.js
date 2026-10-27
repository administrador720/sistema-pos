// Configuración inicial (primera vez) e inicio de sesión
import { api, sesion } from '../api.js';
import { store, errorToast } from '../store.js';

const { ref, reactive, computed, onMounted } = Vue;

export const Setup = {
  emits: ['listo'],
  setup(p, { emit }) {
    const f = reactive({ negocio: '', nit: '', direccion: '', telefono: '', nombre: '', usuario: 'admin', password: '', password2: '', pin: '' });
    const cargando = ref(false), error = ref('');
    const valido = computed(() => f.negocio.trim() && f.nombre.trim() && f.usuario.trim() && f.password.length >= 6
      && f.password === f.password2 && /^\d{4,6}$/.test(f.pin));
    async function crear() {
      error.value = ''; cargando.value = true;
      try {
        const r = await api.post('/api/setup', {
          negocio: { nombre: f.negocio, nit: f.nit, direccion: f.direccion, telefono: f.telefono },
          admin: { nombre: f.nombre, usuario: f.usuario, password: f.password, pin: f.pin } });
        sesion.guardar(r.token); store.configurado = true; emit('listo');
      } catch (e) { error.value = e.message; } finally { cargando.value = false; }
    }
    return { f, cargando, error, valido, crear };
  },
  template: `
    <div class="auth">
      <div class="card" style="max-width:640px">
        <div class="logo"><Icono n="tienda" class="ico xl" style="width:28px;height:28px"/></div>
        <h1>Bienvenido</h1>
        <p class="muted" style="margin:6px 0 22px">Vamos a dejar listo su punto de venta. Solo toma un minuto y se hace una vez.</p>
        <form class="stack lg" @submit.prevent="crear">
          <div class="stack">
            <h3>1. Su negocio</h3>
            <div class="field"><label>Nombre del supermercado</label><input class="input" v-model="f.negocio" placeholder="Supermercado La Esquina" autofocus></div>
            <div class="grid c3">
              <div class="field"><label>NIT (opcional)</label><input class="input" v-model="f.nit"></div>
              <div class="field"><label>Teléfono</label><input class="input" v-model="f.telefono"></div>
              <div class="field"><label>Dirección</label><input class="input" v-model="f.direccion"></div>
            </div>
          </div>
          <div class="stack">
            <h3>2. Administrador del sistema</h3>
            <div class="grid c2">
              <div class="field"><label>Su nombre</label><input class="input" v-model="f.nombre" placeholder="Ana Gómez"></div>
              <div class="field"><label>Usuario para ingresar</label><input class="input" v-model="f.usuario" autocapitalize="off"><span class="hint">Con este usuario (no con su nombre) entrará siempre. Anótelo.</span></div>
              <div class="field"><label>Contraseña (mín. 6 caracteres)</label><input class="input" type="password" v-model="f.password" autocomplete="new-password"></div>
              <div class="field"><label>Repetir contraseña</label><input class="input" type="password" v-model="f.password2" autocomplete="new-password"></div>
            </div>
            <div class="field" style="max-width:260px"><label>PIN de autorización (4 a 6 números)</label>
              <input class="input" type="password" inputmode="numeric" maxlength="6" v-model="f.pin" placeholder="••••" style="letter-spacing:.3em">
              <span class="hint">Se usa para autorizar anulaciones, devoluciones y descuentos grandes.</span></div>
            <span class="err-text" v-if="f.password2 && f.password !== f.password2">Las contraseñas no coinciden.</span>
          </div>
          <div class="alert danger" v-if="error">{{ error }}</div>
          <button class="btn primary lg block" :disabled="!valido || cargando">{{ cargando ? 'Creando…' : 'Comenzar' }}</button>
        </form>
      </div>
    </div>`,
};

export const Login = {
  emits: ['listo'],
  setup(p, { emit }) {
    const usuario = ref(''), password = ref(''), error = ref(''), cargando = ref(false), nombre = ref('');
    onMounted(() => { try { usuario.value = localStorage.getItem('pos_ultimo_usuario') || ''; } catch (e) { /* */ } });
    async function entrar() {
      error.value = ''; cargando.value = true;
      try {
        const r = await api.post('/api/auth/login', { usuario: usuario.value, password: password.value });
        sesion.guardar(r.token);
        try { localStorage.setItem('pos_ultimo_usuario', usuario.value); } catch (e) { /* */ }
        emit('listo');
      } catch (e) { error.value = e.message; password.value = ''; } finally { cargando.value = false; }
    }
    return { usuario, password, error, cargando, entrar, store };
  },
  template: `
    <div class="auth">
      <div class="card">
        <div class="logo"><Icono n="tienda" class="ico xl" style="width:28px;height:28px"/></div>
        <h1>Iniciar sesión</h1>
        <p class="muted" style="margin:6px 0 22px">Ingrese con su usuario y contraseña.</p>
        <form class="stack" @submit.prevent="entrar">
          <div class="field"><label>Usuario</label><input class="input lg" v-model="usuario" autocapitalize="off" autocomplete="username" :autofocus="!usuario">
            <span class="hint">El usuario que eligió al configurar (por ejemplo «admin»), no su nombre.</span></div>
          <div class="field"><label>Contraseña</label><input class="input lg" type="password" v-model="password" autocomplete="current-password" :autofocus="!!usuario"></div>
          <div class="alert danger" v-if="error">{{ error }}</div>
          <button class="btn primary lg block" :disabled="!usuario || !password || cargando">{{ cargando ? 'Ingresando…' : 'Ingresar' }}</button>
          <details class="small muted"><summary style="cursor:pointer">¿Olvidó su contraseña?</summary>
            <p style="margin-top:8px">Si es cajero, pídale al administrador que la cambie en <b>Configuración → Usuarios</b>.</p>
            <p style="margin-top:6px">Si es el administrador: cierre el programa y abra <b>restablecer_clave.bat</b> en la carpeta del programa. Necesita estar en este computador.</p></details>
        </form>
      </div>
    </div>`,
};
