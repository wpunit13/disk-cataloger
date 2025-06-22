from setuptools import setup, find_packages

setup(
    name="disk-cataloger",
    version="0.1.0",
    author="Punit Walawalkar",
    author_email="wpunit13@gmail.com",
    description="An offline disk cataloger using PostgreSQL.",
long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/disk-cataloger', # Optional: if you host it on GitHub
    packages=find_packages(), # Automatically finds your 'disk_cataloger' package
    install_requires=[
        'psycopg2-binary',
        'PyQt5',
        # Add any other dependencies here
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License', # Or your chosen license
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.8', # Specify minimum Python version
    entry_points={
        'console_scripts': [
            'disk-cataloger=disk_cataloger.gui_scan_and_insert_file:main', # If you have a main function to run the GUI
        ],
    },


)