from computer_vision_v2.database.connection import get_connection
from computer_vision_v2.database.queries import INSERT_VEHICLE

def add_v():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(INSERT_VEHICLE,('13m1245','car'))
    conn.commit()
    cur.execute(
        "SELECT plate_number, vehicle_type FROM vehicle WHERE plate_number = %s;",
        ("12m1245",))
    r = cur.fetchone()
    print("plate ", r)
    cur.close()
    conn.close()

add_v()