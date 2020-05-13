import os
from dotenv import load_dotenv

load_dotenv()
# BASEDIR = os.path.abspath(os.path.dirname(__file__))
# load_dotenv(os.path.join(BASEDIR, '.env'))

api_key = os.environ.get("API_KEY")
postgres = os.environ.get("postgres")