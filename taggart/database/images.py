#!/usr/bin/env python3

import os
import re
from collections.abc import Iterable

import torch
from PIL import Image as PILImage

from .utils import clamp, cosine_similarity, top_k


class ImageTag:
    INSERT_TAG = "INSERT OR IGNORE INTO tags (label) VALUES (?)"

    UPDATE_TAG_WEIGHT = """INSERT INTO image_tags (image, tag, weight)
        SELECT :image, rowid, :weight FROM tags WHERE label == :label
        ON CONFLICT DO UPDATE SET weight=:weight"""

    def __init__(self, db, id: int, label: str, weight: float):
        self._db = db
        self._weight = weight

        self.id = id
        self.label = label

    def weight(self):
        return self._weight

    def set_weight(self, weight):
        self._db.execute(self.INSERT_TAG, (self.label,))
        self._db.execute(self.UPDATE_TAG_WEIGHT, {"image": self.id, "label": self.label, "weight": weight})

        self._weight = weight

        # TODO: update the embeddings right here by adding the image embeddings
        # _if_ the tag was not already on the image before.
        self._db._tag_embeddings = None


class ImageTags:
    SELECT_TAG = """SELECT weight FROM image_tags
        INNER JOIN tags ON image_tags.tag == tags.rowid
        WHERE image_tags.image == ?"""
    SELECT_TAGS = """SELECT label, weight FROM image_tags
        INNER JOIN tags ON image_tags.tag == tags.rowid
        WHERE image_tags.image == ? AND weight != 0"""

    def __init__(self, db, id: int):
        self._db = db
        self.id = id

    def __getitem__(self, label):
        res = self._db.execute(self.SELECT_TAG, (self.id,)).fetchone()

        # We treat tags with weight zero the same as unset tags.
        # So just return an ImageTag with weight zero if no tag is set yet.
        weight = res[0] if res is not None else 0

        return ImageTag(self._db, self.id, label, weight)

    def __iter__(self):
        return iter(
            ImageTag(self._db, self.id, label, weight)
            for label, weight in self._db.execute(self.SELECT_TAGS, (self.id,))
        )


