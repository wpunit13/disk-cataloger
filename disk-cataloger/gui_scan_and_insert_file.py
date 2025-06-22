import sys
import os
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# Import DatabaseManager from the new file
from database_operations import DatabaseManager, logger # Import logger as well

### Disk Scanning Logic ###

class DiskScannerThread(QThread):
    """
    A QThread to perform disk scanning in the background,
    preventing the GUI from freezing.
    """
    file_scanned = pyqtSignal(str) # Signal to update GUI with scanned file
    scan_finished = pyqtSignal(int) # Signal when scan is complete, sends total files
    scan_error = pyqtSignal(str) # Signal for errors during scan

    def __init__(self, directory_path, disk_name, db_manager, include_extensions=None, exclude_extensions=None):
        super().__init__()
        self.directory_path = directory_path
        self.disk_name = disk_name
        self.db_manager = db_manager
        self.include_extensions = {ext.lower() for ext in include_extensions} if include_extensions else set()
        self.exclude_extensions = {ext.lower() for ext in exclude_extensions} if exclude_extensions else set()
        self._is_running = True # Flag to allow stopping the scan

    def stop(self):
        self._is_running = False

    def run(self):
        conn = self.db_manager.connect_db()
        if not conn:
            self.scan_error.emit("Failed to connect to database.")
            logger.error("DiskScannerThread: Failed to connect to database.")
            return

        try:
            self.db_manager.delete_disk_records(conn, self.disk_name)
            self.file_scanned.emit(f"Deleting existing records for disk: '{self.disk_name}'...")
            conn.commit()  # Commit the deletion immediately
            self.file_scanned.emit(f"Existing records for '{self.disk_name}' deleted. Starting new scan...")
            logger.info(f"Starting scan for disk: '{self.disk_name}' in '{self.directory_path}'")

            file_count = 0
            file_buffer = []
            BATCH_SIZE = 500 # Defined as a constant

            for root, _, files in os.walk(self.directory_path):
                if not self._is_running: # Check stop flag
                    logger.info("Scan stopped by user.")
                    break
                for file in files:
                    if not self._is_running: # Check stop flag
                        logger.info("Scan stopped by user.")
                        break

                    filepath = os.path.join(root, file)
                    file_extension = os.path.splitext(file)[1].lower()

                    # File Filtering Logic
                    if self.exclude_extensions and file_extension in self.exclude_extensions:
                        logger.debug(f"Skipping excluded file: {filepath}")
                        continue
                    if self.include_extensions and file_extension not in self.include_extensions:
                        logger.debug(f"Skipping non-included file: {filepath}")
                        continue

                    try:
                        file_stats = os.stat(filepath)
                        filename = file
                        filesize = file_stats.st_size
                        last_modified = datetime.fromtimestamp(file_stats.st_mtime)

                        file_info = {
                            "filename": filename,
                            "filepath": filepath,
                            "filesize": filesize,
                            "last_modified": last_modified,
                            "disk_name": self.disk_name
                        }
                        file_buffer.append(file_info)
                        file_count += 1
                        self.file_scanned.emit(f"Scanned: {filename}")
                        logger.debug(f"Scanned: {filepath}")

                        if len(file_buffer) >= BATCH_SIZE:
                            self.db_manager.insert_file_records_batch(conn, file_buffer)
                            conn.commit()
                            self.file_scanned.emit(f"Committed {len(file_buffer)} files. Total scanned: {file_count}")
                            logger.info(f"Committed batch of {len(file_buffer)} files. Total scanned: {file_count}")
                            file_buffer = []

                    except OSError as e:
                        self.file_scanned.emit(f"Error accessing file {filepath}: {e}")
                        logger.warning(f"Error accessing file {filepath}: {e}")
                        continue
            if file_buffer and self._is_running: # Commit any remaining files if scan wasn't stopped
                self.db_manager.insert_file_records_batch(conn, file_buffer)
                conn.commit()
                logger.info(f"Committed final batch of {len(file_buffer)} files. Total scanned: {file_count}")

            if self._is_running: # Only emit finished if not stopped by user
                self.scan_finished.emit(file_count)
                logger.info(f"Scan finished for disk '{self.disk_name}'. Total files: {file_count}")
            else:
                self.scan_error.emit("Scan was interrupted by the user.")
                logger.warning(f"Scan for disk '{self.disk_name}' was interrupted by the user.")

        except Exception as e:
            conn.rollback()
            self.scan_error.emit(f"An unexpected error occurred during scan: {e}")
            logger.critical(f"An unexpected error occurred during scan for disk '{self.disk_name}': {e}", exc_info=True)
        finally:
            if conn:
                conn.close()
                logger.info("Database connection closed for scanner thread.")

