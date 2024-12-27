#!/usr/bin/env python3

import contextlib
import os
import re
import sqlite3

import numpy as np


class Database:
    EMBEDDING_VEC_LEN = 1152

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
            broken INTEGER NOT NULL DEFAULT 0
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS tags (
            label TEXT NOT NULL UNIQUE
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS image_tags (
            image INTEGER REFERENCES images (rowid),
            tag INTEGER REFERENCES tags (rowid)
        ) STRICT""",
        "CREATE INDEX IF NOT EXISTS image_tags_image ON image_tags (image)",
        "CREATE INDEX IF NOT EXISTS image_tags_tag ON image_tags (tag)",
        "CREATE TEMPORARY TABLE image_shuffle AS SELECT images.rowid AS image FROM images ORDER BY RANDOM()",
        "CREATE INDEX IF NOT EXISTS image_shuffle_rev ON image_shuffle ( image )",
    )

    INSERT_IMAGES = "INSERT OR IGNORE INTO images (path, ts_added) VALUES (?, unixepoch())"
    SELECT_IMAGE_PATHS = "SELECT path FROM images where rowid == ?"
    SELECT_IMAGE_TAGS = """SELECT label FROM image_tags
        INNER JOIN tags ON image_tags.tag == tags.rowid
        WHERE image_tags.image == ?"""
    SELECT_IMAGE_COUNT = "SELECT COUNT(*) FROM images"
    SET_META = """UPDATE images SET
        file_size = :file_size,
        width = :width,
        height = :height,
        exif_camera = :exif_camera,
        exif_ts = :exif_ts,
        broken = :is_broken
      WHERE rowid == :id"""
    SET_HAS_EMBEDDING = "UPDATE images SET has_embedding = TRUE WHERE rowid == ?"

    RE_IMAGE_EXT = re.compile(r"(?i)\.(?:png$)|(?:jpe?g$)")

    def __init__(self, path: str):
        self._db = sqlite3.connect(path)
        self._embeddings_path = path.removesuffix(".db") + ".embeddings"
        self._embeddings_mmap = None

        for create in self.CREATE_TABLES:
            self.execute(create)

    def embeddings_mmap(self):
        if self._embeddings_mmap is None:
            bytes_per_elem = np.float32(0).itemsize
            elems_per_row = self.EMBEDDING_VEC_LEN
            bytes_per_row = bytes_per_elem * elems_per_row

            # `+1` because sqlite3 rowids start at 1 and we just keep the first
            # vector empty in order to not have to add and remove 1 all the time.
            target_rows = self.image_count() + 1
            target_size = target_rows * bytes_per_row

            with contextlib.suppress(FileExistsError), open(self._embeddings_path, "x") as fd:
                fd.close()

            current_size = os.stat(self._embeddings_path).st_size

            assert current_size % bytes_per_row == 0

            if current_size < target_size:
                os.truncate(self._embeddings_path, target_size)
                current_size = target_size

            shape = (current_size // bytes_per_row, elems_per_row)

            self._embeddings_mmap = np.memmap(self._embeddings_path, np.float32, "r+", 0, shape)

        return self._embeddings_mmap

    def execute(self, *kargs, **kwargs):
        with self._db:
            return self._db.execute(*kargs, **kwargs)

    def executemany(self, *kargs, **kwargs):
        with self._db:
            return self._db.executemany(*kargs, **kwargs)

    def add_images(self, paths: tuple[str]):
        self._embeddings_mmap = None

        params = iter((path,) for path in paths)
        cur = self.executemany(self.INSERT_IMAGES, params)

        return cur

    def add_images_from_dir(self, dir: str):
        for dirpath, _dirnames, filenames in os.walk(dir):
            paths = tuple(os.path.join(dirpath, name) for name in filenames if self.RE_IMAGE_EXT.search(name))

            if len(paths) == 0:
                continue

            self.add_images(paths)

            print(f"Added {len(paths)} images from {dirpath}")

    def image_shuffle_neighbors(self, id: int):
        # TODO: replace by some unreadable but elegant SQL magic
        (rowid,) = self.execute("SELECT rowid FROM image_shuffle WHERE image == ?", (id,)).fetchone()
        (prev_id,) = self.execute("SELECT image FROM image_shuffle WHERE rowid == ? - 1", (rowid,)).fetchone()
        (next_id,) = self.execute("SELECT image FROM image_shuffle WHERE rowid == ? + 1", (rowid,)).fetchone()

        return (prev_id, next_id)

    def image_path(self, id: int):
        cur = self.execute(self.SELECT_IMAGE_PATHS, (id,))
        (path,) = cur.fetchone()

        return path

    def image_tags(self, id: int):
        cur = self.execute(self.SELECT_IMAGE_TAGS, (id,))
        tags = tuple(tag for (tag,) in cur)

        return tags

    def image_count(self):
        (count,) = self.execute(self.SELECT_IMAGE_COUNT).fetchone()

        return count

    def image_similar(self, id: int, top_k=10, eps=1e-6):
        embeddings = self.embeddings_mmap()

        embedding = embeddings[id]
        cosine_similarities = embeddings @ embedding

        embeddings_norms = np.linalg.norm(embeddings, axis=-1)
        embeddings_norms += eps

        embedding_norm = embeddings_norms[id]

        # Suppress _this_ image as it would always be the most similar
        cosine_similarities[id] = 0
        cosine_similarities /= embeddings_norms
        cosine_similarities /= embedding_norm

        sorted_indices = np.argsort(cosine_similarities)
        top = sorted_indices[-top_k:]

        pairs = tuple((int(idx), float(cosine_similarities[idx])) for idx in top)

        return pairs

    def update_meta(
        self, id: int, is_broken: bool, file_size: int, width: int, height: int, exif_camera: str, exif_ts: int
    ):
        self.execute(
            self.SET_META,
            {
                "id": id,
                "is_broken": is_broken,
                "file_size": file_size,
                "width": width,
                "height": height,
                "exif_camera": exif_camera,
                "exif_ts": exif_ts,
            },
        )

    def update_embedding(self, id: int, embedding: np.ndarray):
        embeddings = self.embeddings_mmap()
        embeddings[id] = embedding

        self.execute(self.SET_HAS_EMBEDDING, (id,))


if __name__ == "__main__":
    db = Database("taggart.db")
