import sys
import os

# Add the backend directory to the path so we can import from it
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app
