#!/usr/bin/env python3

import sqlite3

from ..preview_decoder import PreviewDecoder
from .config import Config
from .image_files import ImageFiles
from .images import Images
from .tags import Tags
from .tensors import Tensors
from .tracing import Tracer


class Database:
    CREATE_TABLES = (
        """CREATE TABLE IF NOT EXISTS config (
            rowid INTEGER PRIMARY KEY,
            key TEXT NOT NULL UNIQUE,
            value ANY NOT NULL
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS image_files (
            rowid INTEGER PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            ts_added INT NOT NULL DEFAULT (unixepoch()),
            file_size INT NOT NULL,
            mime_type TEXT NOT NULL,
            hash BLOB NOT NULL UNIQUE,
            width INT NOT NULL,
            height INT NOT NULL
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS exif (
            rowid INTEGER PRIMARY KEY,
            file INTEGER NOT NULL REFERENCES image_files (rowid),
            tag_id INTEGER NOT NULL,
            value ANY NOT NULL,
            UNIQUE(file, tag_id)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS images (
            rowid INTEGER PRIMARY KEY,
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
            rowid INTEGER PRIMARY KEY,
            image INTEGER REFERENCES images (rowid),
            tag TEXT,
            weight REAL NOT NULL DEFAULT 0,
            ts_added INT NOT NULL DEFAULT (unixepoch()),
            UNIQUE(image, tag)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS tensors (
            rowid INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            row_shape TEXT NOT NULL,
            dtype TEXT NOT NULL
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS tensor_rows (
            rowid INTEGER PRIMARY KEY,
            tensor INTEGER NOT NULL REFERENCES tensors (rowid),
            image INTEGER NOT NULL REFERENCES images (rowid),
            tensor_row INTEGER NOT NULL,
            UNIQUE(tensor, image)
        ) STRICT """,
    )

    CREATE_INDICES = (
        "CREATE INDEX IF NOT EXISTS config_key ON config (key)",
        "CREATE INDEX IF NOT EXISTS image_files_path ON image_files (path)",
        "CREATE INDEX IF NOT EXISTS image_files_hash ON image_files (hash)",
        "CREATE INDEX IF NOT EXISTS image_id ON images (id)",
        "CREATE INDEX IF NOT EXISTS tags_tag ON tags (tag)",
        "CREATE INDEX IF NOT EXISTS tags_image ON tags (image)",
        "CREATE INDEX IF NOT EXISTS tensors_name ON tensors (name)",
        "CREATE INDEX IF NOT EXISTS tensor_rows_tensor ON tensor_rows (tensor)",
        "CREATE INDEX IF NOT EXISTS tensor_rows_image ON tensor_rows (image)",
        "CREATE INDEX IF NOT EXISTS tensor_rows_tensor_image ON tensor_rows (tensor, image)",
        "CREATE INDEX IF NOT EXISTS tensor_rows_tensor_row ON tensor_rows (tensor_row)",
    )

    def __init__(self, path: str, cpu=False):
        self._db = sqlite3.connect(path)
        self._cpu = cpu
        self._base_path = path.removesuffix(".db")

        self.tracer = Tracer()

        self.config = Config(self)
        self.image_files = ImageFiles(self)
        self.images = Images(self)
        self.tags = Tags(self)
        self.tensors = Tensors(self)

        self.preview_decoder = PreviewDecoder()

        for create in self.CREATE_TABLES + self.CREATE_INDICES:
            self.execute(create)

        self.execute("PRAGMA optimize")

    def execute(self, sql, *kargs, **kwargs):
        with self._db, self.tracer.start(sql):
            return self._db.execute(sql, *kargs, **kwargs)

    def executemany(self, sql, *kargs, **kwargs):
        with self._db, self.tracer.start(sql):
            return self._db.executemany(sql, *kargs, **kwargs)


if __name__ == "__main__":
    db = Database("taggart.db")
