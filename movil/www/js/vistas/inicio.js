// Pantalla de inicio: los cinco usos del celular
import { estado, get, cerrarSesion, olvidarDispositivo, post } from '../api.js';
import { aviso } from '../componentes.js';

const { ref, onMounted } = Vue;

export const Inicio = {
  setup() {
    const turno = ref(undefined), menu = ref(false);
    onMounted(async () => { try { turno.value = (await get('/api/turnos/actual', { silencioso: true })).turno; } catch (e) { turno.value = undefined; } });
    function salir() { post('/api/auth/logout', {}, { silencioso: true }).catch(() => {}); cerrarSesion(); location.hash = '#/entrar'; }
    function desvincular() {
      if (!confirm('¿Quitar este celular del sistema?\n\nPara volver a usarlo hay que vincularlo de nuevo desde el computador.')) return;
      post('/api/auth/logout', {}, { silencioso: true }).catch(() => {}); olvidarDispositivo(); aviso('Este celular ya no está vinculado.', 'ok'); location.hash = '#/vincular';
    }
    return { estado, turno, menu, salir, desvincular };
  },
  template: `
    <Pantalla :titulo="estado.negocio || 'POS Móvil'" atras="">
      <template #acciones><button class="btn icono" @click="menu = !menu" aria-label="Menú"><Icono n="candado"/></button></template>
      <div class="tarjeta" v-if="menu">
        <div class="small muted">Sesión de <b>{{ estado.usuario && estado.usuario.nombre }}</b></div>
        <button class="btn bloque" @click="salir"><Icono n="salir"/> Cerrar sesión</button>
        <button class="btn bloque peligro" @click="desvincular"><Icono n="basura"/> Quitar este celular</button>
      </div>
      <div class="fila"><span class="chip" :class="turno === undefined ? '' : turno ? 'ok' : 'warn'">{{ turno === undefined ? 'Revisando la caja…' : turno ? 'Caja abierta · ' + turno.usuario : 'Caja cerrada' }}</span></div>
      <div class="tiles">
        <a class="tile" href="#/consultar"><Icono n="buscar"/><span>Consultar precio y stock</span></a>
        <a class="tile" href="#/conteo"><Icono n="conteo"/><span>Contar inventario</span></a>
        <a class="tile" href="#/compras"><Icono n="factura"/><span>Facturas de compra</span></a>
        <a class="tile" href="#/venta"><Icono n="carrito"/><span>Vender y cobrar</span></a>
        <a class="tile" href="#/panel" style="grid-column:span 2"><Icono n="panel"/><span>Panel de ventas</span><small>Ventas, margen y alertas</small></a>
      </div>
    </Pantalla>`,
};
