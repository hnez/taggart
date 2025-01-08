#!/usr/bin/env python3

import hashlib
import os
import re
from collections.abc import Iterable

import PIL.Image

from .tracing import trace
from .utils import clamp, cosine_similarity, top_k


class ImageTag:
    UPDATE_TAG_WEIGHT = """INSERT INTO tags (image, tag, weight)
        SELECT rowid, :tag, :weight FROM images WHERE id == :id
        ON CONFLICT DO UPDATE SET weight=:weight"""

    def __init__(self, db, id: bytes, tag: str, weight: float):
        self._db = db
        self._weight = weight

        self.id = id
        self.tag = tag

    def weight(self):
        return self._weight

    def set_weight(self, weight):
        self._db.execute(self.UPDATE_TAG_WEIGHT, {"id": self.id, "tag": self.tag, "weight": weight})
        self._weight = weight

        # TODO: update the embeddings right here by adding the image embeddings
        # _if_ the tag was not already on the image before.
        self._db.tags._tag_embeddings = None


class ImageTags:
    SELECT_TAG = """SELECT weight FROM tags
        INNER JOIN images ON tags.image == images.rowid
        WHERE id == ? AND tag == ?"""
    SELECT_TAGS = """SELECT tag, weight FROM tags
        INNER JOIN images ON tags.image == images.rowid
        WHERE id == ? and weight != 0"""

    def __init__(self, db, id: bytes):
        self._db = db
        self.id = id

    def __getitem__(self, tag):
        res = self._db.execute(self.SELECT_TAG, (self.id, tag)).fetchone()

        # We treat tags with weight zero the same as unset tags.
        # So just return an ImageTag with weight zero if no tag is set yet.
        weight = res[0] if res is not None else 0

        return ImageTag(self._db, self.id, tag, weight)

    def __iter__(self):
        return iter(
            ImageTag(self._db, self.id, tag, weight) for tag, weight in self._db.execute(self.SELECT_TAGS, (self.id,))
        )


