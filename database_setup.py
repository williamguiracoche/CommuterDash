from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False)
    picture = Column(String(250))


class SavedStation(Base):
    __tablename__ = 'station'

    gtfs_id = Column(String(3), primary_key=True)
    order = Column(Integer)
    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    user = relationship(User)

    @property
    def serialize(self):
        """Return object data in easily serializeable format"""
        return {
            'gtfs_id': self.name,
            'user_id': self.user_id,
            'order': self.order,
        }

engine = create_engine('sqlite:///savedstations.db')
Base.metadata.create_all(engine)
