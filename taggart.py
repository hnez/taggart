#!/usr/bin/env python3

import os
import re
import sqlite3

import bottle


class Database:
    CREATE_TABLES = (
        """CREATE TABLE IF NOT EXISTS images (
            path TEXT NOT NULL UNIQUE,
            ts_added INT NOT NULL
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

    INSERT_IMAGES = (
        "INSERT OR IGNORE INTO images (path, ts_added) VALUES (?, unixepoch())"
    )
    SELECT_IMAGE_PATHS = "SELECT path FROM images where rowid == ?"
    SELECT_IMAGE_TAGS = """SELECT label FROM image_tags
        INNER JOIN tags ON image_tags.tag == tags.rowid
        WHERE image_tags.image == ?"""

    RE_IMAGE_EXT = re.compile(r"(?i)\.(?:png$)|(?:jpe?g$)")

    def __init__(self, path: str):
        self.db = sqlite3.connect(path)

        with self.db:
            for create in self.CREATE_TABLES:
                self.db.execute(create)

    def add_images(self, paths: tuple[str]):
        with self.db:
            params = iter((path,) for path in paths)
            cur = self.db.executemany(self.INSERT_IMAGES, params)

        return cur

    def add_images_from_dir(self, dir: str):
        for dirpath, _dirnames, filenames in os.walk(dir):
            paths = tuple(
                os.path.join(dirpath, name)
                for name in filenames
                if self.RE_IMAGE_EXT.search(name)
            )

            if len(paths) == 0:
                continue

            self.add_images(paths)

            print(f"Added {len(paths)} images from {dirpath}")

    def image_shuffle_neighbors(self, id: int):
        # TODO: replace by some unreadable but elegant SQL magic
        (rowid,) = self.db.execute(
            "SELECT rowid FROM image_shuffle WHERE image == ?", (id,)
        ).fetchone()
        (prev_id,) = self.db.execute(
            "SELECT image FROM image_shuffle WHERE rowid == ? - 1", (rowid,)
        ).fetchone()
        (next_id,) = self.db.execute(
            "SELECT image FROM image_shuffle WHERE rowid == ? + 1", (rowid,)
        ).fetchone()

        return (prev_id, next_id)

    def image_path(self, id: int):
        cur = self.db.execute(self.SELECT_IMAGE_PATHS, (id,))
        (path,) = cur.fetchone()

        return path

    def image_tags(self, id: int):
        cur = self.db.execute(self.SELECT_IMAGE_TAGS, (id,))
        tags = tuple(tag for (tag,) in cur)

        return tags

    def image_count(self):
        (count,) = self.db.execute("SELECT COUNT(*) FROM images").fetchone()

        return count


class Taggart:
    def __init__(self, db: Database):
        self.db = db
        self.app = bottle.Bottle()

        self.app.get("/", callback=self.get_index)
        self.app.get("/script.js", callback=self.get_script)
        self.app.get("/style.css", callback=self.get_style)
        self.app.get("/img/<id:int>.json", callback=self.get_image_info)
        self.app.get("/img/<id:int>.jpg", callback=self.get_image_file)

    def run(self):
        self.app.run()

    def get_index(self):
        return bottle.static_file("index.html", "static")

    def get_script(self):
        return bottle.static_file("script.js", "static")

    def get_style(self):
        return bottle.static_file("style.css", "static")

    def get_image_info(self, id: int):
        count = self.db.image_count()
        path = self.db.image_path(id)
        tags = self.db.image_tags(id)
        shuffle_prev, shuffle_next = self.db.image_shuffle_neighbors(id)

        serial_next = id % count + 1
        serial_prev = (count + id - 2) % count + 1

        return {
            "tags": tags,
            "path": path,
            "id": id,
            "shuffle_prev": shuffle_prev,
            "shuffle_next": shuffle_next,
            "serial_prev": serial_prev,
            "serial_next": serial_next,
        }

    def get_image_file(self, id: int):
        path = self.db.image_path(id)

        return bottle.static_file(path, "/")


def main(argv):
    db = Database("taggart.db")

    if argv[1:2] == ["add"]:
        for dir in argv[2:]:
            db.add_images_from_dir(dir)

        return 0

    taggart = Taggart(db)

    taggart.run()


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv))
