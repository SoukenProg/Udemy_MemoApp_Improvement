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
    createduser = db.Column(db.Integer, db.ForeignKey("user.unum"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

class user(db.Model):
    __tablename__ = "user"
    unum = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userid = db.Column(db.Text, nullable=False, unique=True)
    password = db.Column(db.Text,nullable=False)


class category(db.Model):
    __tablename__ = "category"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    createduser = db.Column(db.Integer, db.ForeignKey("user.unum"), nullable=False)
