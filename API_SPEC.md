# API - Especificación de Endpoints (CRUD Completo)

## Base URL
```
https://alucarpin-app.onrender.com
```

## Autenticación
Todos los endpoints requieren header:
```
Authorization: Bearer {token}
```

Obtener token:
```http
POST /login
Content-Type: application/json

{
  "usuario": "administrador",
  "password": "AluCarpin2024"
}

Response 200:
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "usuario": "administrador",
  "rol": "admin",
  "ayudante_id": null
}
```

---

## 🆕 ENDPOINTS NUEVOS - FAENAS

### GET /faenas
Listar todas las faenas.

**Autenticación:** Requerida (admin)

**Ejemplo:**
```bash
curl -H "Authorization: Bearer TOKEN" \
  https://alucarpin-app.onrender.com/faenas
```

**Response 200:**
```json
[
  {
    "id": 1,
    "cliente": "CRISTALERIA JACA",
    "obra": "Reparación puertas",
    "fecha": "2026-09-11",
    "ubicacion": "Calle Principal 5",
    "poblacion": "Barcelona",
    "precio": 500.00,
    "ayudantes": "Sí"
  },
  {
    "id": 2,
    "cliente": "SALVADOR DE GUARDIOLA",
    "obra": "Cristalería comercial",
    "fecha": "2026-09-10",
    "ubicacion": "Centro comercial",
    "poblacion": "Terrassa",
    "precio": 1200.00,
    "ayudantes": "Sí"
  }
]
```

---

### POST /faenas
Crear nueva faena.

**Autenticación:** Requerida (admin)

**Body (application/json):**
```json
{
  "cliente": "NUEVO CLIENTE",
  "obra": "Descripción del trabajo",
  "fecha": "2026-09-15",
  "ubicacion": "Dirección completa",
  "poblacion": "Población",
  "precio": 750.50,
  "ayudantes": "Sí"
}
```

**Campos:**
- `cliente` (string, requerido): Nombre del cliente
- `obra` (string, opcional): Descripción del trabajo
- `fecha` (date, opcional): YYYY-MM-DD
- `ubicacion` (string, opcional): Dirección
- `poblacion` (string, opcional): Municipio
- `precio` (float, ≥0, opcional): Precio en €
- `ayudantes` (string, opcional): Sí/No

**Ejemplo:**
```bash
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente": "JACA",
    "obra": "Cristalería nueva",
    "fecha": "2026-09-15",
    "ubicacion": "Calle 1",
    "poblacion": "Barcelona",
    "precio": 500,
    "ayudantes": "Sí"
  }' \
  https://alucarpin-app.onrender.com/faenas
```

**Response 201 (Created):**
```json
{
  "id": 15,
  "cliente": "JACA",
  "obra": "Cristalería nueva",
  "fecha": "2026-09-15",
  "ubicacion": "Calle 1",
  "poblacion": "Barcelona",
  "precio": 500.00,
  "ayudantes": "Sí"
}
```

**Response 400 (Bad Request):**
```json
{
  "detail": "El cliente es requerido"
}
```

---

### PATCH /faenas/{id}
Editar faena existente.

**Autenticación:** Requerida (admin)

**URL:** `/faenas/15`

**Body (application/json):**
Solo los campos a actualizar:
```json
{
  "precio": 600.00,
  "estado": "En progreso"
}
```

**Ejemplo:**
```bash
curl -X PATCH \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"precio": 600.00}' \
  https://alucarpin-app.onrender.com/faenas/15
```

**Response 200:**
```json
{
  "id": 15,
  "cliente": "JACA",
  "obra": "Cristalería nueva",
  "fecha": "2026-09-15",
  "ubicacion": "Calle 1",
  "poblacion": "Barcelona",
  "precio": 600.00,
  "ayudantes": "Sí"
}
```

**Response 404 (Not Found):**
```json
{
  "detail": "Faena no encontrada"
}
```

---

### DELETE /faenas/{id}
Borrar faena.

**Autenticación:** Requerida (admin)

**URL:** `/faenas/15`

