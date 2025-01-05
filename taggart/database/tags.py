#!/usr/bin/env python3

from .images import Image
from .utils import cosine_similarity, top_k


class TagList:
    def __init__(self, db, tags: list[str]):
        self._db = db
        self.tags = tags

    def similar_images(self, count=1000):
        embeddings = self._db._embeddings.read_only()
        tag_names, tag_embs = self._db.tag_embeddings()

        tag_ids = list(i for i, n in enumerate(tag_names) if n in self.tags)

        tag_embs = tag_embs[tag_ids]

        embeddings = embeddings.unsqueeze(1).unsqueeze(2)
        tag_embs = tag_embs.unsqueeze(0).unsqueeze(3)

        cosine_similarities = cosine_similarity(embeddings, tag_embs)
        cosine_similarities = cosine_similarities.squeeze(2, 3)
        cosine_similarities = cosine_similarities.prod(1)

        res = list()

        for index, value in top_k(cosine_similarities, count):
            image = Image.from_tensor_row(self._db, index)

            if image is None:
                continue

            res.append((image, value))

        return tuple(res)


class Tag(TagList):
    def __init__(self, db, tag: str):
        super().__init__(db, [tag])

        self.tag = tag


class Tags:
    SELECT_TAGS = "SELECT DISTINCT tag FROM tags"
    SELECT_OCCURRENCES = """SELECT tag, COUNT(image) FROM tags WHERE weight != 0 GROUP BY tag"""

    def __init__(self, db):
        self._db = db

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
            (Tag(self._db, tag), num_occurrences) for tag, num_occurrences in self._db.execute(self.SELECT_OCCURRENCES)
        )

    def __getitem__(self, tags: list[str] | tuple[str] | str):
        if isinstance(tags, list):
            return TagList(self._db, tuple(tags))
        elif isinstance(tags, tuple):
            return TagList(self._db, tags)
        else:
            return Tag(self._db, tags)

    def __iter__(self):
        return iter(Tag(self._db, tag) for (tag,) in self._db.execute(self.SELECT_TAGS))
