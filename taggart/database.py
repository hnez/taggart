#!/usr/bin/env python3

import contextlib
import importlib
import itertools as it
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

    def __init__(self, path: str, use_torch=False):
        self._db = sqlite3.connect(path)
        self._embeddings_path = path.removesuffix(".db") + ".embeddings"
        self._embeddings_mmap = None
        self._tag_embeddings = None
        self._torch = None

        if use_torch:
            try:
                self._torch = importlib.import_module("torch")
            except ModuleNotFoundError:
                print("Failed to import torch. Continuing without it.")

        for create in self.CREATE_TABLES:
            self.execute(create)

    def _zeros(self, shape):
        if self._torch is not None:
            return self._torch.zeros(shape, device="cuda")
        else:
            return np.zeros(shape)

    def _tensor(self, x: list):
        if self._torch is not None:
            return self._torch.tensor(x, device="cuda")
        else:
            return np.ndarray(x)

    def _norm(self, a, dim, eps=1e-6):
        norm = (
            np.linalg.norm(a, axis=dim, keepdim=True)
            if self._torch is None
            else self._torch.norm(a, dim=dim, keepdim=True)
        )
        norm += eps

        return norm

    def _cosine_similarity(self, a, b):
        res = a @ b

        res /= self._norm(a, -1)
        res /= self._norm(b, -2)

        return res

    def _top_k(self, x, top_k):
        if self._torch is not None:
            top_values, top_indices = self._torch.topk(x, top_k)
        else:
            sorted_indices = np.argsort(x)
            top_indices = sorted_indices[-top_k:]
            top_values = x[top_indices]

        top_values = top_values.tolist()
        top_indices = top_indices.tolist()

        pairs = tuple(zip(top_indices, top_values))

        return pairs

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

            mmap = np.memmap(self._embeddings_path, np.float32, "r+", 0, shape)

            if self._torch is not None:
                mmap = self._torch.from_numpy(mmap).cuda()

            self._embeddings_mmap = mmap

        return self._embeddings_mmap

    def tag_embeddings(self):
        if self._tag_embeddings is None:
            embeddings = self.embeddings_mmap()

            res = self.execute(self.SELECT_ALL_TAG_IMAGE_WEIGHTS)

            img_and_weight_per_tag = dict((tag, list(tiw)) for tag, tiw in it.groupby(res, lambda p: p[0]))

            tag_dim = max(img_and_weight_per_tag.keys(), default=0) + 1
            emb_dim = self.EMBEDDING_VEC_LEN

            self._tag_embeddings = self._zeros((tag_dim, emb_dim))

            for tag, tiw in img_and_weight_per_tag.items():
                image_ids = list(i for _t, i, _w in tiw)
                weights = list(w for _t, _i, w in tiw)

                weights = self._tensor(weights).unsqueeze(1)

                self._tag_embeddings[tag] = (embeddings[image_ids] * weights).sum(0)

        return self._tag_embeddings

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
        embeddings = self.embeddings_mmap()
        image_emb = embeddings[id]
        tag_emb = self.tag_embeddings()

        tag_emb = tag_emb.unsqueeze(-2)
        image_emb = image_emb.unsqueeze(0).unsqueeze(-1)

        cosine_similarities = self._cosine_similarity(tag_emb, image_emb).squeeze(-2, -1)
        cosine_similarities = cosine_similarities.tolist()

        return dict((name, cosine_similarities[index]) for name, index in self.tags().items())

    def images_similar_to_tags(self, tags: list[str], top_k=1000):
        tag_ids = list(self.execute(self.SELECT_TAG_ID, (tag,)).fetchone()[0] for tag in tags)

        embeddings = self.embeddings_mmap()
        tag_embs = self.tag_embeddings()[tag_ids]

        embeddings = embeddings.unsqueeze(1).unsqueeze(2)
        tag_embs = tag_embs.unsqueeze(0).unsqueeze(3)

        cosine_similarities = self._cosine_similarity(embeddings, tag_embs)
        cosine_similarities = cosine_similarities.squeeze(2, 3)
        cosine_similarities = cosine_similarities.prod(1)

        return self._top_k(cosine_similarities, top_k)

    def images_similar(self, image_id: int, top_k=10):
        embeddings = self.embeddings_mmap()
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
        embeddings = self.embeddings_mmap()
        embeddings[id] = embedding

        self.execute(self.UPDATE_HAS_EMBEDDING, (id,))


if __name__ == "__main__":
    db = Database("taggart.db", use_torch=True)