class Image:
    INSERT_CROPPED = """INSERT INTO images (path, crop_left, crop_top, width, height)
        SELECT path, crop_left + ?, crop_top + ?, ?, ?
        FROM images WHERE rowid == ?"""

    SELECT_HAS_LATENTS = "SELECT has_latents FROM images WHERE rowid == ?"
    SELECT_PATH = "SELECT path FROM images where rowid == ?"
    SELECT_PATH_AND_CROP = "SELECT path, crop_left, crop_top, width, height FROM images where rowid == ?"
    SELECT_SHUFFLE_NEIGHBORS = """SELECT
        (SELECT image FROM image_shuffle AS rev WHERE rev.rowid == fwd.rowid - 1),
        (SELECT image FROM image_shuffle AS rev WHERE rev.rowid == fwd.rowid + 1)
        FROM image_shuffle AS fwd WHERE fwd.image == ?"""

    UPDATE_HAS_EMBEDDING = "UPDATE images SET has_embedding = TRUE WHERE rowid == ?"
    UPDATE_HAS_LATENTS = "UPDATE images SET has_latents = TRUE WHERE rowid == ?"
    UPDATE_META = """UPDATE images SET
        file_size = :file_size,
        width = :width,
        height = :height,
        exif_camera = :exif_camera,
        exif_ts = :exif_ts,
        broken = :is_broken
        WHERE rowid == :id"""

    def __init__(self, db, id: int):
        self._db = db
        self.id = id
        self.tags = ImageTags(self._db, self.id)

    def crop_dimensions(self):
        (_path, crop_left, crop_top, width, height) = self._db.execute(
            self.SELECT_PATH_AND_CROP, (self.id,)
        ).fetchone()

        return {
            "left": crop_left,
            "top": crop_top,
            "width": width,
            "height": height,
        }

    def cropped_copy(self, left: int, top: int, width: int, height: int):
        crop = (int(e) for e in (left, top, width, height))

        res = self._db.execute(self.INSERT_CROPPED, (*crop, self.id))
        new_id = res.lastrowid

        self._db._embeddings.resize((len(self._db.images) + 1, self._db.EMBEDDING_VEC_LEN))

        return Image(self._db, new_id)

    def latent_preview(self):
        (has_latents,) = self._db.execute(self.SELECT_HAS_LATENTS, (self.id,)).fetchone()

        if not has_latents:
            return None

        latents = self._db._latents.read_write()
        latent = latents[self.id : self.id + 1]

        output = self._db.preview_decoder.forward(latent)

        output = output[0].transpose(0, -1).transpose(0, 1)

        output = output * 127.5 + 127.5
        output = output.clamp(0, 255).byte().numpy()

        image = PILImage.fromarray(output)

        return image

    def neighbors(self):
        count = len(self._db.images)

        pre = (count + self.id - 2) % count + 1
        nxt = self.id % count + 1

        return (Image(self._db, pre), Image(self._db, nxt))

    def path(self):
        (path,) = self._db.execute(self.SELECT_PATH, (self.id,)).fetchone()

        return path

    def read(self):
        (path, crop_left, crop_top, width, height) = self._db.execute(self.SELECT_PATH_AND_CROP, (self.id,)).fetchone()

        pil = PILImage.open(path)

        # TODO: update metadata

        width = pil.width if width is None else width
        height = pil.height if height is None else height

        crop = (
            clamp(crop_left, 0, width),
            clamp(crop_top, 0, height),
            clamp(crop_left + width, 0, width),
            clamp(crop_top + height, 0, height),
        )

        no_crop = (0, 0, pil.width, pil.height)

        if crop != no_crop:
            pil = pil.crop(crop)

        return pil

    def set_embedding(self, embedding: torch.Tensor):
        embeddings = self._db._embeddings.read_write()
        embeddings[self.id] = embedding.to(embeddings.device)

        self._db.execute(self.UPDATE_HAS_EMBEDDING, (self.id,))

    def set_latent(self, latent: torch.Tensor):
        latents = self._db._latents.read_write()
        latents[self.id] = latent.to(latents.device)

        self._db.execute(self.UPDATE_HAS_LATENTS, (self.id,))

    def set_meta(self, is_broken: bool, file_size: int, width: int, height: int, exif_camera: str, exif_ts: int):
        self._db.execute(
            self.UPDATE_META,
            {
                "id": self.id,
                "is_broken": is_broken,
                "file_size": file_size,
                "width": width,
                "height": height,
                "exif_camera": exif_camera,
                "exif_ts": exif_ts,
            },
        )

    def similar_images(self, count=100):
        embeddings = self._db._embeddings.read_only()
        image_emb = embeddings[self.id]

        embeddings = embeddings.unsqueeze(-2)
        image_emb = image_emb.unsqueeze(0).unsqueeze(-1)

        cosine_similarities = cosine_similarity(embeddings, image_emb).squeeze(-2, -1)

        # Suppress _this_ image as it would always be the most similar
        cosine_similarities[self.id] = 0

        return tuple((Image(self._db, index), value) for index, value in top_k(cosine_similarities, count))

    def similar_tags(self):
        embeddings = self._db._embeddings.read_only()
        image_emb = embeddings[self.id]
        tag_emb = self._db.tag_embeddings()

        tag_emb = tag_emb.unsqueeze(-2)
        image_emb = image_emb.unsqueeze(0).unsqueeze(-1)

        cosine_similarities = cosine_similarity(tag_emb, image_emb).squeeze(-2, -1)
        cosine_similarities = cosine_similarities.tolist()

        return dict((tag.label, cosine_similarities[index]) for tag, index in self._db.tags.ids())

    def shuffled_neighbors(self):
        pre, nxt = self._db.execute(self.SELECT_SHUFFLE_NEIGHBORS, (self.id,)).fetchone()

        return (Image(self._db, pre), Image(self._db, nxt))


class Images:
    INSERT_IMAGE = "INSERT OR IGNORE INTO images (path) VALUES (?)"

    RE_IMAGE_EXT = re.compile(r"(?i)\.(?:png$)|(?:jpe?g$)")

    SELECT_COUNT = "SELECT COUNT(*) FROM images"

    def __init__(self, db):
        self._db = db

    def add_multiple(self, paths: Iterable[str]):
        params = iter((path,) for path in paths)
        cur = self._db.executemany(self.INSERT_IMAGE, params)

        self._db._embeddings.resize((len(self._db.images) + 1, self._db.EMBEDDING_VEC_LEN))

        return cur

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

    def __getitem__(self, id: int):
        return Image(self._db, id)

    def __len__(self):
        (count,) = self._db.execute(self.SELECT_COUNT).fetchone()

        return count
