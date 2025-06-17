from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSON
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    files = relationship("FileUpload", back_populates="user")
    questions = relationship("QASession", back_populates="user")

    def __repr__(self):
        return f"<User {self.email}>"


class FileUpload(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    storage_url = Column(Text)
    upload_status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="files")
    transcript = relationship("Transcript", back_populates="file", uselist=False)

    def __repr__(self):
        return f"<FileUpload {self.original_filename}>"


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    transcript_text = Column(Text)
    summary = Column(Text)
    processing_status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    file = relationship("FileUpload", back_populates="transcript")

    def __repr__(self):
        return f"<Transcript for file_id={self.file_id}>"


class QASession(Base):
    __tablename__ = "qa_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text)
    source_files = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="questions")

    def __repr__(self):
        return f"<QASession for user_id={self.user_id}>"
