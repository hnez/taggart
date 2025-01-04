#!/usr/bin/env python3

import torch


def clamp(x, lower, upper):
    return max(min(x, upper), lower)


def norm(a, dim, eps=1e-6):
    norm = torch.norm(a, dim=dim, keepdim=True)
    norm += eps

    return norm


def cosine_similarity(a, b):
    res = a @ b

    res /= norm(a, -1)
    res /= norm(b, -2)

    return res


def top_k(x, top_k):
    top_values, top_indices = torch.topk(x, top_k)

    top_values = top_values.tolist()
    top_indices = top_indices.tolist()

    return zip(top_indices, top_values)
