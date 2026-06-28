from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base


class SavedDungeon(Base):
    __tablename__ = "dungeons"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    area_type = Column(String, nullable=False)
    size = Column(String, nullable=False)
    num_levels = Column(Integer, nullable=False)
    seed = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DungeonSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    dm_token = Column(String, nullable=False)
    area_type = Column(String, nullable=False)
    size = Column(String, nullable=False)
    num_levels = Column(Integer, nullable=False)
    seed = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    session_code = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    color = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
