#!/usr/bin/env python3

import torch
from diffusers import AutoencoderKL
from torch.nn.functional import interpolate, mse_loss

from .database import Database
from .preview_decoder import PreviewDecoder


def load_decoder():
    print("Loading VAE encoder model ...")
    vae = AutoencoderKL.from_pretrained("stable-diffusion-v1-5/stable-diffusion-v1-5", subfolder="vae")

    decoder = vae.decoder
    post_quant_conv = vae.post_quant_conv

    return decoder, post_quant_conv


def train(db: Database, batch_size=8, max_step=400):
    # Make the model available even when the function is interrupted
    global model, output, target

    model = PreviewDecoder()  # pretrained=False)
    model = model.cuda()
    model.train()

    decoder, post_quant_conv = load_decoder()
    decoder = decoder.cuda()
    post_quant_conv = post_quant_conv.cuda()
    decoder.eval()
    post_quant_conv.eval()

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, 100)

    # Use `.read_write()` to prevent the tensor from being loaded onto the GPU,
    # not because we actually intend to write.
    latents = db._latents.read_write()

    steps = (latents.shape[0] + batch_size - 1) // batch_size

    avg_loss = None

    for step, batch in enumerate(latents.chunk(steps)):
        batch = batch.to(model.device())

        output = model.forward(batch)

        with torch.no_grad():
            target = decoder(post_quant_conv(batch))
            target = interpolate(target, output.shape[-2:])

        loss = mse_loss(output, target)

        if avg_loss is None:
            avg_loss = loss.item()

        avg_loss = 0.9 * avg_loss + 0.1 * loss.item()

        print(f"Step: {step:4} | Loss: {loss.item():1.3f} | Avg Loss: {avg_loss:1.3f}")

        loss.backward()
        optimizer.step()
        optimizer.zero_grad()

        scheduler.step()

        if step > max_step:
            break

    return model