class Image:
    INSERT_CROPPED_COPY = """INSERT INTO images (file, rotation, crop_left, crop_top, width, height)
        SELECT file, ?, ?, ?, ?, ?
        FROM images WHERE id == ?"""

    SELECT_BY_ROWID = "SELECT id FROM images WHERE rowid == ?"
    SELECT_CROP = """SELECT
        rotation, crop_left, crop_top, images.width, images.height, image_files.width, image_files.height
        FROM images INNER JOIN image_files ON image_files.rowid == images.file
        WHERE id == ?"""
    SELECT_FILE_HASH = """SELECT hash FROM images
        INNER JOIN image_files ON image_files.rowid == images.file
        WHERE id == ?"""
    SELECT_NEIGHBORS = """SELECT
        (SELECT fwd.id FROM images AS fwd WHERE fwd.rowid > rev.rowid ORDER BY rowid ASC LIMIT 1),
        (SELECT fwd.id FROM images AS fwd WHERE fwd.rowid < rev.rowid ORDER BY rowid DESC LIMIT 1),
        (SELECT fwd.id FROM images AS fwd WHERE fwd.id > rev.id ORDER BY id ASC LIMIT 1),
        (SELECT fwd.id FROM images AS fwd WHERE fwd.id < rev.id ORDER BY id DESC LIMIT 1)
        FROM images AS rev WHERE rev.id == ?
        """

    def __init__(self, db, id: bytes):
        self._db = db
        self.id = id
        self.hexid = id.hex()
        self.tags = ImageTags(self._db, self.id)

    def crop_dimensions(self):
        (rotation, crop_left, crop_top, width, height, file_width, file_height) = self._db.execute(
            self.SELECT_CROP, (self.id,)
        ).fetchone()

        return {
            "rotation": rotation,
            "left": crop_left,
            "top": crop_top,
            "width": width,
            "height": height,
            "file_width": file_width,
            "file_height": file_height,
        }

    def cropped_copy(self, rotation: int, left: int, top: int, width: int, height: int):
        crop = (int(e) for e in (rotation, left, top, width, height))

        cur = self._db.execute(self.INSERT_CROPPED_COPY, (*crop, self.id))
        (new_id,) = self._db.execute(self.SELECT_BY_ROWID, (cur.lastrowid,)).fetchone()

        return Image(self._db, new_id)

    def image_file(self):
        (hash,) = self._db.execute(self.SELECT_FILE_HASH, (self.id,)).fetchone()

        return self._db.image_files[hash]

    @trace
    def latent_preview(self):
        lat = self._db.images.latents()
        my_tensor_row = lat.image_to_tensor_row(self)

        if my_tensor_row is None:
            return None

        latents = lat.cpu()
        latent = latents[my_tensor_row : my_tensor_row + 1]

        output = self._db.preview_decoder.forward(latent)
        output = output[0].transpose(0, -1).transpose(0, 1)

        output = output * 127.5 + 127.5
        output = output.clamp(0, 255).byte().numpy()

        image = PIL.Image.fromarray(output)

        return image

    def neighbors(self):
        res = self._db.execute(self.SELECT_NEIGHBORS, (self.id,)).fetchone()

        nxt, pre, shuf_nxt, shuf_pre = tuple(Image(self._db, id) if id is not None else None for id in res)

        return nxt, pre, shuf_nxt, shuf_pre

    def path(self):
        (path,) = self._db.execute(self.SELECT_PATH, (self.id,)).fetchone()

        return path

    def read(self):
        path = self.image_file().path()
        crop = self.crop_dimensions()

        pil = PIL.Image.open(path)
        pil = pil.convert("RGB")

        if crop["rotation"] != 0:
            pil = pil.rotate(crop["rotation"])

        crop = (
            clamp(crop["left"], 0, pil.width - 1),
            clamp(crop["top"], 0, pil.height - 1),
            clamp(crop["left"] + crop["width"], 1, pil.width),
            clamp(crop["top"] + crop["height"], 1, pil.height),
        )

        no_crop = (0, 0, pil.width, pil.height)

        if crop != no_crop:
            pil = pil.crop(crop)

        return pil

    def set_embedding(self, embedding):
        self._db.images.embeddings().set_image_row(self, embedding)

    def set_latent(self, latent):
        self._db.images.latents().set_image_row(self, latent)

    @trace
    def similar_images(self, count=100):
        emb = self._db.images.embeddings()
        my_tensor_row = emb.image_to_tensor_row(self)

        if my_tensor_row is None:
            return tuple()

        embeddings = emb.gpu()
        image_emb = embeddings[my_tensor_row]

        embeddings = embeddings.unsqueeze(-2)
        image_emb = image_emb.unsqueeze(0).unsqueeze(-1)

        cosine_similarities = cosine_similarity(embeddings, image_emb).squeeze(-2, -1)

        result = list()

        for tensor_row, value in top_k(cosine_similarities, count):
            if tensor_row == my_tensor_row:
                continue

            image = emb.tensor_row_to_image(tensor_row)

            if image is None:
                continue

            result.append((image, value))

        return tuple(result)

    @trace
    def similar_tags(self):
        emb = self._db.images.embeddings()
        my_tensor_row = emb.image_to_tensor_row(self)

        if my_tensor_row is None:
            return None

        embeddings = emb.gpu()
        image_emb = embeddings[my_tensor_row]
        tags_emb = self._db.tags.embeddings()

        if tags_emb is None:
            return []

        tags, tag_emb = tags_emb

        tag_emb = tag_emb.unsqueeze(-2)
        image_emb = image_emb.unsqueeze(0).unsqueeze(-1)

        cosine_similarities = cosine_similarity(tag_emb, image_emb).squeeze(-2, -1)
        cosine_similarities = cosine_similarities.tolist()

        return zip(tags, cosine_similarities)


