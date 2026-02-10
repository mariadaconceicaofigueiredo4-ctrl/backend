from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "False") == "True"

    SECRET_KEY = os.getenv("SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 120))

    DATABASE_URL = os.getenv("DATABASE_URL")

settings = Settings()
