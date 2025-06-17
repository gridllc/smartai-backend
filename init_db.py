from database import engine
from models import Base

def create_tables():
    print("🔧 Creating tables in PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully.")

if __name__ == "__main__":
    create_tables()