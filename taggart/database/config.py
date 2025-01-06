class Config:
    INSERT_VALUE = """INSERT INTO config (key, value) VALUES (:key, :value)
        ON CONFLICT DO UPDATE SET value=:value"""

    SELECT_VALUE = "SELECT value FROM config WHERE key == ?"

    def __init__(self, db):
        self._db = db

    def get(self, key, default=None):
        res = self._db.execute(self.SELECT_VALUE, (key,)).fetchone()

        if res is None:
            return default

        return res[0]

    def __contains__(self, key):
        return self.get(key) is not None

    def __getitem__(self, key):
        value = self.get(key)

        if value is None:
            return KeyError(f"No such config key: {key}")

        return value

    def __setitem__(self, key, value):
        self._db.execute(self.INSERT_VALUE, {"key": key, "value": value})
