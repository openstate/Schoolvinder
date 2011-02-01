from google.appengine.ext import db


class School(db.Model):
    brin = db.StringProperty()
    name = db.StringProperty()
    slug = db.StringProperty()