**Ejemplo:**
```bash
curl -X DELETE \
  -H "Authorization: Bearer TOKEN" \
  https://alucarpin-app.onrender.com/faenas/15
```

**Response 200:**
```json
{
  "eliminado": true,
  "id": 15
}
```

**Response 404 (Not Found):**
```json
{
  "detail": "Faena no encontrada"
}
```

---

## 🆕 ENDPOINTS NUEVOS - PRESUPUESTOS

### GET /presupuestos
Listar presupuestos con búsqueda opcional.

**Autenticación:** Requerida (usuario)

**Query Parameters:**
- `q` (string, opcional): Buscar por cliente o número presupuesto

**Ejemplo:**
```bash
curl -H "Authorization: Bearer TOKEN" \
  'https://alucarpin-app.onrender.com/presupuestos?q=JACA'
```

**Response 200:**
```json
[
  {
    "id": 1,
    "cliente": "CRISTALERIA JACA",
    "num_presupuesto": "2026-001",
    "fecha": "2026-09-11",
    "bruto": 1000.00,
    "iva": 210.00,
    "total_iva": 1210.00,
    "presupuesto_iva": 1210.00,
    "efectivo": 0.00,
    "estado": "Presupuesto",
    "presupuesto_final": 1210.00
  }
]
```

---

### POST /presupuestos
Crear nuevo presupuesto.

**Autenticación:** Requerida (admin)

**Body (application/json):**
```json
{
  "cliente": "NUEVO CLIENTE",
  "num_presupuesto": "2026-005",
  "fecha": "2026-09-15",
  "bruto": 1500.00,
  "iva": 315.00,
  "total_iva": 1815.00,
  "presupuesto_iva": 1815.00,
  "efectivo": 0.00,
  "estado": "Presupuesto",
  "presupuesto_final": 1815.00
}
```

**Campos:**
- `cliente` (string, requerido)
- `num_presupuesto` (string, opcional, único): Número identificador
- `fecha` (date, opcional): YYYY-MM-DD
- `bruto` (float, ≥0, opcional): Base sin IVA
- `iva` (float, ≥0, opcional): Cantidad de IVA
- `total_iva` (float, ≥0, opcional): Total con IVA
- `presupuesto_iva` (float, ≥0, opcional): Presupuesto cliente
- `efectivo` (float, ≥0, opcional): Pagado en efectivo
- `estado` (string, opcional): "Presupuesto", "Aceptado", "Rechazado", etc.
- `presupuesto_final` (float, ≥0, opcional): Importe final

**Ejemplo:**
```bash
curl -X POST \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente": "JACA",
    "num_presupuesto": "2026-005",
    "fecha": "2026-09-15",
    "bruto": 2000,
    "iva": 420,
    "total_iva": 2420,
    "presupuesto_iva": 2420,
    "efectivo": 0,
    "estado": "Presupuesto",
    "presupuesto_final": 2420
  }' \
  https://alucarpin-app.onrender.com/presupuestos
```

**Response 201 (Created):**
```json
{
  "id": 8,
  "cliente": "JACA",
  "num_presupuesto": "2026-005",
  "fecha": "2026-09-15",
  "bruto": 2000.00,
  "iva": 420.00,
  "total_iva": 2420.00,
  "presupuesto_iva": 2420.00,
  "efectivo": 0.00,
  "estado": "Presupuesto",
  "presupuesto_final": 2420.00
}
```

---

### PATCH /presupuestos/{id}
Editar presupuesto.

**Autenticación:** Requerida (admin)

**URL:** `/presupuestos/8`

**Body (application/json):**
```json
{
  "estado": "Aceptado",
  "presupuesto_final": 2300.00
}
```

**Ejemplo:**
```bash
curl -X PATCH \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"estado": "Aceptado"}' \
  https://alucarpin-app.onrender.com/presupuestos/8
```

