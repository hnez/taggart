#!/usr/bin/env python3

import bottle

from .database import Database


class Server:
    def __init__(self, db: Database):
        self.db = db
        self.app = bottle.Bottle()

        self.app.get("/", callback=self.get_index)
        self.app.get("/script.js", callback=self.get_script)
        self.app.get("/style.css", callback=self.get_style)
        self.app.get("/img/<id:int>.json", callback=self.get_image_info)
        self.app.get("/img/<id:int>.jpg", callback=self.get_image_file)

    def run(self):
        self.app.run()

    def get_index(self):
        return bottle.static_file("index.html", "static")

    def get_script(self):
        return bottle.static_file("script.js", "static")

    def get_style(self):
        return bottle.static_file("style.css", "static")

    def get_image_info(self, id: int):
        count = self.db.image_count()
        path = self.db.image_path(id)
        tags = self.db.image_tags(id)
        shuffle_prev, shuffle_next = self.db.image_shuffle_neighbors(id)

        serial_next = id % count + 1
        serial_prev = (count + id - 2) % count + 1

        similar = self.db.image_similar(id)

        return {
            "tags": tags,
            "path": path,
            "id": id,
            "shuffle_prev": shuffle_prev,
            "shuffle_next": shuffle_next,
            "serial_prev": serial_prev,
            "serial_next": serial_next,
            "similar": similar,
        }

    def get_image_file(self, id: int):
        path = self.db.image_path(id)

        return bottle.static_file(path, "/")
