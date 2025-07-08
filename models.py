from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
import datetime

# CORRECT: Import the single, shared Base from your database.py file
from database import Base


class ActivityLog(Base):
    __tablename__ = "activity"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    action = Column(String, nullable=False)
    filename = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    ip_address = Column(String)
    user_agent = Column(String)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String(20), nullable=False, default="owner")

    files = relationship("UserFile", back_populates="user")
    # NEW: Add relationship to invites
    invites_created = relationship("Invite", back_populates="owner")


class QAHistory(Base):
    __tablename__ = "qa_history"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    sources_used = Column(JSON)


class UserFile(Base):
    __tablename__ = 'user_files'

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_size = Column(Integer)
    upload_timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    email = Column(String, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))

    s3_key = Column(String, nullable=True)
    transcript_text = Column(Text, nullable=True)
    transcript_segments = Column(Text, nullable=True)
    # FIX: Add the missing 'tag' column that the frontend needs
    tag = Column(String, nullable=True, index=True)

    user = relationship("User", back_populates="files")


# NEW: Add the missing Invite model
class Invite(Base):
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="invites_created")