### PyQt GUI Application ###

class DiskCatalogerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()
        # Ensure tables exist when the app starts
        if not self.db_manager.create_tables():
            QMessageBox.critical(self, "Database Error", "Failed to connect to or create database tables. Please check logs.")
            sys.exit(1) # Exit if database setup fails

        self.init_ui()
        self.scanner_thread = None # To hold the QThread instance

    def init_ui(self):
        self.setWindowTitle('Offline Disk Cataloger')
        self.setGeometry(100, 100, 800, 600)

        main_layout = QVBoxLayout()

        # --- Scan Section ---
        scan_group_layout = QVBoxLayout()
        scan_group_layout.addWidget(QLabel("### Scan Disk"))

        # Directory selection
        dir_layout = QHBoxLayout()
        self.dir_path_input = QLineEdit()
        self.dir_path_input.setPlaceholderText("Select directory to scan...")
        self.dir_path_input.setReadOnly(True)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_directory)
        dir_layout.addWidget(self.dir_path_input)
        dir_layout.addWidget(self.browse_button)
        scan_group_layout.addLayout(dir_layout)

        # Disk Name input
        disk_name_layout = QHBoxLayout()
        disk_name_layout.addWidget(QLabel("Disk Name:"))
        self.disk_name_input = QLineEdit()
        self.disk_name_input.setPlaceholderText("e.g., My External HDD")
        disk_name_layout.addWidget(self.disk_name_input)
        scan_group_layout.addLayout(disk_name_layout)

        # Scan button
        self.scan_button = QPushButton("Start Scan")
        self.scan_button.clicked.connect(self.start_scan)
        scan_group_layout.addWidget(self.scan_button)

        main_layout.addLayout(scan_group_layout)
        main_layout.addSpacing(20) # Add some space

        # --- Search Section ---
        search_group_layout = QVBoxLayout()
        search_group_layout.addWidget(QLabel("### Search Files"))

        # Search input and button
        search_input_layout = QHBoxLayout()
        self.search_term_input = QLineEdit()
        self.search_term_input.setPlaceholderText("Enter search term (e.g., 'report' or 'invoice')")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.perform_search)
        search_input_layout.addWidget(self.search_term_input)
        search_input_layout.addWidget(self.search_button)
        search_group_layout.addLayout(search_input_layout)

        # Optional: Search by Disk Name
        search_disk_layout = QHBoxLayout()
        search_disk_layout.addWidget(QLabel("Search on Disk (optional):"))
        self.search_disk_input = QLineEdit()
        self.search_disk_input.setPlaceholderText("e.g., My External HDD")
        search_disk_layout.addWidget(self.search_disk_input)
        search_group_layout.addLayout(search_disk_layout)

        main_layout.addLayout(search_group_layout)
        main_layout.addSpacing(20)

        # --- Results Display ---
        main_layout.addWidget(QLabel("### Results"))
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["Filename", "Filepath", "Size (Bytes)", "Last Modified", "Disk Name"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive) # Auto-resize columns
        main_layout.addWidget(self.results_table)

        self.setLayout(main_layout)

    def browse_directory(self):
        """Opens a dialog to select a directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directory:
            self.dir_path_input.setText(directory)

    def start_scan(self):
        """Initiates the disk scanning process in a separate thread."""
        directory_path = self.dir_path_input.text()
        disk_name = self.disk_name_input.text().strip()

        if not directory_path:
            QMessageBox.warning(self, "Input Error", "Please select a directory to scan.")
            logger.warning("Scan initiated without selecting a directory.")
            return
        if not disk_name:
            QMessageBox.warning(self, "Input Error", "Please enter a name for the disk.")
            logger.warning("Scan initiated without entering a disk name.")
            return

        # Clear previous results/messages
        self.results_table.setRowCount(0)
        self.results_table.clearContents()
        self.results_table.setHorizontalHeaderLabels(["Filename", "Filepath", "Size (Bytes)", "Last Modified", "Disk Name"])


        # Disable buttons during scan
        self.scan_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.search_button.setEnabled(False)
        self.results_table.setRowCount(0) # Clear table for scan progress

        reply = QMessageBox.question(self, 'Confirm Scan',
                                     f"Scanning '{directory_path}' as '{disk_name}'.\n\n"
                                     f"WARNING: This will DELETE ALL existing records for '{disk_name}' "
                                     f"from the database before re-scanning. Are you sure you want to proceed?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.scan_button.setEnabled(True)
            self.browse_button.setEnabled(True)
            self.search_button.setEnabled(True)
            logger.info("Scan cancelled by user.")
            return

        # Start the scanner thread
        self.scanner_thread = DiskScannerThread(directory_path, disk_name, self.db_manager)
        self.scanner_thread.file_scanned.connect(self.update_scan_progress)
        self.scanner_thread.scan_finished.connect(self.scan_completed)
        self.scanner_thread.scan_error.connect(self.scan_error_occurred)
        self.scanner_thread.start()

        QMessageBox.information(self, "Scan Started", f"Scanning '{directory_path}' as '{disk_name}'. This may take a while...")
        logger.info(f"GUI: Scan started for '{directory_path}' as '{disk_name}'.")


    def update_scan_progress(self, message):
        """Updates the GUI with scan progress messages."""
        # For now, still printing to console. We'll enhance this later.
        print(message)
        # Future improvement: Update a status bar or a dedicated log display in the GUI

    def scan_completed(self, total_files):
        """Handles actions after the scan is completed."""
        QMessageBox.information(self, "Scan Complete", f"Scan finished! {total_files} files cataloged.")
        self.scan_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.search_button.setEnabled(True)
        # Optionally, trigger a search for the newly scanned disk
        self.search_term_input.setText("") # Clear search term
        self.search_disk_input.setText(self.disk_name_input.text().strip()) # Pre-fill disk name
        self.perform_search() # Show all files from the newly scanned disk
        logger.info(f"GUI: Scan completed. Total files: {total_files}")

    def scan_error_occurred(self, error_message):
        """Handles errors during the scan."""
        QMessageBox.critical(self, "Scan Error", f"An error occurred during scan: {error_message}")
        self.scan_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.search_button.setEnabled(True)
        logger.error(f"GUI: Scan error occurred: {error_message}")

    def perform_search(self):
        """Performs a search based on user input and displays results."""
        search_term = self.search_term_input.text().strip()
        search_disk = self.search_disk_input.text().strip()

        if not search_term:
            QMessageBox.warning(self, "Input Error", "Please enter a search term.")
            logger.warning("Search initiated without entering a search term.")
            return

        self.results_table.setRowCount(0) # Clear previous results

        # Determine if searching on a specific disk
        if search_disk:
            results = self.db_manager.search_files(search_term, search_disk)
        else:
            results = self.db_manager.search_files(search_term)

        if results:
            self.results_table.setRowCount(len(results))
            for row_idx, file_data in enumerate(results):
                self.results_table.setItem(row_idx, 0, QTableWidgetItem(file_data['filename']))
                self.results_table.setItem(row_idx, 1, QTableWidgetItem(file_data['filepath']))
                self.results_table.setItem(row_idx, 2, QTableWidgetItem(str(file_data['filesize'])))
                self.results_table.setItem(row_idx, 3, QTableWidgetItem(file_data['last_modified'].strftime("%Y-%m-%d %H:%M:%S")))
                self.results_table.setItem(row_idx, 4, QTableWidgetItem(file_data['disk_name']))
            logger.info(f"GUI: Search for '{search_term}' (disk: {search_disk if search_disk else 'All'}) displayed {len(results)} results.")
        else:
            QMessageBox.information(self, "No Results", "No files found matching your search criteria.")
            logger.info(f"GUI: No results found for search term '{search_term}' (disk: {search_disk if search_disk else 'All'}).")




def main():
    app = QApplication(sys.argv)
    main_window = DiskCatalogerApp()
    main_window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()