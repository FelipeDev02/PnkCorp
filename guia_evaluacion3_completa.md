# Guía Evaluación 3 – Arquitectura AWS Completa
### Proyecto: pp2multicloud (Astro + Django + PostgreSQL)

---

## Resumen de la arquitectura

| Componente | Detalle |
|---|---|
| Frontend | Astro (estático) → Nginx → puerto 4321 |
| Backend | Django 6 + Gunicorn → puerto 8000 |
| Base de datos | RDS PostgreSQL (puerto 5432) |
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
El archivo `backend/requirements.txt` ya fue generado con las versiones exactas del venv:
```
django==6.0.3
djangorestframework==3.17.1
django-cors-headers==4.9.0
Pillow==12.2.0
psycopg2-binary==2.9.11
asgiref==3.11.1
sqlparse==0.5.5
gunicorn==21.2.0
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

## FASE 2 – EC2 base (para crear la AMI)

### 2.1 Security Group de la instancia
- VPC → Security Groups → **Create security group**
- Name: `SG-EC2-app`
- VPC: `vpc-evaluacion3`
- Inbound rules:

| Tipo | Puerto | Origen |
|---|---|---|
| SSH | 22 | My IP |
| Custom TCP | 4321 | 0.0.0.0/0 |
| Custom TCP | 8000 | 0.0.0.0/0 |

### 2.2 Lanzar la instancia base
- EC2 → Instances → **Launch instance**
- Name: `ec2-base-evaluacion3`
- AMI: **Ubuntu Server 24.04 LTS (HVM)**
- Instance type: `t2.micro`
- Key pair: existente o crear uno nuevo
- Network: `vpc-evaluacion3`
- Subnet: `subnet-pub-1a` (pública)
- Auto-assign public IP: **Enable**
- Security group: `SG-EC2-app`

### 2.3 User Data
En **Advanced details → User data**, pega el contenido completo de `user_data_ubuntu_node_django.sh` editando las dos variables:

```bash
REPO_URL="https://github.com/TU_USUARIO/pp2multicloud.git"
DB_HOST="TU_ENDPOINT_RDS.rds.amazonaws.com"   # lo tendrás en Fase 5
```

> El script usará `migrate --noinput || true` así que no fallará si el RDS aún no existe.

→ **Launch instance**

### 2.4 Verificar el despliegue
Espera 3-5 minutos y conéctate por SSH:
```bash
ssh -i tu-key.pem ubuntu@IP_PUBLICA_EC2
cat /var/log/user_data.log
# Busca la línea: "Despliegue completado." al final
```

Prueba en el navegador:
- `http://IP_PUBLICA:4321` → web de Astro (sirviendo dist/ via Nginx)
- `http://IP_PUBLICA:8000/api/` → respuesta JSON de Django

### 2.5 Crear la AMI
1. EC2 → Instances → selecciona `ec2-base-evaluacion3`
2. Actions → **Image and templates → Create image**
3. Image name: `ami-pp2multicloud`
4. Deja activado el reboot (garantiza consistencia)
5. → **Create image**
6. Ve a **AMIs** y espera estado **Available** (~5-10 min)

### 2.6 Terminar la instancia base
Una vez creada la AMI:
- EC2 → Instances → selecciona la instancia → Instance state → **Terminate instance**

---

## FASE 3 – Application Load Balancer (ALB)

### 3.1 Security Group del ALB
- Name: `SG-ALB`
- VPC: `vpc-evaluacion3`
- Inbound rules:

| Puerto | Origen |
|---|---|
| 4321 | 0.0.0.0/0 |
| 8000 | 0.0.0.0/0 |

### 3.2 Crear los Target Groups

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

### 3.3 Crear el ALB
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

Guarda el **DNS name** del ALB (lo necesitas para CORS en Django).

---

## FASE 4 – Auto Scaling Group

