import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from reno.services.auth_service import AuthService, hash_password, verify_password


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.service = AuthService()
        self.connection = patch('reno.services.auth_service.get_connection')
        self.connect = self.connection.start()
        self.addCleanup(self.connection.stop)
        self.cursor = self.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value

    def test_password_hash_is_salted_and_preserves_spaces(self):
        encoded = hash_password(' secret ')
        self.assertNotEqual(encoded, hash_password(' secret '))
        self.assertTrue(verify_password(' secret ', encoded))
        self.assertFalse(verify_password('secret', encoded))

    def test_admin_and_logout(self):
        self.assertEqual(self.service.login('admin', '1234').role, 'admin')
        self.connect.assert_not_called()
        self.service.logout()
        self.assertFalse(self.service.is_admin)

    def test_registration_permission_and_validation(self):
        self.assertFalse(self.service.create_guard('g', 'p', 'p').success)
        self.service.login('admin', '1234')
        for args in [('g', 'p', 'q'), ('', 'p', 'p'), ('admin', 'p', 'p')]:
            self.assertFalse(self.service.create_guard(*args).success)
        self.connect.assert_not_called()

    def test_registration_hashes_password_and_duplicate_does_not_overwrite(self):
        self.service.login('admin', '1234')
        self.cursor.fetchone.return_value = ('g',)
        self.assertTrue(self.service.create_guard('g', 'p', 'p').success)
        query, params = self.cursor.execute.call_args.args
        self.assertIn('DO NOTHING', query)
        self.assertTrue(verify_password('p', params[1]))
        self.cursor.fetchone.return_value = None
        self.assertFalse(self.service.create_guard('g', 'p', 'p').success)

    def test_guard_login_and_failed_login_clear_admin(self):
        self.service.login('admin', '1234')
        self.cursor.fetchone.return_value = (hash_password('pass'), 'guard')
        self.assertEqual(self.service.login('g', 'pass').role, 'guard')
        self.assertFalse(self.service.is_admin)
        self.assertFalse(self.service.create_guard('other', 'p', 'p').success)
        self.assertFalse(self.service.login('g', 'wrong').success)
        self.assertEqual(self.service.current_role, '')

    def test_database_failure(self):
        self.connect.side_effect = OSError('offline')
        self.assertFalse(self.service.login('g', 'p').success)
        self.service.login('admin', '1234')
        self.assertFalse(self.service.create_guard('g', 'p', 'p').success)

    def test_list_guards_admin_only_and_no_password_exposed(self):
        self.assertFalse(self.service.list_guards().success)
        self.connect.assert_not_called()
        self.service.login('admin', '1234')
        created = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.cursor.fetchall.return_value = [('guard1', created), ('guard2', None)]
        result = self.service.list_guards()
        self.assertTrue(result.success)
        self.assertEqual(result.usernames, ('guard1', 'guard2'))
        self.assertEqual(result.guards[0].created_at, created)
        self.assertIsNone(result.guards[1].created_at)
        query = self.cursor.execute.call_args.args[0]
        self.assertNotIn('password_hash', query)
        self.assertIn("role = 'guard'", query)

    def test_delete_is_admin_only_and_only_deletes_guard(self):
        self.assertFalse(self.service.delete_guard('g').success)
        self.connect.assert_not_called()
        self.service.login('admin', '1234')
        self.assertFalse(self.service.delete_guard('admin').success)
        self.connect.assert_not_called()
        self.cursor.fetchone.return_value = ('g',)
        self.assertTrue(self.service.delete_guard('g').success)
        query, params = self.cursor.execute.call_args.args
        self.assertIn("role = 'guard'", query)
        self.assertEqual(params, ('g',))
        self.cursor.fetchone.return_value = None
        self.assertFalse(self.service.delete_guard('g').success)

    def test_list_and_delete_database_errors(self):
        self.service.login('admin', '1234')
        self.connect.side_effect = OSError('offline')
        self.assertFalse(self.service.list_guards().success)
        self.assertFalse(self.service.delete_guard('g').success)

    def test_non_english_username_rejected_before_database_access(self):
        for name in ('نگهبان', 'guard۱۲', 'guard name', 'guard\u200c1'):
            self.assertFalse(self.service.login(name, 'pass').success)
            self.service.login('admin', '1234')
            self.assertFalse(self.service.create_guard(name, 'pass', 'pass').success)
        self.connect.assert_not_called()
