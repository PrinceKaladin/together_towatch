from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    google_id = Column(String, unique=True, index=True, nullable=True)

class Preset(Base):
    __tablename__ = "presets"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    preset_type = Column(String)
    cover = Column(String)
    episodes = relationship("Episode", back_populates="preset", cascade="all, delete-orphan")

class Episode(Base):
    __tablename__ = "episodes"
    id = Column(Integer, primary_key=True, index=True)
    preset_id = Column(Integer, ForeignKey("presets.id"))
    name = Column(String)
    video_type = Column(String)
    src = Column(String)
    order = Column(Integer)
    preset = relationship("Preset", back_populates="episodes")