### 4.1 Actualizar SG-EC2-app
Restringe el acceso a los puertos 4321 y 8000 para que solo vengan del ALB:
- Edita las reglas de inbound de puertos 4321 y 8000
- Cambia origen `0.0.0.0/0` → `SG-ALB`

### 4.2 Launch Template
- EC2 → Launch Templates → **Create launch template**
- Name: `LT-pp2multicloud`
- AMI: `ami-pp2multicloud`
- Instance type: `t2.micro`
- Key pair: el mismo que antes
- Security groups: `SG-EC2-app`
- **Advanced details → User data**: mismo script `user_data_ubuntu_node_django.sh` con los valores reales de REPO_URL y DB_HOST

→ **Create launch template**

### 4.3 Auto Scaling Group
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

## FASE 5 – RDS PostgreSQL

### 5.1 Security Group para RDS
- Name: `SG-RDS`
- VPC: `vpc-evaluacion3`
- Inbound: PostgreSQL (5432) → origen: `SG-EC2-app`

### 5.2 Subnet Group
- RDS → Subnet groups → **Create DB subnet group**
- Name: `rds-subnet-group`
- VPC: `vpc-evaluacion3`
- Subnets: **subnet-priv-1a** y **subnet-priv-1b**

### 5.3 Crear la instancia RDS
- RDS → Databases → **Create database**
- Engine: **PostgreSQL**
- Template: Free tier
- DB instance identifier: `rds-evaluacion3`
- Master username: `pnk`
- Master password: `Admin01`
- DB instance class: `db.t3.micro`
- Storage: 20 GiB gp2
- Multi-AZ: **No**
- VPC: `vpc-evaluacion3`
- Subnet group: `rds-subnet-group`
- Public access: **No**
- Security group: `SG-RDS`
- Initial database name: `pnk_db`
- → **Create database**

Copia el **Endpoint** cuando el estado sea Available.

### 5.4 Actualizar Launch Template con el endpoint real
1. EC2 → Launch Templates → `LT-pp2multicloud` → Actions → **Modify template (Create new version)**
2. En User data cambia `DB_HOST` al endpoint real del RDS
3. En el Auto Scaling Group, establece la nueva versión como **Default version**

### 5.5 Actualizar instancias ya en ejecución
```bash
ssh -i tu-key.pem ubuntu@IP_INSTANCIA

# Actualizar el host de la DB en settings.py
sudo sed -i "s/'HOST': '127.0.0.1'/'HOST': 'rds-evaluacion3.xxxx.us-east-1.rds.amazonaws.com'/" \
    /home/ubuntu/app/backend/core/settings.py

# Ejecutar migraciones
cd /home/ubuntu/app/backend
sudo -u ubuntu .venv/bin/python manage.py migrate

# Reiniciar Django
sudo systemctl restart django
```

---

## FASE 6 – Bucket S3 para backups

- S3 → Buckets → **Create bucket**
- Bucket name: `repo-eva3-4`
- Region: us-east-1 (la misma que el resto)
- Block all public access: ✅
- → **Create bucket**

La carpeta `backups/` se creará automáticamente cuando Lambda suba el primer archivo.

---

## FASE 7 – Lambda para backup de PostgreSQL

### 7.1 Crear el rol IAM
- IAM → Roles → **Create role**
- Trusted entity: AWS service → Lambda
- Policies:
  - `AmazonS3FullAccess`
  - `AWSLambdaVPCAccessExecutionRole`
  - `CloudWatchLogsFullAccess`
- Role name: `rol-lambda-backup-rds`

### 7.2 Crear la función Lambda
- Lambda → Functions → **Create function**
- Author from scratch
- Function name: `backup-bd-diario`
- Runtime: **Python 3.12**
- Execution role: `rol-lambda-backup-rds`
- → **Create function**

### 7.3 Pegar el código
Reemplaza el contenido de `lambda_function.py` con el código de `lambda_backup_rds.py` → **Deploy**

### 7.4 Variables de entorno
Configuration → Environment variables → Edit → Agrega:

