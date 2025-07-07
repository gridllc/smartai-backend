from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
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

    # These fields are correct!
    s3_key = Column(String, nullable=True)
    transcript_text = Column(Text, nullable=True)
    transcript_segments = Column(Text, nullable=True)

    user = relationship("User", back_populates="files")
