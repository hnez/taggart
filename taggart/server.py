#!/usr/bin/env python3

import functools

import bottle

from .database import Database


class Server:
    STATIC_ROUTES = (
        ("/", "index.html"),
        ("/style.css", "style.css"),
        ("/spinner.gif", "spinner.gif"),
        ("/browse_similar/", "browse_similar/index.html"),
        ("/browse_similar/script.js", "browse_similar/script.js"),
        ("/browse_similar/style.css", "browse_similar/style.css"),
        ("/browse_tags/", "browse_tags/index.html"),
        ("/browse_tags/script.js", "browse_tags/script.js"),
        ("/browse_tags/style.css", "browse_tags/style.css"),
    )

    def __init__(self, db: Database):
        self.db = db
        self.app = bottle.Bottle()

        for route, filename in self.STATIC_ROUTES:
            self.app.get(route, callback=functools.partial(bottle.static_file, filename, "static"))

        self.app.get("/img/<id:int>.json", callback=self.get_image_info)
        self.app.get("/img/<id:int>.jpg", callback=self.get_image_file)
        self.app.put("/img/<id:int>/tags/current/<name>", callback=self.add_tag_to_image)
        self.app.delete("/img/<id:int>/tags/current/<name>", callback=self.remove_tag_from_image)

        self.app.get("/tags.json", callback=self.get_tags)
        self.app.get("/tag/<filter>/images/by_embedding.json", callback=self.get_images_by_tag_embedding)

    def run(self, *kargs, **kwargs):
        self.app.run(*kargs, **kwargs)

    def get_image_info(self, id: int):
        count = self.db.image_count()
        path = self.db.image_path(id)
        current_tags = self.db.image_tags(id)
        shuffle_prev, shuffle_next = self.db.image_shuffle_neighbors(id)

        serial_next = id % count + 1
        serial_prev = (count + id - 2) % count + 1

        similar = self.db.images_similar(id)
        available_tags = self.db.tags_similar(id)

        return {
            "tags": {
                "current": current_tags,
                "available": available_tags,
            },
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

    def add_tag_to_image(self, id: int, name: str):
        self.db.image_add_tag(id, name.strip().lower())

    def remove_tag_from_image(self, id: int, name: str):
        self.db.image_remove_tag(id, name.strip().lower())

    def get_tags(self):
        tags = self.db.tags_by_occurrence()

        return {"tags": tags}

    def get_images_by_tag_embedding(self, filter: str):
        tags = filter.split("+")
        image_similarity_pairs = self.db.images_similar_to_tags(tags)

        return {"images": image_similarity_pairs}
