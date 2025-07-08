from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# 1. Import the centralized settings object. This is the single source of truth.
from config import settings

# 2. Use the already validated database URL from the settings object.
#    No need for os.getenv() or any custom functions here.
SQLALCHEMY_DATABASE_URL = settings.database_url

# 3. Create the engine directly with the guaranteed-to-be-correct URL.
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 4. Create the session maker.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. Create the Base for all models to inherit from.
Base = declarative_base()


# 6. Define the dependency to get a database session in your routes.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 7. Define a function to create tables (often used for initial setup or testing).


def create_tables():
    # We can import models here to ensure Base is defined first,
    # though it's not strictly necessary with this cleaner structure.
    # from models import User, UserFile # etc.
    Base.metadata.create_all(bind=engine)