class Images:
    INSERT_EXIF = """INSERT OR IGNORE INTO
        exif (file, tag_id, value)
        SELECT rowid, :tag_id, :value
        FROM image_files WHERE hash == :hash"""
    INSERT_IMAGE = """INSERT OR IGNORE INTO
        images (file, rotation, width, height)
        SELECT rowid, :rotation, :width, :height
        FROM image_files WHERE hash == :hash"""
    INSERT_IMAGE_FILE = """INSERT OR IGNORE INTO
        image_files (path, file_size, mime_type, hash, width, height)
        VALUES (:path, :file_size, :mime_type, :hash, :width, :height)"""

    MIME_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "MPO": "image/jpeg"}

    RE_IMAGE_EXT = re.compile(r"(?i)\.(?:png$)|(?:jpe?g$)")

    ROTATIONS = {0: 0, 1: 0, 3: 180, 6: 270, 8: 90}

    SELECT_COUNT = "SELECT COUNT(*) FROM images"
    SELECT_RANDOM = "SELECT id FROM images ORDER BY random() LIMIT 1"

    def __init__(self, db):
        self._db = db

    def add_multiple(self, paths: Iterable[str]):
        for path in paths:
            with open(path, "rb") as fd:
                data = fd.read()
                hash = hashlib.sha256(data).digest()
                file_size = len(data)
                del data

            file_meta = {"path": path, "hash": hash, "file_size": file_size}
            image_meta = {"hash": hash}

            pil = PIL.Image.open(path)

            file_meta["width"] = pil.width
            file_meta["height"] = pil.height
            file_meta["mime_type"] = self.MIME_TYPES[pil.format]

            exif = pil.getexif()

            exif_rows = list()

            for tag_id, value in exif.items():
                if isinstance(value, PIL.TiffImagePlugin.IFDRational):
                    value = float(value)

                exif_rows.append({"hash": hash, "tag_id": tag_id, "value": value})

            exif_rotation = exif.get(PIL.ExifTags.Base.Orientation, 1)
            image_meta["rotation"] = self.ROTATIONS[exif_rotation]

            if image_meta["rotation"] in (0, 180):
                image_meta["width"] = file_meta["width"]
                image_meta["height"] = file_meta["height"]
            else:
                image_meta["width"] = file_meta["height"]
                image_meta["height"] = file_meta["width"]

            self._db.execute(self.INSERT_IMAGE_FILE, file_meta)
            self._db.executemany(self.INSERT_EXIF, exif_rows)
            self._db.execute(self.INSERT_IMAGE, image_meta)

    def add(self, path: str):
        self.add_multiple([self.path])

    def add_directories(self, dirs: Iterable[str]):
        for dir in dirs:
            for dirpath, _dirnames, filenames in os.walk(dir):
                paths = tuple(
                    os.path.join(dirpath, name) for name in sorted(filenames) if self.RE_IMAGE_EXT.search(name)
                )

                if len(paths) == 0:
                    continue

                self.add_multiple(paths)

                print(f"Added {len(paths)} images from {dirpath}")

    def add_directory(self, dir: str):
        self.add_directories([dir])

    def embeddings(self):
        tensor_name = self._db.config.get("default-embeddings", "siglip-so400m-patch14-384")
        return self._db.tensors[tensor_name]

    def get_random(self):
        res = self._db.execute(self.SELECT_RANDOM).fetchone()

        if res is None:
            return None

        return self[res[0]]

    def latents(self):
        tensor_name = self._db.config.get("default-latents", "sd15-79x52")
        return self._db.tensors[tensor_name]

    def __getitem__(self, id: str | bytes):
        if isinstance(id, str):
            id = bytes.fromhex(id)

        return Image(self._db, id)

    def __len__(self):
        (count,) = self._db.execute(self.SELECT_COUNT).fetchone()

        return count
