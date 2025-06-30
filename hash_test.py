from passlib.context import CryptContext

# Your bcrypt hash from the database
hash_in_db = "$2b$12$rofFNDhuRlQEZduUpnD8ZOSM0b6bi4RIaB3xcQ6qc9SXymSpCOHcK"

# The plain password you think should match
plain_password = "yourpassword123"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Test it
print(pwd_context.verify(plain_password, hash_in_db))
