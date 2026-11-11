"""Database connections inherit the administrator's timezone setting."""
import unittest
from unittest.mock import patch

from computer_vision_v2.database.connection import get_connection


class DatabaseTimezoneTests(unittest.TestCase):
    def test_connections_inherit_database_timezone(self):
        with patch('computer_vision_v2.database.connection.psycopg.connect') as connect:
            connection = get_connection(connect_timeout=3)
        self.assertIs(connection, connect.return_value)
        self.assertNotIn('options', connect.call_args.kwargs)
        self.assertEqual(connect.call_args.kwargs['connect_timeout'], 3)
