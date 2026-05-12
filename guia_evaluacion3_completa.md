# Guía Evaluación 3 – Arquitectura AWS Completa
### Proyecto: pp2multicloud (Astro + Django + PostgreSQL)

---

## Resumen de la arquitectura

| Componente | Detalle |
|---|---|
| Frontend | Astro (estático) → Nginx → puerto 4321 |
| Backend | Django 6 + Gunicorn → puerto 8000 |
| Base de datos | RDS PostgreSQL (puerto 5432) |
| Almacenamiento imágenes | S3 bucket `pero-eva3-4-final` → carpeta `media/` |
| Balanceador | ALB con 2 Target Groups |
| Escalado | Auto Scaling Group (min 2, max 4) |
| Backup | Lambda (pg_dump) → S3 vía EventBridge 23:59 |
| Código | GitHub → EC2 via git clone |

---

## FASE 0 – Subir el proyecto a GitHub

Haz esto desde tu máquina local con el backup del proyecto.

### 0.1 Crear el repositorio en GitHub
1. Ve a [github.com](https://github.com) → New repository
2. Nombre: `pp2multicloud` (o el que prefieras)
3. Privado está bien. **No** inicialices con README.
4. Copia la URL: `https://github.com/TU_USUARIO/pp2multicloud.git`

### 0.2 requirements.txt (ya creado)
El archivo `backend/requirements.txt` ya tiene todas las dependencias necesarias:
```
django==6.0.3
djangorestframework==3.17.1
django-cors-headers==4.9.0
Pillow==12.2.0
psycopg2-binary==2.9.11
asgiref==3.11.1
sqlparse==0.5.5
gunicorn==21.2.0
whitenoise==6.9.0
django-storages==1.14.6
boto3==1.38.5
```
Verifica que esté presente en `backend/` antes de hacer el push.

### 0.3 Crear .gitignore
Crea `.gitignore` en la raíz del proyecto:
```
node_modules/
dist/
__pycache__/
*.pyc
.venv/
venv/
*.env
.DS_Store
media/
*.sqlite3
```

### 0.4 Subir a GitHub
Desde la carpeta raíz `pp2multicloud/`:
```bash
git init
git add .
git commit -m "feat: proyecto inicial pp2multicloud"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/pp2multicloud.git
git push -u origin main
```
Si pide credenciales, usa tu usuario y un **Personal Access Token** de GitHub
(Settings → Developer settings → Personal access tokens → Generate new token, scope `repo`).

---

## FASE 1 – Crear la VPC

### 1.1 Ir a VPC → Create VPC
- Servicios → VPC → Your VPCs → **Create VPC**
- Selecciona **VPC and more** (wizard)

### 1.2 Configuración
| Campo | Valor |
|---|---|
| Name tag | `vpc-evaluacion3` |
| IPv4 CIDR | `10.0.0.0/16` |
| Availability Zones | 2 |
| Public subnets | 2 |
| Private subnets | 2 |
| NAT gateways | 1 (en 1 AZ) |
| VPC endpoints | None |

### 1.3 CIDRs de subredes
| Subred | Tipo | AZ | CIDR |
|---|---|---|---|
| subnet-pub-1a | Pública | us-east-1a | 10.0.10.0/24 |
| subnet-pub-1b | Pública | us-east-1b | 10.0.20.0/24 |
| subnet-priv-1a | Privada | us-east-1a | 10.0.100.0/24 |
| subnet-priv-1b | Privada | us-east-1b | 10.0.200.0/24 |

→ **Create VPC** y espera a que todo quede en verde.

---

## FASE 2 – RDS PostgreSQL

> Creamos la base de datos **antes** del EC2 para tener el endpoint disponible cuando configuremos el script de despliegue.

### 2.1 Security Group para RDS
- VPC → Security Groups → **Create security group**
- Name: `SG-RDS`
- VPC: `vpc-evaluacion3`
- Inbound rules:

| Tipo | Puerto | Origen |
|---|---|---|
| PostgreSQL | 5432 | `SG-EC2-app` (se agrega después de crear ese SG en FASE 4) |

> Por ahora puedes dejarlo sin regla inbound y agregarla luego, o poner `0.0.0.0/0` temporalmente para pruebas.

### 2.2 Subnet Group
- RDS → Subnet groups → **Create DB subnet group**
- Name: `rds-subnet-group`
- VPC: `vpc-evaluacion3`
- Subnets: **subnet-priv-1a** y **subnet-priv-1b**

### 2.3 Crear la instancia RDS
- RDS → Databases → **Create database**
- Engine: **PostgreSQL**
- Template: Free tier
- DB instance identifier: `rds-evaluacion3`
- Master username: `pnk`
- Master password: `Admin01.`
- DB instance class: `db.t3.micro`
- Storage: 20 GiB gp2
- Multi-AZ: **No**
- VPC: `vpc-evaluacion3`
- Subnet group: `rds-subnet-group`
- Public access: **No**
- Security group: `SG-RDS`
- Initial database name: `pnk_db`
- → **Create database**

Espera estado **Available** (~10 min) y copia el **Endpoint** — lo necesitas en la siguiente fase.

---

## FASE 3 – Bucket S3

> El bucket S3 debe existir **antes** del EC2. Django necesita escribir imágenes en S3 desde el primer arrange.

### 3.1 Crear el bucket

- S3 → Buckets → **Create bucket**
- Bucket name: `pero-eva3-4-final`
- Region: **us-east-1**
- **Desmarcar** "Block all public access" → marcar el checkbox de confirmación
- → **Create bucket**

> Los nombres de bucket S3 son globalmente únicos. Si `pero-eva3-4-final` ya existe, elige otro nombre y actualiza la variable `S3_BUCKET` en el User Data script (FASE 4).

### 3.2 Bucket Policy (acceso público de lectura para imágenes)
- S3 → `pero-eva3-4-final` → Permissions → **Bucket policy** → Edit
- Pega el contenido del archivo `Configuration/s3_bucket_policy.json`:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadMedia",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::pero-eva3-4-final/media/*"
        }
    ]
}
```

→ **Save changes**

### 3.3 CORS del bucket
- S3 → `pero-eva3-4-final` → Permissions → **Cross-origin resource sharing (CORS)** → Edit
- Pega el contenido del archivo `Configuration/s3_cors.json`:

```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET"],
        "AllowedOrigins": ["*"],
        "ExposeHeaders": []
    }
]
```

→ **Save changes**

### 3.4 Carpeta de backups
La carpeta `backups/` se creará automáticamente cuando Lambda suba el primer archivo. No necesitas crearla manualmente.

---

## FASE 4 – EC2 base (para crear la AMI)

### 4.1 Security Group de la instancia
- VPC → Security Groups → **Create security group**
- Name: `SG-EC2-app`
- VPC: `vpc-evaluacion3`
- Inbound rules:

| Tipo | Puerto | Origen |
|---|---|---|
| SSH | 22 | My IP |
| Custom TCP | 4321 | 0.0.0.0/0 |
| Custom TCP | 8000 | 0.0.0.0/0 |

> Ahora que `SG-EC2-app` existe, vuelve a **SG-RDS** y agrega la regla inbound PostgreSQL 5432 con origen `SG-EC2-app`.

### 4.2 Lanzar la instancia base
- EC2 → Instances → **Launch instance**
- Name: `ec2-base-evaluacion3`
- AMI: **Ubuntu Server 24.04 LTS (HVM)**
- Instance type: `t2.micro`
- Key pair: existente o crear uno nuevo
- Network: `vpc-evaluacion3`
- Subnet: `subnet-pub-1a` (pública)
- Auto-assign public IP: **Enable**
- Security group: `SG-EC2-app`
- **Advanced details → IAM instance profile**: selecciona **LabRole**

### 4.3 User Data
En **Advanced details → User data**, pega el contenido completo de `Configuration/user_data_ec2.sh` y edita las variables al inicio:

```bash
GITHUB_REPO="https://github.com/TU_USUARIO/pp2multicloud.git"   # ← tu repo real
DB_HOST="rds-evaluacion3.XXXX.us-east-1.rds.amazonaws.com"       # ← endpoint de FASE 2
S3_BUCKET="pero-eva3-4-final"                                      # ← nombre del bucket de FASE 3
```

→ **Launch instance**

### 4.4 Verificar el despliegue
Espera 3-5 minutos y conéctate por SSH:
```bash
ssh -i tu-key.pem ubuntu@IP_PUBLICA_EC2
cat /var/log/user-data.log
# Busca la línea: "Deploy completo." al final
```

Prueba en el navegador:
- `http://IP_PUBLICA:4321` → web de Astro (sirviendo dist/ via Nginx)
- `http://IP_PUBLICA:8000/api/` → respuesta JSON de Django
- `http://IP_PUBLICA:8000/admin/` → panel de administración (admin / Admin01.)

