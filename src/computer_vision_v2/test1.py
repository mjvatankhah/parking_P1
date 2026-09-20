import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="parking_db",
    user="postgres",
    password="123456"
)

cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM gate;")
result = cursor.fetchone()
print("تعداد ردیف‌های جدول gate:", result[0])

cursor.close()
conn.close()