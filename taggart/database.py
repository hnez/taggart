#!/usr/bin/env python3

import contextlib
import functools as ft
import itertools as it
import operator as op
import os
import re
import sqlite3

import numpy as np
import torch


class TensorFile:
    def __init__(self, path: str, shape: tuple[int], cpu=False, dtype=np.float32):
        self.path = path
        self.shape = shape
        self.cpu = cpu
        self.dtype = dtype

        self._rw = None
        self._ro = None

    def resize(self, shape):
        assert shape[1:] == self.shape[1:]

        if shape[0] > self.shape[0]:
            self.shape = shape
            self._rw = None
            self._ro = None

    def read_write(self):
        if self._rw is None:
            bytes_per_elem = self.dtype(0).itemsize
            elems_per_row = ft.reduce(op.mul, self.shape[1:])
            bytes_per_row = bytes_per_elem * elems_per_row

            min_rows = self.shape[0]
            min_size = min_rows * bytes_per_row

            with contextlib.suppress(FileExistsError), open(self.path, "x") as fd:
                fd.close()

            current_size = os.stat(self.path).st_size

            assert current_size % bytes_per_row == 0

            if current_size < min_size:
                os.truncate(self.path, min_size)
                current_size = min_size

            self.shape = (current_size // bytes_per_row, *self.shape[1:])

            mmap = np.memmap(self.path, self.dtype, "r+", 0, self.shape)
            self._rw = torch.from_numpy(mmap)

        # Invalidate the read only copy of the tensor that may reside
        # on the GPU.
        self._ro = None

        return self._rw

    def read_only(self):
        if self._ro is None:
            rw = self.read_write()
            self._ro = rw if self.cpu else rw.cuda()

        return self._ro


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
        """CREATE TABLE IF NOT EXISTS rating_categories (
            label TEXT NOT NULL UNIQUE
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS image_tags (
            image INTEGER REFERENCES images (rowid),
            tag INTEGER REFERENCES tags (rowid),
            weight REAL NOT NULL DEFAULT 0,
            UNIQUE(image, tag)
        ) STRICT""",
        """CREATE TABLE IF NOT EXISTS image_rating (
            image INTEGER REFERENCES images (rowid),
            category INTEGER REFERENCES rating_categories (rowid),
            rating INTEGER NOT NULL DEFAULT 0,
            UNIQUE(image, category)
        ) STRICT""",
        "CREATE INDEX IF NOT EXISTS image_tags_image ON image_tags (image)",
        "CREATE INDEX IF NOT EXISTS image_tags_tag ON image_tags (tag)",
        "CREATE TEMPORARY TABLE image_shuffle AS SELECT images.rowid AS image FROM images ORDER BY RANDOM()",
        "CREATE INDEX IF NOT EXISTS image_shuffle_rev ON image_shuffle ( image )",
    )

    INSERT_IMAGES = "INSERT OR IGNORE INTO images (path, ts_added) VALUES (?, unixepoch())"
    INSERT_TAG = "INSERT OR IGNORE INTO tags (label) VALUES (?)"
    INSERT_RATING_CATEGORY = "INSERT OR IGNORE INTO rating_categories (label) VALUES (?)"
    INSERT_TAG_IMAGE = """INSERT INTO image_tags (image, tag, weight)
        SELECT :image, rowid, :weight FROM tags WHERE label == :label
        ON CONFLICT DO UPDATE SET weight=:weight"""

    DELETE_TAG_IMAGE = "DELETE FROM image_tags WHERE image == ? AND tag == (SELECT rowid FROM tags WHERE label == ?)"

    SELECT_IMAGE_PATHS = "SELECT path FROM images where rowid == ?"
    SELECT_IMAGE_TAGS = """SELECT label, weight FROM image_tags
        INNER JOIN tags ON image_tags.tag == tags.rowid
        WHERE image_tags.image == ? AND weight != 0"""
    SELECT_IMAGE_COUNT = "SELECT COUNT(*) FROM images"
    SELECT_TAGS = "SELECT DISTINCT label, rowid FROM tags"
    SELECT_TAGS_WITH_OCCURRENCE = """SELECT label, COUNT(image) FROM image_tags
        INNER JOIN tags ON image_tags.tag == tags.rowid
        WHERE weight != 0
        GROUP BY tag"""
    SELECT_RATING_CATEGORIES = "SELECT DISTINCT label, rowid FROM rating_categories"
    SELECT_TAG_ID = "SELECT rowid FROM tags WHERE label == ?"
    SELECT_ALL_TAG_IMAGE_WEIGHTS = "SELECT tag, image, weight FROM image_tags ORDER BY tag"
    SELECT_SHUFFLE_NEIGHBORS = """SELECT
        (SELECT image FROM image_shuffle AS rev WHERE rev.rowid == fwd.rowid - 1),
        (SELECT image FROM image_shuffle AS rev WHERE rev.rowid == fwd.rowid + 1)
        FROM image_shuffle AS fwd WHERE fwd.image == ?"""
    SELECT_IMAGE_RATINGS = """SELECT label, rating FROM image_rating
        INNER JOIN rating_categories ON image_rating.category == rating_categories.rowid
        WHERE image_rating.image == ?"""

    UPDATE_META = """UPDATE images SET
        file_size = :file_size,
        width = :width,
        height = :height,
        exif_camera = :exif_camera,
        exif_ts = :exif_ts,
        broken = :is_broken
      WHERE rowid == :id"""
    UPDATE_HAS_EMBEDDING = "UPDATE images SET has_embedding = TRUE WHERE rowid == ?"
    UPDATE_RATING = """INSERT INTO image_rating (image, category, rating)
        SELECT :image, rowid, :rating FROM rating_categories WHERE label == :label
        ON CONFLICT DO UPDATE SET rating=:rating"""

    RE_IMAGE_EXT = re.compile(r"(?i)\.(?:png$)|(?:jpe?g$)")

    def __init__(self, path: str, cpu=False):
        self._db = sqlite3.connect(path)
        self._tag_embeddings = None
        self._cpu = cpu

        for create in self.CREATE_TABLES:
            self.execute(create)

        embeddings_path = path.removesuffix(".db") + ".embeddings"

        self._embeddings = TensorFile(embeddings_path, (self.image_count() + 1, self.EMBEDDING_VEC_LEN), cpu)

    def _norm(self, a, dim, eps=1e-6):
        norm = torch.norm(a, dim=dim, keepdim=True)
        norm += eps

        return norm

    def _cosine_similarity(self, a, b):
        res = a @ b

        res /= self._norm(a, -1)
        res /= self._norm(b, -2)

        return res

    def _top_k(self, x, top_k):
        top_values, top_indices = torch.topk(x, top_k)

        top_values = top_values.tolist()
        top_indices = top_indices.tolist()

        pairs = tuple(zip(top_indices, top_values))

        return pairs

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

    def execute(self, *kargs, **kwargs):
        with self._db:
            return self._db.execute(*kargs, **kwargs)

    def executemany(self, *kargs, **kwargs):
        with self._db:
            return self._db.executemany(*kargs, **kwargs)

    def add_images(self, paths: tuple[str]):
        params = iter((path,) for path in paths)
        cur = self.executemany(self.INSERT_IMAGES, params)

        self._embeddings.resize((self.image_count() + 1, self.EMBEDDING_VEC_LEN))

        return cur

    def add_images_from_dir(self, dir: str):
        for dirpath, _dirnames, filenames in os.walk(dir):
            paths = tuple(os.path.join(dirpath, name) for name in filenames if self.RE_IMAGE_EXT.search(name))

            if len(paths) == 0:
                continue

            self.add_images(paths)

            print(f"Added {len(paths)} images from {dirpath}")

    def image_shuffle_neighbors(self, id: int):
        return self.execute(self.SELECT_SHUFFLE_NEIGHBORS, (id,)).fetchone()

    def image_path(self, id: int):
        cur = self.execute(self.SELECT_IMAGE_PATHS, (id,))
        (path,) = cur.fetchone()

        return path

    def image_tags(self, id: int):
        return dict(self.execute(self.SELECT_IMAGE_TAGS, (id,)))

    def image_ratings(self, id: int):
        return dict(self.execute(self.SELECT_IMAGE_RATINGS, (id,)))

    def image_set_tag_weight(self, image_id: int, tag: str, weight=1.0):
        with self._db:
            self._db.execute(self.INSERT_TAG, (tag,))
            self._db.execute(self.INSERT_TAG_IMAGE, {"image": image_id, "label": tag, "weight": weight})

        # TODO: update the embeddings right here by adding the image embeddings
        # _if_ the tag was not already on the image before.
        self._tag_embeddings = None

    def image_set_rating(self, image_id: int, category: str, rating: int):
        assert rating in range(6)

        with self._db:
            self._db.execute(self.INSERT_RATING_CATEGORY, (category,))
            self._db.execute(self.UPDATE_RATING, {"image": image_id, "label": category, "rating": rating})

    def image_count(self):
        (count,) = self.execute(self.SELECT_IMAGE_COUNT).fetchone()

        return count

    def tags_similar(self, id):
        embeddings = self._embeddings.read_only()
        image_emb = embeddings[id]
        tag_emb = self.tag_embeddings()

        tag_emb = tag_emb.unsqueeze(-2)
        image_emb = image_emb.unsqueeze(0).unsqueeze(-1)

        cosine_similarities = self._cosine_similarity(tag_emb, image_emb).squeeze(-2, -1)
        cosine_similarities = cosine_similarities.tolist()

        return dict((name, cosine_similarities[index]) for name, index in self.tags().items())

    def images_similar_to_tags(self, tags: list[str], top_k=1000):
        tag_ids = list(self.execute(self.SELECT_TAG_ID, (tag,)).fetchone()[0] for tag in tags)

        embeddings = self._embeddings.read_only()
        tag_embs = self.tag_embeddings()[tag_ids]

        embeddings = embeddings.unsqueeze(1).unsqueeze(2)
        tag_embs = tag_embs.unsqueeze(0).unsqueeze(3)

        cosine_similarities = self._cosine_similarity(embeddings, tag_embs)
        cosine_similarities = cosine_similarities.squeeze(2, 3)
        cosine_similarities = cosine_similarities.prod(1)

        return self._top_k(cosine_similarities, top_k)

    def images_similar(self, image_id: int, top_k=10):
        embeddings = self._embeddings.read_only()
        image_emb = embeddings[image_id]

        embeddings = embeddings.unsqueeze(-2)
        image_emb = image_emb.unsqueeze(0).unsqueeze(-1)

        cosine_similarities = self._cosine_similarity(embeddings, image_emb).squeeze(-2, -1)

        # Suppress _this_ image as it would always be the most similar
        cosine_similarities[image_id] = 0

        return self._top_k(cosine_similarities, top_k)

    def rating_categories(self):
        return dict(self.execute(self.SELECT_RATING_CATEGORIES))

    def tags(self):
        return dict(self.execute(self.SELECT_TAGS))

    def tags_with_occurrence(self):
        return dict(self.execute(self.SELECT_TAGS_WITH_OCCURRENCE))

    def update_meta(
        self, id: int, is_broken: bool, file_size: int, width: int, height: int, exif_camera: str, exif_ts: int
    ):
        self.execute(
            self.UPDATE_META,
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
        embeddings = self._embeddings.read_write()
        embeddings[id] = embedding

        self.execute(self.UPDATE_HAS_EMBEDDING, (id,))


if __name__ == "__main__":
    db = Database("taggart.db")
