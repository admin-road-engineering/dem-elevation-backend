# api/index.py
# This file is the entry point for Vercel Serverless Functions

# Import the FastAPI app from your main backend file
from main import app

# Vercel's Python runtime looks for an 'app' object (for frameworks like FastAPI)
# or a 'handler' function (for pure lambda-style functions).
# By importing your FastAPI 'app', you make it available to Vercel. 