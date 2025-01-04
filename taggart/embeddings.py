#!/usr/bin/env python3

import contextlib
import os
import sys
from datetime import datetime

import PIL
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoProcessor

from .database import Database


class ImagesToEmbedDataset(Dataset):
    CREATE_TMP_TABLE = """CREATE TEMPORARY TABLE images_to_embed AS
        SELECT images.rowid AS image
        FROM images
        WHERE has_embedding == FALSE AND broken == FALSE"""
    DROP_TMP_TABLE = "DROP TABLE images_to_embed"
    SELECT_COUNT = "SELECT COUNT(*) FROM images_to_embed"
    SELECT_IMAGE = """SELECT images.rowid, path FROM images_to_embed
        INNER JOIN images ON images_to_embed.image == images.rowid
        WHERE images_to_embed.rowid == (? + 1)"""

    def __init__(self, db: Database, image_processor: AutoProcessor):
        self.db = db
        self.image_processor = image_processor

        self.db.execute(self.CREATE_TMP_TABLE)

    def __getitem__(self, index: int):
        image_id, path = self.db.execute(self.SELECT_IMAGE, (index,)).fetchone()

        file_size = None
        broken = True
        width = None
        height = None
        exif_camera = None
        exif_ts = None

        with contextlib.suppress(FileNotFoundError):
            file_size = os.stat(path).st_size

        try:
            image = PIL.Image.open(path)
            image = PIL.ImageOps.exif_transpose(image)
            image = image.convert("RGB")

            broken = False
            width = image.width
            height = image.height

        except Exception as e:
            print(f'Failed to load "{path}":', e, file=sys.stderr, flush=True)

            image = PIL.Image.new("RGB", (1, 1))

        inputs = self.image_processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].squeeze(0)

        with contextlib.suppress(KeyError):
            exif = image.getexif()
            exif_camera = exif[PIL.ExifTags.Base.Model]

        with contextlib.suppress(KeyError, ValueError):
            exif = image.getexif()
            exif_ts_raw = exif[PIL.ExifTags.Base.DateTime]
            exif_ts_dt = datetime.strptime(exif_ts_raw, "%Y:%m:%d %H:%M:%S")
            exif_ts = exif_ts_dt.timestamp()

        self.db.update_meta(image_id, broken, file_size, width, height, exif_camera, exif_ts)

        return (image_id, pixel_values)

    def __len__(self):
        (count,) = self.db.execute(self.SELECT_COUNT).fetchone()

        return count

    def __del__(self):
        self.db.execute(self.DROP_TMP_TABLE)


def load_vision_model():
    print("Loading vision model ...")
    model = AutoModel.from_pretrained("google/siglip-so400m-patch14-384")
    vision_model = model.vision_model

    return vision_model


def load_image_processor():
    print("Loading image processor ...")
    processor = AutoProcessor.from_pretrained("google/siglip-so400m-patch14-384")
    image_processor = processor.image_processor

    return image_processor


@torch.no_grad
def add_embeddings(db: Database, batch_size: int, num_workers: int):
    image_processor = load_image_processor()
    dataset = ImagesToEmbedDataset(db, image_processor)
    dataloader = DataLoader(dataset, batch_size=batch_size, num_workers=num_workers)

    vision_model = load_vision_model()
    vision_model.eval()

    if not db._cpu:
        vision_model = vision_model.cuda()

    num_batches = len(dataloader)

    start_time = datetime.now()

    for batch, (image_ids, pixel_values) in enumerate(dataloader):
        if not db._cpu:
            pixel_values = pixel_values.cuda()

        output = vision_model.forward(pixel_values)
        embeddings = output["pooler_output"]

        for id, emb in zip(image_ids, embeddings):
            id = id.item()
            db.update_embedding(id, emb)

        done_ratio = (batch + 1) / num_batches
        done_percentage = done_ratio * 100

        current_time = datetime.now()
        elapsed_time = current_time - start_time
        end_time = start_time + elapsed_time / done_ratio
        end_time_str = end_time.strftime("%d.%m.%Y %H:%M:%S")

        print(
            f"\33[2K\r{batch} / {num_batches} = {done_percentage:3.2f}% Completion: {end_time_str}", end="", flush=True
        )
