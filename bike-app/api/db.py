import os
import psycopg
from dotenv import load_dotenv
load_dotenv()

def get_conn():
    return psycopg.connect(os.getenv("DATABASE_URL"), autocommit=True)
