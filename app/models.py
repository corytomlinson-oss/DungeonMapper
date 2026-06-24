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
