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
        self.app.put("/img/<id:int>/tags/current/<tag>", callback=self.set_image_tag)
        self.app.put("/img/<id:int>/ratings/<category>", callback=self.set_image_rating)

        self.app.get("/tags.json", callback=self.get_tags)
        self.app.get("/tag/<filter>/images/by_embedding.json", callback=self.get_images_by_tag_embedding)

    def _clean_tag_name(self, name):
        return name.strip().lower()

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

    def set_image_tag(self, id: int, tag: str):
        req = bottle.request.json
        tag = self._clean_tag_name(tag)
        weight = req.get("weight", 1)

        self.db.image_set_tag_weight(id, tag, weight)

    def set_image_rating(self, id: int, category: str):
        req = bottle.request.json
        category = self._clean_tag_name(category)
        rating = req["rating"]

        self.db.image_set_rating(id, category, rating)

    def get_tags(self):
        tags = self.db.tags_by_occurrence()

        return {"tags": tags}

    def get_images_by_tag_embedding(self, filter: str):
        tags = filter.split("+")
        image_similarity_pairs = self.db.images_similar_to_tags(tags)

        return {"images": image_similarity_pairs}
