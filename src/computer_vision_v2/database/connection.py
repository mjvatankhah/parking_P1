"""PostgreSQL connection settings for the vision pipeline.

Credentials come from environment variables so they are never committed into
source code. The defaults make local PostgreSQL usable with the usual
postgres database/user, while production can provide all values through its
service configuration.
"""

from __future__ import annotations

import psycopg


DB_HOST = "127.0.0.1"
DB_PORT = 5432
DB_NAME = "parking_db"
DB_USER = "postgres"
DB_PASSWORD = "123456"

# یک شی اتصال برمگیرداند  به عبارتی یک مسیر باز بین برنامه پایتون و پوست گرس
def get_connection(*, connect_timeout=5):
    connection = psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=connect_timeout,
    )

    return connection
