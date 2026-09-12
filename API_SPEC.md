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
PATCH  /fichajes/{id}/validacion
```

Al crear un fichaje, la aplicacion genera automaticamente el destino provisional segun `tipo_destino`: `faena`, `presupuesto` o `reparacion`. El pago de la jornada se guarda en `pagos_jornadas` y no depende de la validacion contable.

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