**Response 200:**
```json
{
  "id": 8,
  "cliente": "JACA",
  "num_presupuesto": "2026-005",
  "fecha": "2026-09-15",
  "bruto": 2000.00,
  "iva": 420.00,
  "total_iva": 2420.00,
  "presupuesto_iva": 2420.00,
  "efectivo": 0.00,
  "estado": "Aceptado",
  "presupuesto_final": 2420.00
}
```

---

### DELETE /presupuestos/{id}
Borrar presupuesto.

**Autenticación:** Requerida (admin)

**URL:** `/presupuestos/8`

**Ejemplo:**
```bash
curl -X DELETE \
  -H "Authorization: Bearer TOKEN" \
  https://alucarpin-app.onrender.com/presupuestos/8
```

**Response 200:**
```json
{
  "eliminado": true,
  "id": 8
}
```

---

## Fichajes, pagos y validacion

```http
GET    /ayudantes/{id}/fichajes
POST   /fichajes
PATCH  /fichajes/{id}
DELETE /fichajes/{id}
PATCH  /fichajes/{id}/pago
GET    /fichajes/{id}/pago
GET    /ayudantes/{id}/jornadas-pago?desde=YYYY-MM-DD&hasta=YYYY-MM-DD
PATCH  /fichajes/{id}/validacion
```

Al crear un fichaje como ayudante, debe seleccionarse un destino existente mediante `obra_catalogo`: no se generan faenas, presupuestos ni reparaciones nuevos. El administrador mantiene la creacion de destinos provisionales cuando registra sin referencia. El pago de la jornada se guarda en `pagos_jornadas` y no depende de la validacion contable.

El pago corresponde a una fecha y ayudante, incluidos fines de semana. El endpoint de jornadas devuelve una fila por fecha con `id` representativo, `fecha`, `obra`, `fichajes_ids`, `pago`, `revision` y `pagos_existentes`. Consultar o modificar el pago desde cualquier fichaje de esa fecha resuelve el mismo pago. Se conserva el identificador y la fecha del pago existente.

Varios pagos historicos generan `revision: true`, estado `Revisar` e importes agregados `null` (no se suman automaticamente). PATCH devuelve 409 sin modificar ninguno. Un pago historico de gastos tambien bloquea PATCH con 409 para evitar duplicarlo. Los rangos invertidos devuelven 400 en jornadas y 422 al crear/modificar una liquidacion. Las liquidaciones cuentan fechas distintas confirmadas, incluyendo sabados y domingos.

### Ejecucion y cobro de obras

`GET /alarmas` incluye trabajos propios, faenas y presupuestos Aceptado o Completado, de fechas pasadas y futuras. Emite `tipo: trabajo`, `origen: propio|faena|presupuesto`, `referencia_id`, `estado_ejecucion: Pendiente|Terminado` y estado visible `Pendiente|Archivado`; si queda dinero pendiente emite tambien `tipo: cobro`. Para faenas y presupuestos devuelve `importe`, `importe_cobrado` y `pendiente_cobro`, calculados con pagos_faenas/pagos_ingresos. Los importes cero no generan cobro pendiente. Presupuesto y Rechazado quedan fuera.

`PATCH /trabajos/{id}/ejecucion?origen=propio|faena|presupuesto` recibe `{"estado":"Pendiente"}` o `{"estado":"Terminado"}` y no modifica el cobro. `origen` es propio por defecto para preservar los clientes anteriores; evita mezclar identificadores de tablas distintas. Se almacena en estados_ejecucion_trabajos, estados_ejecucion_faenas o estados_ejecucion_presupuestos, creadas idempotentemente al arrancar y definidas en `migracion_estado_ejecucion.sql`. Un id inexistente devuelve 404.

`GET /trabajos` comparte estos estados y pendientes con Alarmas; los presupuestos no aceptados tienen estado_ejecucion null. Completado historico conserva la interpretacion anterior de terminado/cobrado sin fabricar movimientos monetarios; PATCH de estado comercial conserva la ejecucion previa.

`PATCH /seguimientos/{id}/estado` recibe `{"estado":"Realizado"}` (tambien admite Pendiente y Archivado) y modifica exclusivamente el estado, conservando el resto de la nota. Todos estos endpoints requieren administrador.

