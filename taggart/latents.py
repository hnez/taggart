#!/usr/bin/env python3

from datetime import datetime

import torch
from diffusers import AutoencoderKL
from diffusers.image_processor import VaeImageProcessor
from torch.utils.data import DataLoader

from .database import Database
from .embeddings import ImagesToEmbedDataset


class ImagesToVaeDataset(ImagesToEmbedDataset):
    CREATE_TMP_TABLE = """CREATE TEMPORARY TABLE images_to_vae AS
        SELECT images.rowid AS image
        FROM images
        WHERE has_latents == FALSE AND broken == FALSE"""

    DROP_TMP_TABLE = "DROP TABLE images_to_vae"

    SELECT_COUNT = "SELECT COUNT(*) FROM images_to_vae"
    SELECT_IMAGE = "SELECT image FROM images_to_vae WHERE rowid == (? + 1)"


def load_image_processor(width, height):
    vae_processor = VaeImageProcessor()

    def image_processor(images, return_tensors):
        bounding_box = (
            max(width, height * images.width // max(1, images.height) + 1),
            max(height, width * images.height // max(1, images.width) + 1),
        )

        images.thumbnail(bounding_box)

        if images.width < width:
            images = images.resize((width, width * images.height // max(1, images.width)))

        if images.height < height:
            images = images.resize((height * images.width // max(1, images.height), height))

        crop = (
            max(0, (images.width - width) / 2),
            max(0, (images.height - height) / 2),
            min(images.width, (images.width + width) / 2),
            min(images.height, (images.height + height) / 2),
        )

        images = images.crop(crop)

        return {"pixel_values": vae_processor.preprocess(images)}

    return image_processor


def load_encoder():
    print("Loading VAE encoder model ...")
    vae = AutoencoderKL.from_pretrained("stable-diffusion-v1-5/stable-diffusion-v1-5", subfolder="vae")

    encoder = vae.encoder
    quant_conv = vae.quant_conv

    return encoder, quant_conv


@torch.no_grad
def add_latents(db: Database, batch_size: int, num_workers):
    width = db.LATENTS_SHAPE[2] * 8
    height = db.LATENTS_SHAPE[1] * 8

    image_processor = load_image_processor(width, height)
    dataset = ImagesToVaeDataset(db, image_processor)
    dataloader = DataLoader(dataset, batch_size=batch_size, num_workers=num_workers)

    encoder, quant_conv = load_encoder()
    encoder.eval()
    quant_conv.eval()

    if not db._cpu:
        encoder = encoder.cuda()
        quant_conv = quant_conv.cuda()

    num_batches = len(dataloader)

    start_time = datetime.now()

    for batch, (image_ids, pixel_values) in enumerate(dataloader):
        if not db._cpu:
            pixel_values = pixel_values.cuda()

        latents = encoder.forward(pixel_values)
        latents = quant_conv(latents)
        latents = latents[:, :4]

        for id, lat in zip(image_ids, latents):
            id = id.item()
            db.images[id].set_latent(lat)

        done_ratio = (batch + 1) / num_batches
        done_percentage = done_ratio * 100

        current_time = datetime.now()
        elapsed_time = current_time - start_time
        end_time = start_time + elapsed_time / done_ratio
        end_time_str = end_time.strftime("%d.%m.%Y %H:%M:%S")

        print(
            f"\33[2K\r{batch + 1} / {num_batches} = {done_percentage:3.2f}% Completion: {end_time_str}",
            end="",
            flush=True,
        )
