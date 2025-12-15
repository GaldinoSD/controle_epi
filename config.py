import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = 'chave-secreta-adaptlink'
    SQLALCHEMY_DATABASE_URI = "postgresql://jonatas:26828021jJ@localhost:5432/epi"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
