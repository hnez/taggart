#!/usr/bin/env python3

import functools
import io

import bottle

from .database import Database


class Server:
    STATIC_ROUTES = (
        ("/", "index.html"),
        ("/style.css", "style.css"),
        ("/spinner.gif", "spinner.gif"),
        ("/common.js", "common.js"),
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
        self.app.get("/images/<id:int>/latent/preview.png", callback=self.get_latent_preview_file)

        self.app.post("/images/<id:int>/crops", callback=self.post_image_crop)

        self.app.get("/images/<id:int>/neighbors", callback=self.get_image_neighbors)
        self.app.get("/images/<id:int>/similar", callback=self.get_image_similar)

        self.app.get("/images/<id:int>/tags", callback=self.get_image_tags)
        self.app.get("/images/<id:int>/tags/<tag>", callback=self.get_image_tag)
        self.app.put("/images/<id:int>/tags/<tag>", callback=self.set_image_tag)

        self.app.get("/tags", callback=self.get_tags)
        self.app.get("/tags/<filter>/images", callback=self.get_tag_images)

    def _clean_tag_name(self, name):
        return name.strip().lower()

    def _qp_trueish(self, query_param):
        return self.QP_TRUEISH[query_param.strip().lower()]

    def _split_tag_filter(self, filter):
        return tuple(self._clean_tag_name(tag) for tag in filter.split("+"))

    def _serve_pil_image(self, pil, file_type="png"):
        buf = io.BytesIO()
        pil.save(buf, file_type)
        buf.seek(0)

        bottle.response.content_type = f"image/{file_type}"

        return buf

    def run(self, *kargs, **kwargs):
        self.app.run(*kargs, **kwargs)

    def get_images(self):
        raise NotImplementedError

    def get_image_file(self, id: int):
        path = self.db.images[id].path()

        return bottle.static_file(path, "/")

    def get_latent_preview_file(self, id: int):
        pil = self.db.images[id].latent_preview()

        if pil is None:
            raise bottle.HTTPError(404, "Latents have not been generated for this image")

        return self._serve_pil_image(pil)

    def post_image_crop(self, id: int):
        crop = bottle.request.json

        res = self.db.images[id].cropped(crop["left"], crop["top"], crop["width"], crop["height"])

        bottle.response.set_header("Content-Location", f"/images/{res.id}")

        return

    def get_image_neighbors(self, id: int):
        image = self.db.images[id]

        serial_prev, serial_next = image.neighbors()
        shuffle_prev, shuffle_next = image.shuffled_neighbors()

        return {
            "serial_prev": serial_prev.id,
            "serial_next": serial_next.id,
            "shuffle_prev": shuffle_prev.id,
            "shuffle_next": shuffle_next.id,
        }

    def get_image_similar(self, id: int):
        image = self.db.images[id]

        similar = tuple((img.id, value) for img, value in image.similar_images())

        return {"images": similar}

    def get_image_tags(self, id: int):
        image = self.db.images[id]

        tags = dict((name, {"estimated": weight}) for name, weight in image.similar_tags().items())

        for image_tag in image.tags:
            tags[image_tag.label]["assigned"] = image_tag.weight()

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

        self.db.images[id].tags[tag].set_weight(assigned_weight)

    def get_tags(self):
        return dict((tag.label, {"occurrences": occurrences}) for tag, occurrences in self.db.tags.occurrences())

    def get_tag_images(self, filter: str):
        tags = filter.split("+")

        include_assigned = self._qp_trueish(bottle.request.query.assigned)
        include_estimated = self._qp_trueish(bottle.request.query.estimated)

        images = dict()

        if include_assigned:
            raise NotImplementedError()

        if include_estimated:
            for image, similarity in self.db.tags[tags].similar_images():
                if image.id not in images:
                    images[image.id] = {}

                images[image.id]["estimated"] = similarity

        images = sorted(
            ({"id": id, **kw} for id, kw in images.items()),
            key=lambda a: a["assigned"] if "assigned" in a else a["estimated"],
            reverse=True,
        )

        return {"images": images}
