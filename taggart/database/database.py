#!/usr/bin/env python3

import itertools as it
import sqlite3

import torch

from ..preview_decoder import PreviewDecoder
from .images import Images
from .tags import Tags
from .tensor_file import TensorFile


class Database:
    EMBEDDING_VEC_LEN = 1152
    LATENTS_SHAPE = (4, 79, 52)

    CREATE_TABLES = (
        """CREATE TABLE IF NOT EXISTS images (
            path TEXT NOT NULL UNIQUE,
            ts_added INT NOT NULL,
            file_size INT,
            width INT,
            height INT,
            exif_camera TEXT,
            exif_ts INT,
            has_embedding INTEGER NOT NULL DEFAULT 0,
            has_latents INTEGER NOT NULL DEFAULT 0,
            broken INTEGER NOT NULL DEFAULT 0
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS tags (
            label TEXT NOT NULL UNIQUE
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS image_tags (
            image INTEGER REFERENCES images (rowid),
            tag INTEGER REFERENCES tags (rowid),
            weight REAL NOT NULL DEFAULT 0,
            UNIQUE(image, tag)
        ) STRICT""",
        "CREATE INDEX IF NOT EXISTS image_tags_image ON image_tags (image)",
        "CREATE INDEX IF NOT EXISTS image_tags_tag ON image_tags (tag)",
        "CREATE TEMPORARY TABLE image_shuffle AS SELECT images.rowid AS image FROM images ORDER BY RANDOM()",
        "CREATE INDEX IF NOT EXISTS image_shuffle_rev ON image_shuffle ( image )",
    )

    SELECT_ALL_TAG_IMAGE_WEIGHTS = "SELECT tag, image, weight FROM image_tags ORDER BY tag"

    def __init__(self, path: str, cpu=False):
        self._db = sqlite3.connect(path)
        self._tag_embeddings = None
        self._cpu = cpu

        self.images = Images(self)
        self.tags = Tags(self)

        self.preview_decoder = PreviewDecoder()

        for create in self.CREATE_TABLES:
            self.execute(create)

        base_path = path.removesuffix(".db")

        self._embeddings = TensorFile(f"{base_path}.embeddings", (len(self.images) + 1, self.EMBEDDING_VEC_LEN), cpu)
        self._latents = TensorFile(f"{base_path}.latents", (len(self.images) + 1, *self.LATENTS_SHAPE), cpu)

    def execute(self, *kargs, **kwargs):
        with self._db:
            return self._db.execute(*kargs, **kwargs)

    def executemany(self, *kargs, **kwargs):
        with self._db:
            return self._db.executemany(*kargs, **kwargs)

    def tag_embeddings(self):
        if self._tag_embeddings is None:
            embeddings = self._embeddings.read_only()

            res = self.execute(self.SELECT_ALL_TAG_IMAGE_WEIGHTS)

            img_and_weight_per_tag = dict((tag, list(tiw)) for tag, tiw in it.groupby(res, lambda p: p[0]))

            tag_dim = max(img_and_weight_per_tag.keys(), default=0) + 1
            emb_dim = self.EMBEDDING_VEC_LEN

            self._tag_embeddings = torch.zeros((tag_dim, emb_dim), device=embeddings.device, dtype=embeddings.dtype)

            for tag, tiw in img_and_weight_per_tag.items():
                image_ids = list(i for _t, i, _w in tiw)
                weights = list(w for _t, _i, w in tiw)

                weights = torch.tensor(weights, device=embeddings.device).unsqueeze(1)

                self._tag_embeddings[tag] = (embeddings[image_ids] * weights).sum(0)

        return self._tag_embeddings


if __name__ == "__main__":
    db = Database("taggart.db")
