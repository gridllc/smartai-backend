from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)


class Activity(Base):
    __tablename__ = "activity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    action = Column(String, nullable=False)
    filename = Column(String)
    timestamp = Column(String, nullable=False)
    ip_address = Column(String)
    user_agent = Column(String)


class QAHistory(Base):
    __tablename__ = "qa_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    timestamp = Column(String, nullable=False)
    sources_used = Column(Text)  # JSON string


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    token_hash = Column(String, nullable=False)
    created_at = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)
    used = Column(Boolean, default=False)


class UserFile(Base):
    __tablename__ = "user_files"
    __table_args__ = (UniqueConstraint(
        "email", "filename", name="uix_email_filename"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_size = Column(Integer)
    upload_timestamp = Column(String, nullable=False)
