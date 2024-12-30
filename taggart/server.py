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

    QP_TRUEISH = {"": True, "0": False, "1": True, "false": False, "true": True, "no": False, "yes": True}

    def __init__(self, db: Database):
        self.db = db
        self.app = bottle.Bottle()

        for route, filename in self.STATIC_ROUTES:
            self.app.get(route, callback=functools.partial(bottle.static_file, filename, "web"))

        self.app.get("/images", callback=self.get_images)
        self.app.get("/images/<id:int>.jpg", callback=self.get_image_file)

        self.app.get("/images/<id:int>/neighbors", callback=self.get_image_neighbors)
        self.app.get("/images/<id:int>/similar", callback=self.get_image_similar)

        self.app.get("/images/<id:int>/tags", callback=self.get_image_tags)
        self.app.get("/images/<id:int>/tags/<tag>", callback=self.get_image_tag)
        self.app.put("/images/<id:int>/tags/<tag>", callback=self.set_image_tag)

        self.app.get("/images/<id:int>/ratings", callback=self.get_image_ratings)
        self.app.get("/images/<id:int>/ratings/<category>", callback=self.get_image_rating)
        self.app.put("/images/<id:int>/ratings/<category>", callback=self.set_image_rating)

        self.app.get("/tags", callback=self.get_tags)
        self.app.get("/tags/<filter>/images", callback=self.get_tag_images)

    def _clean_tag_name(self, name):
        return name.strip().lower()

    def _qp_trueish(self, query_param):
        return self.QP_TRUEISH[query_param.strip().lower()]

    def _split_tag_filter(self, filter):
        return tuple(self._clean_tag_name(tag) for tag in filter.split("+"))

    def run(self, *kargs, **kwargs):
        self.app.run(*kargs, **kwargs)

    def get_images(self):
        raise NotImplementedError

    def get_image_file(self, id: int):
        path = self.db.image_path(id)

        return bottle.static_file(path, "/")

    def get_image_neighbors(self, id: int):
        count = self.db.image_count()

        serial_next = id % count + 1
        serial_prev = (count + id - 2) % count + 1

        shuffle_prev, shuffle_next = self.db.image_shuffle_neighbors(id)

        return {
            "serial_prev": serial_prev,
            "serial_next": serial_next,
            "shuffle_prev": shuffle_prev,
            "shuffle_next": shuffle_next,
        }

    def get_image_similar(self, id: int):
        return {"images": self.db.images_similar(id)}

    def get_image_tags(self, id: int):
        assigned_tags = self.db.image_tags(id)
        estimated_tags = self.db.tags_similar(id)

        tags = dict((name, {"estimated": weight}) for name, weight in estimated_tags.items())

        for name, weight in assigned_tags.items():
            tags[name]["assigned"] = weight

        return tags

    def get_image_tag(self, id: int, tag: str):
        # This is obviously a very inefficient way to do this.
        # It is only here to make the API feel more complete.
        # Optimize if it actually gets used.
        return self.get_image_tags(id)[tag]

    def set_image_tag(self, id: int, tag: str):
        req = bottle.request.json
        tag = self._clean_tag_name(tag)
        assigned_weight = req.get("assigned", 1)

        self.db.image_set_tag_weight(id, tag, assigned_weight)

    def get_image_ratings(self, id: int):
        ratings = dict((name, {}) for name in self.db.rating_categories())

        for name, value in self.db.image_ratings(id).items():
            ratings[name]["assigned"] = value

        return ratings

    def get_image_rating(self, id: int, category: str):
        # This is obviously a very inefficient way to do this.
        # It is only here to make the API feel more complete.
        # Optimize if it actually gets used.
        return self.get_image_ratings(id)[category]

    def set_image_rating(self, id: int, category: str):
        req = bottle.request.json
        category = self._clean_tag_name(category)
        assigned = req["assigned"]

        self.db.image_set_rating(id, category, assigned)

    def get_tags(self):
        tags = dict(
            (name, {"occurrences": occurrences}) for name, occurrences in self.db.tags_with_occurrence().items()
        )

        return tags

    def get_tag_images(self, filter: str):
        tags = filter.split("+")

        include_assigned = self._qp_trueish(bottle.request.query.assigned)
        include_estimated = self._qp_trueish(bottle.request.query.estimated)

        images = dict()

        if include_assigned:
            raise NotImplementedError()

        if include_estimated:
            for id, similarity in self.db.images_similar_to_tags(tags):
                if id not in images:
                    images[id] = {}

                images[id]["estimated"] = similarity

        images = sorted(
            ({"id": id, **kw} for id, kw in images.items()),
            key=lambda a: a["assigned"] if "assigned" in a else a["estimated"],
            reverse=True,
        )

        return {"images": images}
