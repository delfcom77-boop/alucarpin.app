# AlucarpinSamitier - Sistema de Gestión Bidireccional

Sistema profesional de gestión empresarial con sincronización bidireccional entre aplicación de escritorio (PyQt6) y aplicación web (FastAPI + HTML/JS).

---

## 📋 Descripción General

**AlucarpinSamitier** es una solución integral que permite:

- ✅ Gestionar ayudantes, fichajes, faenas, presupuestos, gastos y pagos
- ✅ Sincronización automática entre desktop y web
- ✅ Almacenamiento centralizado en Supabase (PostgreSQL)
- ✅ Acceso desde PC (aplicación de escritorio) y navegador web
- ✅ Transacciones seguras con autenticación JWT

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                     SUPABASE (PostgreSQL)                   │
│  Centro de datos: ayudantes, faenas, presupuestos, etc.     │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
      ↓ sincronizar_datos_app()    sincronizar_datos_locales()↓
             │                               │
┌────────────┴────────────────┐  ┌──────────┴──────────────────┐
│    DESKTOP (PyQt6)          │  │    WEB (FastAPI + HTML/JS)  │
│ • menu_principal.py         │  │ • api_central.py            │
│ • form_contabilidad.py      │  │ • app_web/administrador.html│
│ • sincronizacion_app.py     │  │ • app_web/agenda.html       │
│ • SQLite (empresa.db)       │  │ • SQLite (empresa.db)       │
│                             │  │ • Render (https://...)      │
└─────────────────────────────┘  └─────────────────────────────┘
```

### Componentes Principales

| Componente | Tipo | Función |
|-----------|------|---------|
| **Supabase** | Backend Central | Base de datos PostgreSQL, autenticación |
| **Desktop App** | PyQt6 GUI | Interfaz de escritorio con caché local |
| **Web App** | FastAPI + HTML/JS | Interfaz web, endpoints REST |
| **Sincronización** | Python | Bidireccional automática y manual |

---

## 🗄️ Modelo de Datos

### Tablas Principales

#### `ayudantes`
```sql
id (INTEGER) | nombre (TEXT) | activo (INTEGER)
```

#### `fichajes_ayudantes`
```sql
 id | ayudante_id | fecha | tipo_destino | cliente | obra | ubicacion | poblacion
| num_presupuesto | faena_id_vinculada | presupuesto_id | trabajo_propio_id
| estado_revision | confirmado_ayudante | sincronizado
```

#### `pagos_jornadas`
Registra el pago de cada jornada de forma independiente de su faena, presupuesto o reparacion. Una jornada puede estar `Pagado` y continuar `Pendiente de revisar` hasta que el administrador valide el trabajo.

#### `faenas`
```sql
id | cliente | obra | fecha | ubicacion | poblacion | precio | ayudantes
```

#### `presupuestos`
```sql
id | cliente | num_presupuesto | fecha | bruto | iva | total_iva
| presupuesto_iva | efectivo | estado | presupuesto_final
```

#### `pagos_faenas`, `pagos_gastos`, `pagos_ingresos`
```sql
id | {faena|presupuesto}_id | fecha | importe_iva | importe_b | observaciones | forma_pago
```

---

## 🔄 Sincronización Bidireccional

### Flujo 1: Descarga (Supabase → Local)

```python
# EmpresaPython/sincronizacion_app.py
sincronizar_datos_app()
└── Descarga de Supabase:
    ├── Ayudantes (merge por ID)
    ├── Fichajes (merge por natural keys)
    ├── Liquidaciones
    ├── Trabajos propios
    ├── Citas y seguimientos
    └── Retorna: {"ayudantes": 2, "fichajes": 6, ...}
```

**Botón en UI:** "Actualizar fichajes de la app"

### Flujo 2: Procesamiento Local

```
1. El ayudante registra el tipo de trabajo y sus datos.
2. La app crea automaticamente una faena, presupuesto provisional o reparacion.
3. El administrador revisa y valida el trabajo desde la app o el programa.
4. El pago de la jornada se registra independientemente (PATCH /fichajes/{id}/pago).
```

### Flujo 3: Subida (Local → Supabase)

```python
# EmpresaPython/sincronizacion_app.py
sincronizar_datos_locales()
└── Sube a Supabase:
    ├── Faenas (match: cliente/obra/fecha/ubicación)
    ├── Presupuestos (match: número)
    ├── Pagos de ingresos/faenas/gastos
    ├── Liquidaciones
    ├── Gastos de faenas/presupuestos
    └── Retorna: {"faenas": 5, "presupuestos": 2, ...}
```

**Botón en UI:** "ENVIAR DATOS LOCALES A LA APP"

---

## 📡 API REST - Endpoints

### Autenticación

```http
POST /login
{
  "usuario": "administrador",
  "password": "AluCarpin2024"
}
→ {"token": "jwt_token", "usuario": "administrador", "rol": "admin", "ayudante_id": null}
```

### Ayudantes

```http
GET    /ayudantes                          # Listar
POST   /ayudantes                          # Crear
PATCH  /ayudantes/{id}                     # Editar
DELETE /ayudantes/{id}                     # Borrar
```

### Fichajes

```http
GET    /ayudantes/{id}/fichajes            # Por rango de fechas
POST   /fichajes                           # Crear
PATCH  /fichajes/{id}                      # Editar
DELETE /fichajes/{id}                      # Borrar
PATCH  /fichajes/{id}/vinculacion          # Vincular a faena
PATCH  /fichajes/{id}/pago                 # Registrar pago
GET    /fichajes/{id}/pago                 # Consultar pago
```

### Faenas (NUEVO CRUD)

```http
GET    /faenas                             # Listar todas
POST   /faenas                             # Crear nueva faena
PATCH  /faenas/{id}                        # Editar faena
DELETE /faenas/{id}                        # Borrar faena
```

**Modelo de datos (POST/PATCH):**
```json
{
  "cliente": "CRISTALERIA JACA",
  "obra": "Reparación puertas",
  "fecha": "2026-09-11",
  "ubicacion": "Calle Principal 5",
  "poblacion": "Barcelona",
  "precio": 500.00,
  "ayudantes": "Sí"
}
```

### Presupuestos (NUEVO CRUD)

```http
GET    /presupuestos                       # Listar todas
POST   /presupuestos                       # Crear nuevo presupuesto
PATCH  /presupuestos/{id}                  # Editar presupuesto
DELETE /presupuestos/{id}                  # Borrar presupuesto
```

**Modelo de datos (POST/PATCH):**
```json
{
  "cliente": "SALVADOR DE GUARDIOLA",
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
```

### Trabajos, Citas, Seguimientos

### Gestión desde la web

En `/app/administrador.html`, los usuarios administradores pueden gestionar directamente faenas y presupuestos:

- Crear, editar y borrar registros desde sus formularios y tablas.
- Cancelar una edición sin modificar el registro existente.
- Buscar faenas por cliente, obra, ubicación o población.
- Buscar presupuestos por cliente o número.
- Exportar a CSV las filas visibles después de aplicar un filtro.
- Validar clientes vacíos antes de enviar el formulario; la API aplica la misma validación.

Los archivos CSV incluyen encabezados, usan `;` como separador y excluyen la columna de acciones para abrirlos directamente en Excel.

```http
GET    /trabajos
POST   /trabajos
PATCH  /trabajos/{id}
DELETE /trabajos/{id}

GET    /citas
POST   /citas
PATCH  /citas/{id}
DELETE /citas/{id}

GET    /seguimientos
POST   /seguimientos
PATCH  /seguimientos/{id}
DELETE /seguimientos/{id}
```

---

## 🚀 Instalación y Configuración

### Requisitos

- Python 3.14+ (para compilar .exe)
- Supabase (PostgreSQL remoto)
- Render.com (hosting web gratuito) o servidor propio

### Backend (API)

```bash
# En alucarpin.app/
pip install -r requirements-api.txt

# Configurar variables de entorno
export DATABASE_URL="postgresql://usuario:password@host/bd"
export ALUCARPIN_DATABASE="/ruta/a/empresa.db"
export ALUCARPIN_SESSION_SECRET="tu-secreto"

# Ejecutar
uvicorn api_central:app --host 0.0.0.0 --port 8000
```

### Desktop App

```bash
# En EmpresaPython/
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-api.txt

# Configurar variable de entorno (en terminal que ejecuta app)
export DATABASE_URL="postgresql://usuario:password@host/bd"

# Ejecutar
python menu_principal.py

# Compilar a .exe
pyinstaller AlucarpinSamitier.spec
# → Genera: dist/AlucarpinSamitier.exe
```

### Compilación (.exe)

```bash
cd EmpresaPython
pyinstaller AlucarpinSamitier.spec
```

El archivo `AlucarpinSamitier.exe` se genera en `dist/AlucarpinSamitier/`.

---

## 🔐 Seguridad

- **Autenticación:** JWT (Bearer token)
- **Autorización:** Roles (admin, usuario)
- **Contraseñas:** Hash PBKDF2 + salt
- **HTTPS:** Requerido en producción (Render)
- **CORS:** Configurado para desarrollo local

---

## 📊 Flujo de Prueba Completo

### Paso 1: Iniciar Desktop App
```
1. Ejecutar: python menu_principal.py (con DATABASE_URL)
2. Click: CENTRO DE CONTROL
3. Click: "Actualizar fichajes de la app"
   → Descarga ayudantes y fichajes de Supabase
```

### Paso 2: Procesar Datos Localmente
```
4. Seleccionar fichaje
5. Vincular a faena (dropdown)
6. Registrar pago
   → Se envía PATCH /fichajes/{id}/pago
```

### Paso 3: Sincronizar a Supabase
```
7. Click: "ENVIAR DATOS LOCALES A LA APP"
   → Sube: faenas, presupuestos, fichajes, gastos, pagos
```

### Paso 4: Verificar en Web App
```
8. Abrir: https://alucarpin-app.onrender.com/app/login.html
9. Login: usuario=administrador, password=AluCarpin2024
10. Click: Ayudantes
    → Debe mostrar 2 ayudantes + 6 fichajes (del paso 1)
```

---

## 🧪 Validación

**Última validación (2026-09-11):**

✅ Descarga: 2 ayudantes + 6 fichajes desde Supabase  
✅ Procesamiento: Pago registrado correctamente  
✅ Subida: 5 faenas, 2 presupuestos, 9 fichajes, 1 gasto  
✅ Web: Todos los datos visibles en administrador.html  

---

## 📝 Variables de Entorno

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://user:pass@host/db` | Conexión Supabase |
| `ALUCARPIN_DATABASE` | `/app/empresa.db` | Ruta SQLite local |
| `ALUCARPIN_SESSION_SECRET` | `abc123def456` | Secreto JWT |
| `PORT` | `8000` | Puerto del servidor |

---

## 🛠️ Troubleshooting

### "DATABASE_URL es None"
→ Configura la variable de entorno en la terminal que ejecuta app_principal.py

### "Render se suspende después de 15 min"
→ Es normal en plan free. Upgrade a Standard ($7/mes) para instancia siempre activa

### "Fichajes no se descargan"
→ Verifica que DATABASE_URL apunta a Supabase correcto

### "Campos vacíos al sincronizar"
→ Revisa sincronizacion_app.py líneas 500-850 (validaciones de datos)

---

## 📦 Estructura de Carpetas

```
alucarpin.app/
├── api_central.py              # API FastAPI principal
├── autenticacion.py            # JWT y hashing
├── base_datos.py               # Conexión SQLite/Postgres
├── app_web/
│   ├── login.html              # Pantalla de login
│   ├── inicio.html             # Menú principal
│   ├── administrador.html      # Gestión de ayudantes/fichajes
│   ├── agenda.html             # Citas y seguimientos
│   ├── alarmas.html            # Notificaciones
│   ├── mi_control.html         # Trabajos propios
│   └── pwa.js                  # Service worker
├── requirements-api.txt        # Dependencias Python
├── empresa.db                  # Base de datos SQLite
└── render.yaml                 # Config deploy Render

EmpresaPython/
├── menu_principal.py           # Ventana principal PyQt6
├── form_contabilidad.py        # Panel de control (Centro Control)
├── form_faenas.py              # Gestión de faenas
├── form_presupuestos.py        # Gestión de presupuestos
├── form_ayudantes.py           # Gestión de personal
├── sincronizacion_app.py       # Lógica de sync bidireccional
├── autenticacion.py            # Misma que alucarpin.app
├── base_datos.py               # Misma que alucarpin.app
├── .venv/                      # Virtual environment Python
├── requirements-api.txt        # Dependencias
├── empresa.db                  # Base de datos SQLite
└── AlucarpinSamitier.spec      # Config PyInstaller
```

---

## 🚀 Próximos Pasos (Opcional)

1. **Caché mejorado:** Implementar SQLite Write-Ahead Logging (WAL)
2. **Validaciones:** Añadir más controles de integridad de datos
3. **Reportes:** Dashboard con gráficos en web
4. **Móvil:** App nativa con React Native o Flutter
5. **Backup automático:** Script de respaldo diario a S3

---

## 📞 Soporte

**Última actualización:** 2026-09-11  
**Versión:** 1.0.0 (Sincronización Bidireccional Completa)  
**Estado:** ✅ Producción

Para reportar problemas o sugerencias, contactar al equipo de desarrollo.
