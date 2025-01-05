#!/usr/bin/env python3

import sqlite3

from ..preview_decoder import PreviewDecoder
from .image_files import ImageFiles
from .images import Images
from .tags import Tags
from .tensor_file import TensorFile


class Database:
    EMBEDDING_VEC_LEN = 1152
    LATENTS_SHAPE = (4, 79, 52)

    CREATE_TABLES = (
        """CREATE TABLE IF NOT EXISTS image_files (
            path TEXT NOT NULL UNIQUE,
            ts_added INT NOT NULL DEFAULT (unixepoch()),
            file_size INT NOT NULL,
            mime_type TEXT NOT NULL,
            hash BLOB NOT NULL UNIQUE,
            width INT NOT NULL,
            height INT NOT NULL
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS exif (
            file INTEGER NOT NULL REFERENCES image_files (rowid),
            tag_id INTEGER NOT NULL,
            value ANY NOT NULL,
            UNIQUE(file, tag_id)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS images (
            file INTEGER NOT NULL REFERENCES image_files (rowid),
            id BLOB NOT NULL DEFAULT (randomblob(8)),
            ts_added INT NOT NULL DEFAULT (unixepoch()),
            rotation REAL NOT NULL DEFAULT 0,
            crop_left INT NOT NULL DEFAULT 0,
            crop_top INT NOT NULL DEFAULT 0,
            width INT NOT NULL,
            height INT NOT NULL,
            UNIQUE(file, rotation, crop_left, crop_top, width, height)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS tags (
            image INTEGER REFERENCES images (rowid),
            tag TEXT,
            weight REAL NOT NULL DEFAULT 0,
            ts_added INT NOT NULL DEFAULT (unixepoch()),
            UNIQUE(image, tag)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS embeddings (
            image INTEGER NOT NULL REFERENCES images (rowid),
            type TEXT NOT NULL,
            tensor_row INTEGER NOT NULL,
            UNIQUE(image, type)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS latents (
            image INTEGER NOT NULL REFERENCES images (rowid),
            type TEXT NOT NULL,
            tensor_row INTEGER NOT NULL,
            UNIQUE(image, type)
        ) STRICT """,
    )

    SELECT_ALL_TAG_TENSOR_ROW_WEIGHTS = """SELECT tag, tensor_row, weight FROM tags
        INNER JOIN images ON tags.image == images.rowid
        INNER JOIN embeddings ON embeddings.image == images.rowid
        WHERE embeddings.type == 'siglip'"""

    def __init__(self, path: str, cpu=False):
        self._db = sqlite3.connect(path)
        self._tag_embeddings = None
        self._cpu = cpu

        self.image_files = ImageFiles(self)
        self.images = Images(self)
        self.tags = Tags(self)

        self.preview_decoder = PreviewDecoder()

        for create in self.CREATE_TABLES:
            self.execute(create)

        base_path = path.removesuffix(".db")

        self._embeddings = TensorFile(f"{base_path}.embeddings", (0, self.EMBEDDING_VEC_LEN), cpu)
        self._latents = TensorFile(f"{base_path}.latents", (0, *self.LATENTS_SHAPE), cpu)

    def execute(self, *kargs, **kwargs):
        with self._db:
            return self._db.execute(*kargs, **kwargs)

    def executemany(self, *kargs, **kwargs):
        with self._db:
            return self._db.executemany(*kargs, **kwargs)

    def tag_embeddings(self):
        if self._tag_embeddings is None:
            embeddings = self._embeddings.read_only()

            tag_embeddings = dict()

            for tag, tensor_row, weight in self.execute(self.SELECT_ALL_TAG_TENSOR_ROW_WEIGHTS):
                weighted = embeddings[tensor_row] * weight

                if tag in tag_embeddings:
                    tag_embeddings[tag] += weighted
                else:
                    tag_embeddings[tag] = weighted

            tag_names, tag_embeddings = zip(*tag_embeddings.items())

            self._tag_embeddings = (tag_names, embeddings)

        return self._tag_embeddings


if __name__ == "__main__":
    db = Database("taggart.db")
