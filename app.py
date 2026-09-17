"""The Form in the browser, for Vercel: it finds `app` here and serves it (see README, "Deploy to Vercel")."""
from ufaz_agreement_generator.cli import DEFAULT_TEMPLATE, load_settings
from ufaz_agreement_generator.web import create_app

app = create_app(load_settings(None, None), DEFAULT_TEMPLATE)
