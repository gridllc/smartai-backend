# Step 1: Restore `database.py` to a Working Version

from database import SessionLocal
This version keeps `get_db`

# This is the central provider for database sessions.
# All route files will import get_db from HERE.


def get_db():
    db = SessionLocal()
    try:
        where all your other files expect it to be, but it loads the database URL reliably.


**`database.pyyield db
finally:
    db.close()
