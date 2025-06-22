# database_operations.py

import psycopg2
from datetime import datetime
import logging
from config import DATABASE_CONFIG

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("disk_cataloger.log"),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connections and operations."""
    def __init__(self):
        self.dbname = DATABASE_CONFIG["dbname"]
        self.user = DATABASE_CONFIG["user"]
        self.password = DATABASE_CONFIG["password"]
        self.host = DATABASE_CONFIG["host"]
        self.port = DATABASE_CONFIG["port"]

    def connect_db(self):
        """Establishes a connection to the PostgreSQL database."""
        try:
            conn = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            logger.info("Successfully connected to the database.")
            return conn
        except psycopg2.Error as e:
            logger.error(f"Error connecting to database: {e}")
            return None

    def create_tables(self):
        """Creates necessary tables if they don't exist."""
        conn = self.connect_db()
        if not conn:
            logger.error("Failed to connect to database to create tables.")
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        filepath TEXT NOT NULL,
                        filesize BIGINT NOT NULL,
                        last_modified TIMESTAMP WITH TIME ZONE NOT NULL,
                        disk_name VARCHAR(255) NOT NULL
                    );
                """)
                conn.commit()
                logger.info("Database tables checked/created successfully.")
                return True
        except psycopg2.Error as e:
            logger.error(f"Error creating tables: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def delete_disk_records(self, conn, disk_name):
        """
        Deletes all the existing disk records for a given disk name.
        :param conn: Database connection object.
        :param disk_name: Name of the disk whose records are to be deleted.
        """
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM files WHERE disk_name = %s", (disk_name,))
            logger.info(f"Deleted existing records for disk: '{disk_name}'.")
        except psycopg2.Error as e:
            logger.error(f"Error deleting records for disk {disk_name}: {e}")
            raise

    def bulk_insert_from_csv(self, conn, csv_filepath):
        """
        Performs a bulk insert of file records from a CSV file.
        Note: This method assumes the CSV file is tab-separated and matches the table schema.
        :param conn: Database connection object.
        :param csv_filepath: Path to the CSV file.
        """
        try:
            with conn.cursor() as cur:
                with open(csv_filepath, 'r') as f:
                    cur.copy_from(f, 'files', sep='\t',
                                  columns=('filename', 'filepath', 'filesize', 'last_modified', 'disk_name'))
                conn.commit()
                logger.info(f"Bulk inserted data from {csv_filepath}.")
        except psycopg2.Error as e:
            logger.error(f"Error during bulk copy from {csv_filepath}: {e}")
            conn.rollback()
            raise # Re-raise to allow calling function to handle
        except FileNotFoundError:
            logger.error(f"CSV file not found: {csv_filepath}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during bulk insert: {e}")
            conn.rollback()
            raise

    def insert_file_records_batch(self, conn, records):
        """
        Inserts multiple file records into the 'files' table in a single batch.
        :param conn: Database connection object.
        :param records: A list of dictionaries, each representing a file record.
        """
        if not records:
            return
        try:
            with conn.cursor() as cur:
                data_to_insert = [(r['filename'], r['filepath'], r['filesize'], r['last_modified'], r['disk_name']) for
                                  r in records]
                cur.executemany(
                    "INSERT INTO files (filename, filepath, filesize, last_modified, disk_name) VALUES (%s, %s, %s, %s, %s)",
                    data_to_insert
                )
            logger.debug(f"Inserted batch of {len(records)} records.")
        except psycopg2.Error as e:
            logger.error(f"Error inserting batch records: {e}")
            raise  # Re-raise to allow rollback in the calling thread

    def insert_file_record(self, conn, filename, filepath, filesize, last_modified, disk_name):
        """
        Inserts a single file record into the 'files' table.
        Note: This method is generally less efficient than batch insertion for many records.
        :param conn: Database connection object.
        :param filename: Name of the file.
        :param filepath: Full path of the file.
        :param filesize: Size of the file in bytes.
        :param last_modified: Last modified timestamp of the file.
        :param disk_name: Name of the disk the file belongs to.
        """
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO files (filename, filepath, filesize, last_modified, disk_name) VALUES (%s, %s, %s, %s, %s)",
                    (filename, filepath, filesize, last_modified, disk_name)
                )
            logger.debug(f"Inserted single record: {filename}")
        except psycopg2.Error as e:
            logger.error(f"Error inserting record {filename}: {e}")
            raise

    def search_files(self, search_term, disk_name=None):
        """
        Searches for files in the database based on a search term and optional disk name.
        Returns a list of dictionaries, each representing a file.
        :param search_term: The term to search for in filenames (case-insensitive).
        :param disk_name: Optional. The name of the disk to narrow the search.
        :return: A list of dictionaries, each representing a file.
        """
        results = []
        conn = self.connect_db()
        if not conn:
            logger.error("Failed to connect to database for search operation.")
            return results
        try:
            with conn.cursor() as cur:
                query = "SELECT filename, filepath, filesize, last_modified, disk_name FROM files WHERE filename ILIKE %s"
                params = [f"%{search_term}%"]

                if disk_name:
                    query += " AND disk_name = %s"
                    params.append(disk_name)

                cur.execute(query, params)
                for row in cur.fetchall():
                    results.append({
                        "filename": row[0],
                        "filepath": row[1],
                        "filesize": row[2],
                        "last_modified": row[3],
                        "disk_name": row[4]
                    })
            logger.info(f"Search for '{search_term}' (disk: {disk_name if disk_name else 'All'}) returned {len(results)} results.")
        except psycopg2.Error as e:
            logger.error(f"Error searching database for '{search_term}': {e}")
        finally:
            if conn:
                conn.close()
        return results