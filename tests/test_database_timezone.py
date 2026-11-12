"""Database connections use the parking site timezone."""
import unittest
from unittest.mock import patch

from computer_vision_v2.database.connection import get_connection


class DatabaseTimezoneTests(unittest.TestCase):
    def test_connections_use_tehran_timezone(self):
        with patch('computer_vision_v2.database.connection.psycopg.connect') as connect:
            connection = get_connection(connect_timeout=3)
        self.assertIs(connection, connect.return_value)
        self.assertEqual(connect.call_args.kwargs['options'], '-c timezone=Asia/Tehran')
        self.assertEqual(connect.call_args.kwargs['connect_timeout'], 3)
