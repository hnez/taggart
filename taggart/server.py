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

        self.app.get("/image_files/<hash>.jpg", callback=self.get_image_file)

        self.app.get("/images", callback=self.get_images)
        self.app.get("/images/random", callback=self.redirect_image_random)
        self.app.get("/images/<id>", callback=self.get_image_info)
        self.app.get("/images/<id>/latent/preview.png", callback=self.get_latent_preview_file)

        self.app.post("/images/<id>/crops", callback=self.post_image_crop)

        self.app.get("/images/<id>/neighbors", callback=self.get_image_neighbors)
        self.app.get("/images/<id>/similar", callback=self.get_image_similar)

        self.app.get("/images/<id>/tags", callback=self.get_image_tags)
        self.app.get("/images/<id>/tags/<tag>", callback=self.get_image_tag)
        self.app.put("/images/<id>/tags/<tag>", callback=self.set_image_tag)

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

    def _image_info(self, image):
        crop = image.crop_dimensions()
        image_file = image.image_file()

        url = f"/image_files/{image_file.hexhash}.jpg"

        # TODO: only add if it exists
        latent_url = f"/images/{image.hexid}/latent/preview.png"

        return {"id": image.hexid, "url": url, "crop": crop, "latent_url": latent_url}

    def run(self, *kargs, **kwargs):
        self.app.run(*kargs, **kwargs)

    def get_image_file(self, hash: str):
        path = self.db.image_files[hash].path()

        return bottle.static_file(path, "/")

    def get_images(self):
        raise NotImplementedError

    def redirect_image_random(self):
        image = self.db.images.get_random()

        if image is None:
            pass

        bottle.redirect(f"/images/{image.hexid}")

    def get_image_info(self, id: str):
        return self._image_info(self.db.images[id])

    def get_latent_preview_file(self, id: str):
        pil = self.db.images[id].latent_preview()

        if pil is None:
            raise bottle.HTTPError(404, "Latents of this type have not been generated for this image")

        return self._serve_pil_image(pil)

    def post_image_crop(self, id: str):
        crop = bottle.request.json

        new_image = self.db.images[id].cropped_copy(
            crop["rotation"], crop["left"], crop["top"], crop["width"], crop["height"]
        )

        bottle.response.set_header("Content-Location", f"/images/{new_image.hexid}")

    def get_image_neighbors(self, id: str):
        image = self.db.images[id]

        serial_next, serial_prev, shuffle_next, shuffle_prev = tuple(
            self._image_info(n) if n is not None else None for n in image.neighbors()
        )

        return {
            "serial_prev": serial_prev,
            "serial_next": serial_next,
            "shuffle_prev": shuffle_prev,
            "shuffle_next": shuffle_next,
        }

    def get_image_similar(self, id: str):
        image = self.db.images[id]

        similar = tuple((self._image_info(img), value) for img, value in image.similar_images())

        return {"images": similar}

    def get_image_tags(self, id: str):
        image = self.db.images[id]

        tags = dict((tag.tag, {}) for tag in self.db.tags)

        for tag_name, value in image.similar_tags() or []:
            tags[tag_name]["estimated"] = value

        for image_tag in image.tags:
            tags[image_tag.tag]["assigned"] = image_tag.weight()

        return tags

    def get_image_tag(self, id: str, tag: str):
        # This is obviously a very inefficient way to do this.
        # It is only here to make the API feel more complete.
        # Optimize if it actually gets used.
        return self.get_image_tags(id)[tag]

    def set_image_tag(self, id: str, tag: str):
        req = bottle.request.json
        tag = self._clean_tag_name(tag)
        assigned_weight = req.get("assigned", 1)

        self.db.images[id].tags[tag].set_weight(assigned_weight)

    def get_tags(self):
        return dict((tag.tag, {"occurrences": occurrences}) for tag, occurrences in self.db.tags.occurrences())

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
                    images[image.hexid] = {}

                images[image.hexid]["info"] = self._image_info(image)
                images[image.hexid]["estimated"] = similarity

        images = sorted(
            images.values(),
            key=lambda a: a["assigned"] if "assigned" in a else a["estimated"],
            reverse=True,
        )

        return {"images": images}
