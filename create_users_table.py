from database import engine
from models import Base
from dotenv import load_dotenv
load_dotenv()


Base.metadata.create_all(engine)
print("✅ Tables created.")
