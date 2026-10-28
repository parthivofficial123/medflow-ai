"""Entry point for Vercel, which looks for a WSGI app named ``app`` here.

Locally, use ``flask --app medflow run --debug`` instead.
"""

from medflow import create_app

app = create_app()
