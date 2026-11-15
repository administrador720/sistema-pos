// Conectar con el computador (vincular) e iniciar sesión
import { API_APP, ErrorApp, estado, get, post, guardarVinculo, guardarSesion, normalizarServidor } from '../api.js';
import { aviso, avisoError } from '../componentes.js';
import { escanear, hayCamara } from '../escaner.js';

const { ref } = Vue;

export const Vincular = {
  setup() {
    const direccion = ref(estado.nativo ? (estado.servidor || '').replace(/^https?:\/\//, '') : ''), codigo = ref(''), nombre = ref('Mi celular');
    const enviando = ref(false), camara = hayCamara();

    async function canjear(servidor, cod) {
      enviando.value = true;
      const antes = estado.servidor;
      if (estado.nativo) estado.servidor = servidor;     // la app instalada no sabe todavía dónde está el computador
      try {
        const info = await get('/api/movil/info');
        if (info.api !== API_APP) throw new ErrorApp('La app del celular y el programa del computador tienen versiones distintas. Actualice los dos a la versión más reciente.', 'VERSION');
        const r = await post('/api/movil/vincular', { codigo: cod, nombre: nombre.value.trim() || 'Mi celular' });
        guardarVinculo({ servidor, llave: r.token, negocio: r.negocio });
        aviso('Celular vinculado con ' + (r.negocio || 'el sistema') + '.', 'ok');
        location.hash = '#/entrar';
      } catch (e) { if (estado.nativo) estado.servidor = antes; avisoError(e); }
      finally { enviando.value = false; }
    }
    async function porQR() {
      try {
        const t = await escanear({ soloQR: true });
        if (!t) return;
        let d = null;
        try { d = JSON.parse(t); } catch (e) { /* no es nuestro QR */ }
        if (!d || !d.url || !d.codigo) return aviso('Ese QR no es del sistema. Use el que aparece en Configuración → Celulares.', 'warn', 6000);
        await canjear(String(d.url), String(d.codigo));
      } catch (e) { avisoError(e); }
    }
    const aMano = () => canjear(estado.nativo ? normalizarServidor(direccion.value) : estado.servidor, codigo.value.trim());
    return { direccion, codigo, nombre, enviando, camara, porQR, aMano, estado };
  },
  template: `
    <div class="pantalla"><div class="centro-pantalla">
      <div class="center pila"><div class="chip acento" style="align-self:center"><Icono n="tienda"/> POS Móvil</div>
        <h1>Conectar con el computador</h1>
        <p class="muted">En el computador abra el sistema y entre a <b>Configuración → Celulares → Vincular un celular</b>.</p></div>
      <button v-if="camara" class="btn primario grande bloque" :disabled="enviando" @click="porQR"><Icono n="camara"/> Escanear el QR del computador</button>
      <div class="tarjeta">
        <h3>{{ camara ? 'O escribir los datos' : 'Escribir el código' }}</h3>
        <label class="campo" v-if="estado.nativo">Dirección del computador<input class="input" v-model="direccion" placeholder="192.168.1.20" inputmode="decimal" autocapitalize="off"></label>
        <label class="campo">Código de 6 números<input class="input grande num" v-model="codigo" inputmode="numeric" maxlength="6" placeholder="000000" autocomplete="one-time-code" @keydown.enter="aMano"></label>
        <label class="campo">Nombre de este celular<input class="input" v-model="nombre"></label>
        <button class="btn primario bloque" :disabled="enviando || codigo.length < 6 || (estado.nativo && !direccion.trim())" @click="aMano">{{ enviando ? 'Conectando…' : 'Vincular' }}</button>
      </div>
      <p class="xs muted center">Tanto el celular como el computador deben estar en el mismo Wi-Fi.</p>
    </div></div>`,
};

export const Entrar = {
  setup() {
    const usuario = ref((() => { try { return localStorage.getItem('posm_ultimo_usuario') || ''; } catch (e) { return ''; } })()), clave = ref(''), enviando = ref(false);
    async function entrar() {
      enviando.value = true;
      try {
        const r = await post('/api/auth/login', { usuario: usuario.value.trim(), password: clave.value });
        guardarSesion(r.token, r.usuario);
        try { localStorage.setItem('posm_ultimo_usuario', usuario.value.trim()); } catch (e) { /* */ }
        location.hash = '#/';
      } catch (e) { clave.value = ''; avisoError(e); }
      finally { enviando.value = false; }
    }
    return { usuario, clave, enviando, entrar, estado };
  },
  template: `
    <div class="pantalla"><div class="centro-pantalla">
      <div class="center pila"><div class="chip acento" style="align-self:center"><Icono n="tienda"/> {{ estado.negocio || 'POS Móvil' }}</div>
        <h1>Iniciar sesión</h1><p class="muted">Solo el administrador puede usar la app del celular.</p></div>
      <div class="tarjeta">
        <label class="campo">Usuario<input class="input" v-model="usuario" autocapitalize="off" autocomplete="username"></label>
        <label class="campo">Contraseña<input class="input" type="password" v-model="clave" autocomplete="current-password" @keydown.enter="entrar"></label>
        <button class="btn primario bloque" :disabled="enviando || !usuario || !clave" @click="entrar">{{ enviando ? 'Ingresando…' : 'Ingresar' }}</button>
      </div>
    </div></div>`,
};
