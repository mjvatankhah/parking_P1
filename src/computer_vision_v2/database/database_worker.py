from computer_vision_v2.database.connection import get_connection


def database_worker(db_queue, running_flag):
    connection = get_connection()
    cursor = connection.cursor()

    while True:
        item = db_queue.get()

        if item is None:
            break

        try:
            plate_number = item["plate_text"] or None
            camera_id = item["camera_id"]
            class_id = item["class_id"]
            direction = item["direction"]
            confidence = item["confidence"]
            image_path = item["image_path"]

            if plate_number is not None:
                cursor.execute(
                    """
                    INSERT INTO vehicle (plate_number, vehicle_type)
                    VALUES (%s, %s)
                    ON CONFLICT (plate_number) DO NOTHING;
                    """,
                    (plate_number, "car")
                )

            cursor.execute(
                """
                INSERT INTO event (
                    camera_id,
                    plate_number,
                    event_type,
                    class_id,
                    confidence,
                    image_path
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    camera_id,
                    plate_number,
                    direction,
                    class_id,
                    confidence,
                    image_path,
                )
            )

            event_id = cursor.fetchone()[0]
            
            if plate_number is not None:
                cursor.execute(
                    """
                    SELECT id
                    FROM vehicle_session
                    WHERE plate_number = %s
                    AND status = 'open'
                    ORDER BY opened_at DESC
                    LIMIT 1;
                    """,
                    (plate_number,)
                )
                open_session = cursor.fetchone()
                if direction == "entry":
                    if open_session is None:
                        cursor.execute(
                            """
                            INSERT INTO vehicle_session (
                                plate_number,
                                entry_event_id,
                                status
                            )
                            VALUES (%s, %s, 'open');
                            """,
                            (plate_number, event_id)
                        )
                elif direction == "exit":
                    if open_session is not None:
                        session_id = open_session[0]

                        cursor.execute(
                            """
                            UPDATE vehicle_session
                            SET
                                exit_event_id = %s,
                                status = 'closed',
                                closed_at = NOW()
                            WHERE id = %s;
                            """,
                            (event_id, session_id)
                        )
                    else:
                        print(
                            f"[DATABASE] open session not found "
                            f"for plate={plate_number}"
                        )



            connection.commit()

            print(
                f"[DATABASE] event={event_id} "
                f"camera={camera_id} "
                f"class_id={class_id} "
                f"plate={plate_number} "
                f"direction={direction}"
            )

        except Exception as error:
            connection.rollback()
            print("[DATABASE ERROR]", error)

    cursor.close()
    connection.close()
