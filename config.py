import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = 'chave-secreta-adaptlink'
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'controle_epi.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
