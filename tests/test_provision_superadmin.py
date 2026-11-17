import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('provision_superadmin', Path(__file__).resolve().parents[1]/'scripts/provision_superadmin.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProvisionOwnerTests(unittest.TestCase):
    def test_provision_hashes_password_and_never_promotes_existing_username(self):
        from plakino_ui.services.auth_service import verify_password
        with patch.object(module, 'get_connection') as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = ('superadmin',)
            module.provision('superadmin', 'a-local-secret-password')
            sql, params = cursor.execute.call_args.args
            self.assertIn('DO NOTHING', sql)
            self.assertIn("'superadmin'", sql)
            self.assertTrue(verify_password('a-local-secret-password', params[1]))
            cursor.fetchone.return_value = None
            with self.assertRaises(ValueError):
                module.provision('superadmin', 'another-local-password')

    def test_reset_cannot_change_admin_or_guard(self):
        with patch.object(module, 'get_connection') as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = None
            with self.assertRaises(ValueError):
                module.provision('guard', 'a-local-secret-password', reset=True)
            self.assertIn("role = 'superadmin'", cursor.execute.call_args.args[0])

    def test_invalid_names_and_short_password_fail_before_database(self):
        with patch.object(module, 'get_connection') as connect:
            for username, password in [('admin', 'long-enough-password'), ('bad name', 'long-enough-password'),
                                       ('superadmin', 'short')]:
                with self.assertRaises(ValueError):
                    module.provision(username, password)
            connect.assert_not_called()