### 4.5 Crear la AMI
1. EC2 → Instances → selecciona `ec2-base-evaluacion3`
2. Actions → **Image and templates → Create image**
3. Image name: `ami-pp2multicloud`
4. Deja activado el reboot (garantiza consistencia)
5. → **Create image**
6. Ve a **AMIs** y espera estado **Available** (~5-10 min)

### 4.6 Terminar la instancia base
Una vez creada la AMI:
- EC2 → Instances → selecciona la instancia → Instance state → **Terminate instance**

---

## FASE 5 – Application Load Balancer (ALB)

### 5.1 Security Group del ALB
- Name: `SG-ALB`
- VPC: `vpc-evaluacion3`
- Inbound rules:

| Puerto | Origen |
|---|---|
| 4321 | 0.0.0.0/0 |
| 8000 | 0.0.0.0/0 |

### 5.2 Crear los Target Groups

**TG-Astro-4321:**
- EC2 → Target Groups → **Create target group**
- Target type: Instances
- Name: `TG-Astro-4321`
- Protocol: HTTP | Port: **4321**
- VPC: `vpc-evaluacion3`
- Health check path: `/`
- → Create (sin registrar instancias, lo hará el ASG)

**TG-Django-8000:**
- Name: `TG-Django-8000`
- Protocol: HTTP | Port: **8000**
- VPC: `vpc-evaluacion3`
- Health check path: `/api/`
- → Create

