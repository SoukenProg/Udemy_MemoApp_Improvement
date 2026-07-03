from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class memo(db.Model):
    __tablename__ = "memo"
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    title = db.Column(db.Text,nullable=False)
    body = db.Column(db.Text, nullable=False)
    createduser = db.Column(db.Integer,nullable=False)

class user(db.Model):
    __tablename__ = "user"
    unum = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userid = db.Column(db.Text, nullable=False, unique=True)
    password = db.Column(db.Text,nullable=False)
