from database import SessionLocal

# This is the single, central place for the get_db dependency.
# It can be safely imported by any route file.


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
