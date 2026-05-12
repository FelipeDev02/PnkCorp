#!/bin/bash
set -e
exec > /var/log/user-data.log 2>&1

# =============================================================
# VARIABLES - MODIFICAR ANTES DE USAR
# =============================================================
GITHUB_REPO="https://github.com/TU_USUARIO/pp2multicloud.git"
APP_DIR="/home/ubuntu/pp2multicloud"
S3_BUCKET="pero-eva3-4-final"
DB_HOST="rds-evaluacion3.cyzhg9dznddy.us-east-1.rds.amazonaws.com"
DB_NAME="pnk_db"
DB_USER="pnk"
DB_PASSWORD="Admin01."
SUPERUSER_USER="admin"
SUPERUSER_PASS="Admin01."
SUPERUSER_EMAIL="admin@example.com"
# =============================================================

echo ">>> Actualizando sistema..."
apt-get update -y
apt-get install -y git python3 python3-pip python3-venv nginx

echo ">>> Instalando Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

echo ">>> Clonando repositorio..."
git clone "$GITHUB_REPO" "$APP_DIR"
chown -R ubuntu:ubuntu "$APP_DIR"

# ---------------------------------------------------------------
# BACKEND (Django + Gunicorn)
# ---------------------------------------------------------------
echo ">>> Configurando backend..."
cd "$APP_DIR/backend"
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# Variables de entorno para Django producción
export DJANGO_SETTINGS_MODULE=core.settings_prod
export S3_BUCKET="$S3_BUCKET"
export DB_HOST="$DB_HOST"
export DB_NAME="$DB_NAME"
export DB_USER="$DB_USER"
export DB_PASSWORD="$DB_PASSWORD"

echo ">>> Migraciones..."
python manage.py migrate --noinput

echo ">>> Archivos estáticos..."
python manage.py collectstatic --noinput

echo ">>> Creando superusuario..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$SUPERUSER_USER').exists():
    User.objects.create_superuser('$SUPERUSER_USER', '$SUPERUSER_EMAIL', '$SUPERUSER_PASS')
    print('Superusuario creado: $SUPERUSER_USER / $SUPERUSER_PASS')
else:
    print('Superusuario ya existe')
"

deactivate

# ---------------------------------------------------------------
# FRONTEND (Astro → dist estático)
# ---------------------------------------------------------------
echo ">>> Construyendo frontend Astro..."
cd "$APP_DIR"
npm install
npm run build

# ---------------------------------------------------------------
# NGINX — sirve Astro en :4321, proxea /api/ a Django :8000
# ---------------------------------------------------------------
echo ">>> Configurando Nginx..."
cat > /etc/nginx/sites-available/astro << 'NGINX_CONF'
server {
    listen 4321;
    server_name _;
    root /home/ubuntu/pp2multicloud/dist;
    index index.html;

    # Archivos estáticos del build de Astro
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy de la API hacia Gunicorn (Django)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
NGINX_CONF

ln -sf /etc/nginx/sites-available/astro /etc/nginx/sites-enabled/astro
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

# ---------------------------------------------------------------
# GUNICORN — servicio systemd para Django :8000
# ---------------------------------------------------------------
echo ">>> Configurando Gunicorn como servicio..."
cat > /etc/systemd/system/gunicorn.service << GUNICORN_UNIT
[Unit]
Description=Gunicorn – Django pp2multicloud
After=network.target

[Service]
User=ubuntu
WorkingDirectory=$APP_DIR/backend
Environment="DJANGO_SETTINGS_MODULE=core.settings_prod"
Environment="S3_BUCKET=$S3_BUCKET"
Environment="DB_HOST=$DB_HOST"
Environment="DB_NAME=$DB_NAME"
Environment="DB_USER=$DB_USER"
Environment="DB_PASSWORD=$DB_PASSWORD"
ExecStart=$APP_DIR/backend/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 core.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
GUNICORN_UNIT

systemctl daemon-reload
systemctl enable gunicorn
systemctl start gunicorn

echo ">>> Deploy completo."
echo "    Frontend → http://IP:4321"
echo "    Backend  → http://IP:8000"
echo "    Admin    → http://IP:8000/admin   ($SUPERUSER_USER / $SUPERUSER_PASS)"
