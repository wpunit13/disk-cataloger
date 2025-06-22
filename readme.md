# Disk Cataloger

An offline disk cataloger application that scans local directories and stores file metadata (filename, path, size, last modified, disk name) in a PostgreSQL database. This allows users to search for files across multiple "disks" (scanned directories) without them being physically connected.

## Features

*   Scan specified directories and store file metadata.
*   Search for files by name, optionally filtered by disk.
*   (Add any other features)

## Prerequisites

*   Python 3.8+
*   PostgreSQL database server (local or remote)

## Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/disk-cataloger.git
    cd disk-cataloger
    ```

2.  **Create a Python Virtual Environment (Recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -e .
    ```
    (The `-e .` installs your project in "editable" mode, which is good for development, but `pip install .` also works for a standard install.)

4.  **PostgreSQL Database Setup:**
    *   Ensure you have a PostgreSQL server running.
    *   Create a new database for the cataloger (e.g., `disk_catalog_db`).
    *   Create a database user with appropriate permissions for this database.

5.  **Configuration:**
    *   Copy the example configuration file:
        ```bash
        cp disk_cataloger/config.py.example disk_cataloger/config.py
        ```
    *   Edit `disk_cataloger/config.py` and replace the placeholder values with your actual PostgreSQL database credentials:
        ```python
        # disk_cataloger/config.py
        DB_CONFIG = {
            "host": "localhost",
            "database": "disk_catalog_db",
            "user": "your_db_user",
            "password": "your_db_password",
            "port": "5432"
        }
        ```

6.  **Initialize Database Tables:**
    The application will attempt to create tables on first run if they don't exist.

## Usage

To start the Disk Cataloger GUI:

```bash
disk-cataloger