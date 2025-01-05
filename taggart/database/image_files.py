class ImageFile:
    SELECT_PATH = "SELECT path FROM image_files WHERE hash == ?"

    def __init__(self, db, hash: bytes):
        self._db = db
        self.hash = hash
        self.hexhash = hash.hex()

    def path(self):
        (path,) = self._db.execute(self.SELECT_PATH, (self.hash,)).fetchone()

        return path


class ImageFiles:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, hash: str | bytes):
        if isinstance(hash, str):
            hash = bytes.fromhex(hash)

        return ImageFile(self._db, hash)
