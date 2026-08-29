"""Vercel ASGI entry point without process-local background workers."""

from .main import create_app

app = create_app(serverless=True)
