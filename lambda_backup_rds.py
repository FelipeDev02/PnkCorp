import boto3
import os
import datetime
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Backup PostgreSQL → S3 usando psycopg2 (sin pg_dump).

    Variables de entorno en Lambda:
      DB_HOST      -> endpoint RDS (ej: rds-evaluacion3.xxxx.rds.amazonaws.com)
      DB_PORT      -> 5432
      DB_NAME      -> pnk_db
      DB_USER      -> pnk
      DB_PASSWORD  -> contraseña
      S3_BUCKET    -> pero-eva3-4-final

    Requiere Lambda Layer: psycopg2-binary para Python 3.12
      ARN: arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p312-psycopg2-binary:1
    """
    import psycopg2

    db_host     = os.environ['DB_HOST']
    db_port     = os.environ.get('DB_PORT', '5432')
    db_name     = os.environ['DB_NAME']
    db_user     = os.environ['DB_USER']
    db_password = os.environ['DB_PASSWORD']
    s3_bucket   = os.environ['S3_BUCKET']

    timestamp = datetime.datetime.now().strftime('%d_%m_%Y')
    filename  = f'Respaldo_BD_{timestamp}.sql'
    s3_key    = f'backups/{filename}'

    logger.info(f"Conectando a {db_host}:{db_port}/{db_name}...")

    conn = psycopg2.connect(
        host=db_host,
        port=int(db_port),
        dbname=db_name,
        user=db_user,
        password=db_password,
        connect_timeout=15
    )
    cur = conn.cursor()
    logger.info("Conexión exitosa.")

    lines = []
    lines.append(f"-- Backup de '{db_name}' | {datetime.datetime.now().isoformat()}")
    lines.append(f"-- Host: {db_host}:{db_port}")
    lines.append("-- Generado por Lambda backup-bd-diario (psycopg2)")
    lines.append("")
    lines.append("SET client_encoding = 'UTF8';")
    lines.append("SET standard_conforming_strings = on;")
    lines.append("")

    # Obtener lista de tablas públicas
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    tables = [row[0] for row in cur.fetchall()]
    logger.info(f"Tablas: {tables}")

    for table in tables:
        lines.append(f"\n-- ===== Tabla: {table} =====")

        # Columnas
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='public' AND table_name=%s
               ORDER BY ordinal_position""",
            (table,)
        )
        col_names = [row[0] for row in cur.fetchall()]
        lines.append(f"-- Columnas: {', '.join(col_names)}")

        # Filas
        cur.execute(f'SELECT * FROM "{table}"')
        rows = cur.fetchall()
        lines.append(f"-- {len(rows)} fila(s)")

        for row in rows:
            values = []
            for val in row:
                if val is None:
                    values.append('NULL')
                elif isinstance(val, bool):
                    values.append('TRUE' if val else 'FALSE')
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                else:
                    escaped = str(val).replace("'", "''")
                    values.append(f"'{escaped}'")
            cols_str = ', '.join(f'"{c}"' for c in col_names)
            vals_str = ', '.join(values)
            lines.append(f'INSERT INTO "{table}" ({cols_str}) VALUES ({vals_str});')

    cur.close()
    conn.close()

    sql_content = '\n'.join(lines)
    total_lines = len(lines)
    logger.info(f"Dump generado: {total_lines} líneas.")

    # Subir a S3
    s3 = boto3.client('s3')
    s3.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=sql_content.encode('utf-8'),
        ContentType='text/plain; charset=utf-8'
    )
    logger.info(f"Subido a s3://{s3_bucket}/{s3_key}")

    return {
        'statusCode': 200,
        'body': f'Backup "{filename}" guardado en s3://{s3_bucket}/{s3_key} ({total_lines} líneas)'
    }
