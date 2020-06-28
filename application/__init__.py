from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from application.logger import Logger

# globally accessible variables
db = SQLAlchemy()
cors = CORS()


def create_app(config):
    app = Flask(__name__)
    app.config.from_object(config)

    cors.init_app(app)
    db.init_app(app)

    with app.app_context():
        from . import routes
        from application.models import Meta
        from application.tasks import sync_district_data, sync_stats

        db.create_all()

        # create meta
        Meta.create_meta()

        # try to sync data on server start
        sync_district_data()
        sync_stats()

        return app