| Key | Value |
|---|---|
| DB_HOST | `rds-evaluacion3.xxxx.us-east-1.rds.amazonaws.com` |
| DB_PORT | `5432` |
| DB_NAME | `pnk_db` |
| DB_USER | `pnk` |
| DB_PASSWORD | `Admin01` |
| S3_BUCKET | `repo-eva3-4` |

### 7.5 Configurar VPC
Configuration → VPC → Edit:
- VPC: `vpc-evaluacion3`
- Subnets: `subnet-priv-1a` y `subnet-priv-1b`
- Security groups: `SG-EC2-app` (tiene salida al RDS)

### 7.6 Timeout y memoria
Configuration → General configuration → Edit:
- Timeout: **5 min 0 seg**
- Memory: **512 MB**

### 7.7 ⚠️ Nota sobre pg_dump en Lambda
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

### 7.8 Probar la función
- Test → Configure test event → Event JSON: `{}`
- → **Test**
- Verifica en S3 → `repo-eva3-4` → carpeta `backups/` → archivo `Respaldo_BD_DD_MM_YYYY.sql`

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

## FASE 9 – Actualizar CORS de Django (post-ALB)

Con el DNS del ALB en mano, actualiza `settings.py` en cada instancia:

```bash
# Reemplaza con tu DNS real del ALB
ALB_DNS="ALB-evaluacion3-xxxxx.us-east-1.elb.amazonaws.com"

sudo sed -i "s|CORS_ALLOWED_ORIGINS = \[|CORS_ALLOWED_ORIGINS = [\n    'http://$ALB_DNS',|" \
    /home/ubuntu/app/backend/core/settings.py

sudo systemctl restart django
```

O simplemente añade `CORS_ALLOW_ALL_ORIGINS = True` en settings.py para el lab (ya lo hace el User Data script automáticamente).

---

## Verificación final

| Check | Cómo comprobar |
|---|---|
| Astro accesible | `http://ALB_DNS:4321` → muestra la web |
| Django API accesible | `http://ALB_DNS:8000/api/` → respuesta JSON |
| ASG con 2 instancias | EC2 → ASG → ver instancias en running |
| Health checks verdes | EC2 → Target Groups → Targets → "healthy" |
| RDS conectado | `manage.py migrate` sin errores |
| Lambda ejecutada | CloudWatch → `/aws/lambda/backup-bd-diario` → logs OK |
| Archivo en S3 | S3 → `repo-eva3-4` → `backups/` → archivo SQL presente |
| EventBridge activa | EventBridge → Rules → `backup-diario-2359` → Enabled |

---

## Comandos de diagnóstico en EC2

```bash
# Logs del User Data (todo el proceso de instalación)
cat /var/log/user_data.log

# Estado de servicios
sudo systemctl status django
sudo systemctl status nginx

# Reiniciar
sudo systemctl restart django
sudo systemctl restart nginx

# Logs en tiempo real
sudo journalctl -u django -f

# Probar localmente en la instancia
curl http://localhost:4321/
curl http://localhost:8000/api/
```

---

## Estructura del proyecto (referencia)

```
pp2multicloud/
├── astro.config.mjs          # Astro modo estático (sin output: 'server')
├── package.json              # Node >=22.12.0, Astro ^6.1.1
├── src/pages/                # Páginas de Astro
├── public/                   # Assets estáticos
├── dist/                     # Build output (generado por npm run build)
└── backend/
    ├── manage.py
    ├── requirements.txt      # ← generado: django, drf, cors, pillow, psycopg2-binary, gunicorn
    ├── core/
    │   ├── settings.py       # DB: PostgreSQL pnk_db, puerto 5432
    │   ├── wsgi.py           # core.wsgi.application
    │   └── urls.py           # /admin/  /api/
    └── api/
        ├── models.py         # CarouselItem (title, description, image, order)
        ├── views.py
        ├── serializers.py
        └── urls.py
```



ALB-evaluacion3-1664710038.us-east-1.elb.amazonaws.com