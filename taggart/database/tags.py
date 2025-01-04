#!/usr/bin/env python3

from .images import Image
from .utils import cosine_similarity, top_k


class TagList:
    SELECT_ID = "SELECT rowid FROM tags WHERE label == ?"

    def __init__(self, db, labels: list[str]):
        self._db = db
        self.labels = labels

    def similar_images(self, count=1000):
        tag_ids = list(self._db.execute(self.SELECT_ID, (label,)).fetchone()[0] for label in self.labels)

        embeddings = self._db._embeddings.read_only()
        tag_embs = self._db.tag_embeddings()[tag_ids]

        embeddings = embeddings.unsqueeze(1).unsqueeze(2)
        tag_embs = tag_embs.unsqueeze(0).unsqueeze(3)

        cosine_similarities = cosine_similarity(embeddings, tag_embs)
        cosine_similarities = cosine_similarities.squeeze(2, 3)
        cosine_similarities = cosine_similarities.prod(1)

        return tuple((Image(self._db, index), value) for index, value in top_k(cosine_similarities, count))


class Tag(TagList):
    def __init__(self, db, label: str):
        super().__init__(db, [label])

        self.label = label


class Tags:
    SELECT_IDS = "SELECT DISTINCT label, rowid FROM tags"
    SELECT_LABELS = "SELECT DISTINCT label FROM tags"
    SELECT_OCCURRENCES = """SELECT label, COUNT(image) FROM image_tags
        INNER JOIN tags ON image_tags.tag == tags.rowid
        WHERE weight != 0
        GROUP BY tag"""

    def __init__(self, db):
        self._db = db
        self._embeddings = None

    @trace
    def embeddings(self):
        if self._embeddings is None:
            tensor_name = self._db.config.get("default-embeddings", "siglip-so400m-patch14-384")

            embeddings = self._db.images.embeddings().gpu()

            tag_embeddings = dict()

            for tag, tensor_row, weight in self._db.execute(self.SELECT_ALL_TAG_TENSOR_ROW_WEIGHTS, (tensor_name,)):
                weighted = embeddings[tensor_row] * weight

                if tag in tag_embeddings:
                    tag_embeddings[tag] += weighted
                else:
                    tag_embeddings[tag] = weighted

            if len(tag_embeddings) > 0:
                tag_names, tag_embeddings = zip(*tag_embeddings.items())

                tag_embeddings = torch.stack(tag_embeddings)

                self._embeddings = (tag_names, tag_embeddings)

        return self._embeddings

    def occurrences(self):
        return iter(
            (Tag(self._db, label), num_occurrences)
            for label, num_occurrences in self._db.execute(self.SELECT_OCCURRENCES)
        )

    def ids(self):
        return iter((Tag(self._db, label), id) for label, id in self._db.execute(self.SELECT_IDS))

    def __getitem__(self, labels: list[str] | tuple[str] | str):
        if isinstance(labels, list):
            return TagList(self._db, tuple(labels))
        elif isinstance(labels, tuple):
            return TagList(self._db, labels)
        else:
            return Tag(self._db, labels)

    def __iter__(self):
        return iter(Tag(self._db, label) for (label,) in self._db.execute(self.SELECT_LABELS))
