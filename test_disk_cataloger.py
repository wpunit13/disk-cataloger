# test_disk_cataloger.py

import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
from datetime import datetime, timezone

# Import the classes we want to test
from database_operations import DatabaseManager, logger as db_logger
from gui_scan_and_insert_file import DiskScannerThread  # We'll test this later


# Mock the DATABASE_CONFIG to ensure tests are isolated
# This is important because DatabaseManager directly imports it.
# We'll use patch.dict for this.

class TestDatabaseManager(unittest.TestCase):

    @patch('database_operations.psycopg2.connect')
    def setUp(self, mock_connect):
        # This setUp will run before each test method
        self.db_manager = DatabaseManager()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        mock_connect.return_value = self.mock_conn

        # Suppress logging output during tests for cleaner console
        # You might want to configure a separate test logger if you need to assert logs
        self.original_log_level = db_logger.level
        db_logger.setLevel(100)  # Set to a level higher than CRITICAL to suppress all output

    def tearDown(self):
        # Restore original logging level after each test
        db_logger.setLevel(self.original_log_level)

    def test_connect_db_success(self):
        conn = self.db_manager.connect_db()
        self.assertIsNotNone(conn)
        self.assertEqual(conn, self.mock_conn)
        self.mock_conn.close.assert_not_called()  # Connection should not be closed by connect_db

    @patch('database_operations.psycopg2.connect', side_effect=Exception("Connection error"))
    def test_connect_db_failure(self, mock_connect):
        conn = self.db_manager.connect_db()
        self.assertIsNone(conn)

    @patch('database_operations.DatabaseManager.connect_db')
    def test_create_tables_success(self, mock_connect_db):
        mock_connect_db.return_value = self.mock_conn
        result = self.db_manager.create_tables()
        self.assertTrue(result)
        self.mock_cursor.execute.assert_called_once()
        self.mock_conn.commit.assert_called_once()
        self.mock_conn.close.assert_called_once()

    @patch('database_operations.DatabaseManager.connect_db', return_value=None)
    def test_create_tables_no_connection(self, mock_connect_db):
        result = self.db_manager.create_tables()
        self.assertFalse(result)
        self.mock_cursor.execute.assert_not_called()
        self.mock_conn.commit.assert_not_called()
        self.mock_conn.close.assert_not_called()

    @patch('database_operations.psycopg2.connect')
    def test_delete_disk_records(self, mock_connect):
        # We need a connection for this method, so mock it directly or via setUp
        mock_connect.return_value = self.mock_conn
        self.db_manager.delete_disk_records(self.mock_conn, "TestDisk")
        self.mock_cursor.execute.assert_called_once_with("DELETE FROM files WHERE disk_name = %s", ("TestDisk",))

    @patch('database_operations.psycopg2.connect')
    def test_delete_disk_records_error(self, mock_connect):
        mock_connect.return_value = self.mock_conn
        self.mock_cursor.execute.side_effect = Exception("DB Error")
        with self.assertRaises(Exception):  # Expect the exception to be re-raised
            self.db_manager.delete_disk_records(self.mock_conn, "TestDisk")
        self.mock_cursor.execute.assert_called_once()

    @patch('builtins.open', new_callable=mock_open)
    @patch('database_operations.psycopg2.connect')
    def test_bulk_insert_from_csv_success(self, mock_connect, mock_file_open):
        mock_connect.return_value = self.mock_conn
        # Simulate CSV file content
        mock_file_open.return_value.read.return_value = "file1\t/path/to/file1\t100\t2023-01-01 10:00:00+00\tDiskA\n"

        self.db_manager.bulk_insert_from_csv(self.mock_conn, "dummy.csv")
        self.mock_cursor.copy_from.assert_called_once_with(
            mock_file_open(), 'files', sep='\t',
            columns=('filename', 'filepath', 'filesize', 'last_modified', 'disk_name')
        )
        self.mock_conn.commit.assert_called_once()
        self.mock_conn.rollback.assert_not_called()

    @patch('builtins.open', new_callable=mock_open)
    @patch('database_operations.psycopg2.connect')
    def test_bulk_insert_from_csv_db_error(self, mock_connect, mock_file_open):
        mock_connect.return_value = self.mock_conn
        self.mock_cursor.copy_from.side_effect = Exception("Bulk copy error")

        with self.assertRaises(Exception):
            self.db_manager.bulk_insert_from_csv(self.mock_conn, "dummy.csv")

        self.mock_conn.rollback.assert_called_once()
        self.mock_conn.commit.assert_not_called()

    @patch('database_operations.psycopg2.connect')
    def test_insert_file_records_batch_success(self, mock_connect):
        mock_connect.return_value = self.mock_conn
        records = [
            {"filename": "f1", "filepath": "/p1", "filesize": 10, "last_modified": datetime.now(timezone.utc),
             "disk_name": "D1"},
            {"filename": "f2", "filepath": "/p2", "filesize": 20, "last_modified": datetime.now(timezone.utc),
             "disk_name": "D1"}
        ]
        self.db_manager.insert_file_records_batch(self.mock_conn, records)
        self.mock_cursor.executemany.assert_called_once()
        # Check that executemany was called with the correct SQL and data
        args, kwargs = self.mock_cursor.executemany.call_args
        self.assertEqual(args[0],
                         "INSERT INTO files (filename, filepath, filesize, last_modified, disk_name) VALUES (%s, %s, %s, %s, %s)")
        self.assertEqual(len(args[1]), 2)  # Ensure two records were passed

    @patch('database_operations.psycopg2.connect')
    def test_insert_file_records_batch_empty(self, mock_connect):
        mock_connect.return_value = self.mock_conn
        self.db_manager.insert_file_records_batch(self.mock_conn, [])
        self.mock_cursor.executemany.assert_not_called()

    @patch('database_operations.psycopg2.connect')
    def test_insert_file_records_batch_error(self, mock_connect):
        mock_connect.return_value = self.mock_conn
        self.mock_cursor.executemany.side_effect = Exception("Batch insert error")
        records = [
            {"filename": "f1", "filepath": "/p1", "filesize": 10, "last_modified": datetime.now(timezone.utc),
             "disk_name": "D1"}
        ]
        with self.assertRaises(Exception):
            self.db_manager.insert_file_records_batch(self.mock_conn, records)
        self.mock_cursor.executemany.assert_called_once()

    @patch('database_operations.psycopg2.connect')
    def test_insert_file_record_success(self, mock_connect):
        mock_connect.return_value = self.mock_conn
        self.db_manager.insert_file_record(self.mock_conn, "file.txt", "/path/file.txt", 123,
                                           datetime.now(timezone.utc), "MyDisk")
        self.mock_cursor.execute.assert_called_once()
        args, kwargs = self.mock_cursor.execute.call_args
        self.assertEqual(args[0],
                         "INSERT INTO files (filename, filepath, filesize, last_modified, disk_name) VALUES (%s, %s, %s, %s, %s)")
        self.assertEqual(args[1][0], "file.txt")

    @patch('database_operations.psycopg2.connect')
    def test_insert_file_record_error(self, mock_connect):
        mock_connect.return_value = self.mock_conn
        self.mock_cursor.execute.side_effect = Exception("Single insert error")
        with self.assertRaises(Exception):
            self.db_manager.insert_file_record(self.mock_conn, "file.txt", "/path/file.txt", 123,
                                               datetime.now(timezone.utc), "MyDisk")
        self.mock_cursor.execute.assert_called_once()

    @patch('database_operations.DatabaseManager.connect_db')
    def test_search_files_success(self, mock_connect_db):
        mock_connect_db.return_value = self.mock_conn
        # Mock fetchall to return some data
        mock_data = [
            ("report.pdf", "/docs/report.pdf", 500, datetime(2023, 1, 1, tzinfo=timezone.utc), "WorkDisk"),
            (
            "old_report.doc", "/archive/old_report.doc", 300, datetime(2022, 6, 15, tzinfo=timezone.utc), "ArchiveDisk")
        ]
        self.mock_cursor.fetchall.return_value = mock_data

        results = self.db_manager.search_files("report")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["filename"], "report.pdf")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT filename, filepath, filesize, last_modified, disk_name FROM files WHERE filename ILIKE %s",
            ("%report%",))
        self.mock_conn.close.assert_called_once()

    @patch('database_operations.DatabaseManager.connect_db')
    def test_search_files_with_disk_name(self, mock_connect_db):
        mock_connect_db.return_value = self.mock_conn
        mock_data = [
            ("report.pdf", "/docs/report.pdf", 500, datetime(2023, 1, 1, tzinfo=timezone.utc), "WorkDisk")
        ]
        self.mock_cursor.fetchall.return_value = mock_data

        results = self.db_manager.search_files("report", "WorkDisk")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["disk_name"], "WorkDisk")
        self.mock_cursor.execute.assert_called_once_with(
            "SELECT filename, filepath, filesize, last_modified, disk_name FROM files WHERE filename ILIKE %s AND disk_name = %s",
            ("%report%", "WorkDisk"))
        self.mock_conn.close.assert_called_once()

    @patch('database_operations.DatabaseManager.connect_db')
    def test_search_files_no_results(self, mock_connect_db):
        mock_connect_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = []

        results = self.db_manager.search_files("nonexistent")
        self.assertEqual(len(results), 0)
        self.mock_conn.close.assert_called_once()

    @patch('database_operations.DatabaseManager.connect_db', return_value=None)
    def test_search_files_no_connection(self, mock_connect_db):
        results = self.db_manager.search_files("any")
        self.assertEqual(len(results), 0)
        self.mock_cursor.execute.assert_not_called()  # Cursor methods should not be called if no connection

    @patch('database_operations.DatabaseManager.connect_db')
    def test_search_files_db_error(self, mock_connect_db):
        mock_connect_db.return_value = self.mock_conn
        self.mock_cursor.execute.side_effect = Exception("Search DB error")

        results = self.db_manager.search_files("error_term")
        self.assertEqual(len(results), 0)  # Should return empty list on error
        self.mock_conn.close.assert_called_once()

# To run these tests, save the above code as test_disk_cataloger.py
# and run from your terminal in the same directory:
# python -m unittest test_disk_cataloger.py