### 5.3 Crear el ALB
- EC2 → Load Balancers → **Create load balancer → Application Load Balancer**
- Name: `ALB-evaluacion3`
- Scheme: **Internet-facing**
- VPC: `vpc-evaluacion3`
- Mappings: selecciona **subnet-pub-1a** y **subnet-pub-1b**
- Security groups: `SG-ALB`

**Listeners:**
| Puerto | Acción |
|---|---|
| 4321 | Forward → TG-Astro-4321 |
| 8000 | Forward → TG-Django-8000 |

→ **Create load balancer**

Guarda el **DNS name** del ALB (lo necesitarás para verificación final).

---

## FASE 6 – Auto Scaling Group

### 6.1 Actualizar SG-EC2-app
Restringe el acceso a los puertos 4321 y 8000 para que solo vengan del ALB:
- Edita las reglas de inbound de puertos 4321 y 8000
- Cambia origen `0.0.0.0/0` → `SG-ALB`

### 6.2 Launch Template
- EC2 → Launch Templates → **Create launch template**
- Name: `LT-pp2multicloud`
- AMI: `ami-pp2multicloud`
- Instance type: `t2.micro`
- Key pair: el mismo que antes
- Security groups: `SG-EC2-app`
- **Advanced details → IAM instance profile**: selecciona **LabRole**
- **Advanced details → User data**: mismo contenido de `Configuration/user_data_ec2.sh` con los valores reales de `GITHUB_REPO`, `DB_HOST` y `S3_BUCKET`

→ **Create launch template**

### 6.3 Auto Scaling Group
- EC2 → Auto Scaling Groups → **Create Auto Scaling group**
- Name: `ASG-evaluacion3`
- Launch template: `LT-pp2multicloud`

**Network:**
- VPC: `vpc-evaluacion3`
- Subnets: **subnet-pub-1a** y **subnet-pub-1b**

**Load balancing:**
- Attach to existing load balancer target groups
- Selecciona: `TG-Astro-4321` y `TG-Django-8000`
- Health checks: activa **ELB health checks**

**Group size:**
| Campo | Valor |
|---|---|
| Desired | 2 |
| Minimum | 2 |
| Maximum | 4 |

**Scaling policy:**
- Target tracking
- Metric: Average CPU utilization
- Target: **50%**

→ **Create Auto Scaling group**

---

## FASE 7 – Lambda para backup de PostgreSQL

### 7.1 Crear la función Lambda
- Lambda → Functions → **Create function**
- Author from scratch
- Function name: `backup-bd-diario`
- Runtime: **Python 3.12**
- Execution role: **Use an existing role** → selecciona **LabRole**
- → **Create function**

### 7.2 Pegar el código
Reemplaza el contenido de `lambda_function.py` con el código de `Configuration/lambda_backup_rds.py` → **Deploy**

### 7.3 Variables de entorno
Configuration → Environment variables → Edit → Agrega:

| Key | Value |
|---|---|
| DB_HOST | `rds-evaluacion3.xxxx.us-east-1.rds.amazonaws.com` |
| DB_PORT | `5432` |
| DB_NAME | `pnk_db` |
| DB_USER | `pnk` |
| DB_PASSWORD | `Admin01.` |
| S3_BUCKET | `pero-eva3-4-final` |

### 7.4 Configurar VPC
Configuration → VPC → Edit:
- VPC: `vpc-evaluacion3`
- Subnets: `subnet-priv-1a` y `subnet-priv-1b`
- Security groups: `SG-EC2-app` (tiene salida al RDS)

### 7.5 Timeout y memoria
Configuration → General configuration → Edit:
- Timeout: **5 min 0 seg**
- Memory: **512 MB**

### 7.6 ⚠️ Nota sobre pg_dump en Lambda
Lambda no incluye el cliente PostgreSQL por defecto. Opciones:

