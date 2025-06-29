from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

hash_in_db = "$2b$12$rofFNDhuRlQEZduUpnD8ZOSM0b6bi4RIaB3xcQ6qc9SXymSpCOHcK"

print(pwd_context.verify("wrongpassword", hash_in_db))