---

## Códigos de Respuesta HTTP

| Código | Significado |
|--------|------------|
| **200** | OK - Solicitud exitosa |
| **201** | Created - Recurso creado exitosamente |
| **400** | Bad Request - Datos inválidos |
| **401** | Unauthorized - Token inválido/expirado |
| **403** | Forbidden - Sin permisos (no admin) |
| **404** | Not Found - Recurso no existe |
| **500** | Server Error - Error interno |

---

## Ejemplo de Flujo Completo (Client JavaScript)

```javascript
// 1. Login
const loginRes = await fetch('https://alucarpin-app.onrender.com/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    usuario: 'administrador',
    password: 'AluCarpin2024'
  })
});
const { token } = await loginRes.json();

// 2. Crear faena
const faenaRes = await fetch('https://alucarpin-app.onrender.com/faenas', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    cliente: 'JACA',
    obra: 'Nueva obra',
    fecha: '2026-09-15',
    precio: 500
  })
});
const faena = await faenaRes.json();
console.log('Faena creada:', faena);

// 3. Editar faena
const editRes = await fetch(`https://alucarpin-app.onrender.com/faenas/${faena.id}`, {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    precio: 600
  })
});
const faenaActualizada = await editRes.json();

// 4. Listar faenas
const listRes = await fetch('https://alucarpin-app.onrender.com/faenas', {
  headers: { 'Authorization': `Bearer ${token}` }
});
const faenas = await listRes.json();
console.log('Todas las faenas:', faenas);

// 5. Borrar faena
const delRes = await fetch(`https://alucarpin-app.onrender.com/faenas/${faena.id}`, {
  method: 'DELETE',
  headers: { 'Authorization': `Bearer ${token}` }
});
console.log('Faena eliminada');
```

---

## Testing con cURL

```bash
# Guardar token
TOKEN=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"usuario":"administrador","password":"AluCarpin2024"}' \
  https://alucarpin-app.onrender.com/login | jq -r '.token')

# Crear faena
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente": "TEST",
    "obra": "Test obra",
    "precio": 100
  }' \
  https://alucarpin-app.onrender.com/faenas

# Listar faenas
curl -H "Authorization: Bearer $TOKEN" \
  https://alucarpin-app.onrender.com/faenas | jq

# Editar faena
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"precio": 200}' \
  https://alucarpin-app.onrender.com/faenas/1

# Borrar faena
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  https://alucarpin-app.onrender.com/faenas/1
```

---

## Status: ✅ Implementado
- Fecha: 2026-09-11
- Endpoints CRUD: 6 nuevos (POST/PATCH/DELETE faenas + presupuestos)
- Validación: Python py_compile sin errores
- Documentación: Completa
## Catalogo compartido de clientes y obras

`GET /catalogo-obras` requiere una sesion autenticada y esta disponible para administradores y ayudantes. Devuelve una lista de objetos con `referencia`, `tipo`, `id`, `cliente`, `obra`, `ubicacion`, `poblacion` y `num_presupuesto`, sin importes. El catalogo se obtiene de las faenas con obra, los presupuestos y las reparaciones existentes; no requiere una tabla ni migracion nueva.

En `POST /fichajes`, los ayudantes deben enviar `obra_catalogo` (por ejemplo `faena:25`, `presupuesto:10` o `reparacion:20`). El servidor toma los nombres, la ubicacion, el tipo y los vinculos del registro existente, no del texto enviado. Una referencia inexistente o incompatible con el tipo devuelve HTTP 400. El tipo `pendiente` acepta cualquier entrada y se resuelve al tipo del catalogo.

En `PATCH /fichajes/{id}`, `obra_catalogo` permite seleccionar otra obra y actualiza todos los vinculos, sin tocar pagos ni otros fichajes. Cambiar el destino reinicia la revision a `Pendiente de revisar`. Un ayudante sin referencia solo puede conservar los datos del destino existente y cambiar la fecha. El administrador mantiene la capacidad de crear nombres mediante los endpoints administrativos existentes.