**Opción A (recomendada):** Agregar una Lambda Layer con el binario `pg_dump` para Amazon Linux 2023. Busca en la comunidad layers públicas con "pg_dump lambda layer".

**Opción B (para demostración rápida):** Si el profesor solo quiere ver que la arquitectura funciona y que algo llega a S3, puedes reemplazar el bloque del `pg_dump` por una exportación simple via `psycopg2`:

```python
# Alternativa sin pg_dump — instala psycopg2-binary en la layer
import psycopg2

conn = psycopg2.connect(
    host=db_host, port=db_port, dbname=db_name,
    user=db_user, password=db_password
)
cursor = conn.cursor()
cursor.execute("SELECT * FROM api_carouselitem;")
rows = cursor.fetchall()
with open(tmp_path, 'w') as f:
    f.write(str(rows))
conn.close()
```

### 7.7 Probar la función
- Test → Configure test event → Event JSON: `{}`
- → **Test**
- Verifica en S3 → `pero-eva3-4-final` → carpeta `backups/` → archivo `Respaldo_BD_DD_MM_YYYY.sql`

---

## FASE 8 – EventBridge (disparo diario a las 23:59)

### 8.1 Crear la regla
- EventBridge → Rules → **Create rule**
- Name: `backup-diario-2359`
- Event bus: default
- Rule type: **Schedule**

### 8.2 Cron expression
```
59 23 * * ? *
```
Esta expresión dispara a las 23:59 UTC todos los días.

> Si necesitas 23:59 en tu zona horaria local, ajusta la hora:
> - UTC-3 (Chile verano): usa `59 2 * * ? *` (02:59 UTC = 23:59 Chile)
> - UTC-4 (Chile invierno): usa `59 3 * * ? *`

### 8.3 Target
- Target type: AWS service
- Select target: **Lambda function**
- Function: `backup-bd-diario`
- → **Create rule**

---

## Verificación final

| Check | Cómo comprobar |
|---|---|
| Astro accesible | `http://ALB_DNS:4321` → muestra la web |
| Django API accesible | `http://ALB_DNS:8000/api/` → respuesta JSON |
| Django Admin accesible | `http://ALB_DNS:8000/admin/` → login con `admin / Admin01.` |
| Carrusel con imágenes S3 | Sube imágenes en `/admin/` → aparecen en el dashboard |
| URLs de imágenes apuntan a S3 | Inspect en browser → `src` de `<img>` debe ser `https://pero-eva3-4-final.s3.amazonaws.com/media/...` |
| ASG con 2 instancias | EC2 → ASG → ver instancias en running |
| Health checks verdes | EC2 → Target Groups → Targets → "healthy" |
| RDS conectado | `manage.py migrate` sin errores (ver log del User Data) |
| Lambda ejecutada | CloudWatch → `/aws/lambda/backup-bd-diario` → logs OK |
| Archivo en S3 | S3 → `pero-eva3-4-final` → `backups/` → archivo presente |
| EventBridge activa | EventBridge → Rules → `backup-diario-2359` → Enabled |

---

## Comandos de diagnóstico en EC2

```bash
# Logs del User Data (todo el proceso de instalación)
cat /var/log/user-data.log

# Estado de servicios
sudo systemctl status gunicorn
sudo systemctl status nginx

# Reiniciar
sudo systemctl restart gunicorn
sudo systemctl restart nginx

# Logs en tiempo real
sudo journalctl -u gunicorn -f

# Probar localmente en la instancia
curl http://localhost:4321/
curl http://localhost:8000/api/
curl http://localhost:8000/api/carrusel/
```

---

## Estructura del proyecto (referencia)

```
pp2multicloud/
├── astro.config.mjs          # Astro modo estático
├── package.json              # Node >=22.12.0, Astro ^6.1.1
├── src/pages/                # Páginas de Astro
├── public/                   # Assets estáticos
├── dist/                     # Build output (generado por npm run build)
├── Configuration/
│   ├── user_data_ec2.sh      # Script de despliegue para Launch Template / User Data
│   ├── s3_bucket_policy.json # Bucket policy para acceso público a media/
│   ├── s3_cors.json          # CORS del bucket S3
│   └── lambda_backup_rds.py  # Código de la función Lambda de backup
└── backend/
    ├── manage.py
    ├── requirements.txt      # django, drf, cors, pillow, psycopg2, gunicorn, storages, boto3
    ├── core/
    │   ├── settings.py       # Desarrollo local
    │   ├── settings_prod.py  # Producción: S3 + RDS + DJANGO_SETTINGS_MODULE=core.settings_prod
    │   ├── wsgi.py
    │   └── urls.py           # /admin/  /api/
    └── api/
        ├── models.py         # CarouselItem (title, description, image→S3, order)
        ├── views.py
        ├── serializers.py
        └── urls.py
```
