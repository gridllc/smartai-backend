from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class ActivityLog(Base):
    __tablename__ = "activity"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    action = Column(String, nullable=False)
    filename = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String)
    user_agent = Column(String)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)  # this matches the table
    name = Column(String, nullable=False)

    role = Column(String(20), nullable=False, default="owner")  # ADD THIS

    files = relationship("UserFile", back_populates="user")


class QAHistory(Base):
    __tablename__ = "qa_history"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sources_used = Column(JSON)  # Stored as JSON array


class UserFile(Base):
    __tablename__ = "user_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    audio_url = Column(String, nullable=True)
    transcript_url = Column(String, nullable=True)

    user = relationship("User", back_populates="files")
