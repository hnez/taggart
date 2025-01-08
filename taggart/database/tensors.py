#!/usr/bin/env python3

import contextlib
import functools as ft
import json
import operator as op
import os

import numpy as np
import torch

STR_TO_DTYPE = {
    "float32": torch.float32,
}

DTYPE_TO_STR = dict((dt, st) for st, dt in STR_TO_DTYPE.items())


def torch_to_np_dtype(dtype_torch):
    return torch.tensor([], dtype=dtype_torch).numpy().dtype


def mmap_tensor(path, shape, dtype):
    (rows, *row_shape) = shape

    bytes_per_elem = dtype.itemsize
    elems_per_row = ft.reduce(op.mul, row_shape)
    bytes_per_row = bytes_per_elem * elems_per_row

    min_size = rows * bytes_per_row

    with contextlib.suppress(FileExistsError), open(path, "x") as fd:
        fd.close()

    current_size = os.stat(path).st_size

    assert current_size % bytes_per_row == 0

    if current_size < min_size:
        os.truncate(path, min_size)
        current_size = min_size

    shape = (current_size // bytes_per_row, *row_shape)
    np_dtype = torch_to_np_dtype(dtype)

    mmap = np.memmap(path, np_dtype, "r+", 0, shape)
    mmap = torch.from_numpy(mmap)

    return mmap


class Tensor:
    INSERT_ROW = """INSERT OR IGNORE INTO tensor_rows (tensor, tensor_row, image)
        VALUES (
            (SELECT rowid FROM tensors WHERE name == :name),
            (SELECT COALESCE(MAX(tensor_row) + 1, 0) FROM tensor_rows
                INNER JOIN tensors ON tensor_rows.tensor == tensors.rowid
                WHERE name == :name),
            (SELECT rowid FROM images WHERE id == :image_id)
        )"""
    INSERT_ROW_SHAPE = "INSERT OR IGNORE INTO tensors (name, row_shape, dtype) VALUES (?, ?, ?)"

    SELECT_DTYPE = "SELECT dtype FROM tensors WHERE name == ?"
    SELECT_IMAGE = """SELECT images.id FROM tensor_rows
        INNER JOIN tensors ON tensor_rows.tensor == tensors.rowid
        INNER JOIN images ON tensor_rows.image == images.rowid
        WHERE tensors.name == ? AND tensor_rows.tensor_row == ?"""
    SELECT_ROW = """SELECT tensor_row FROM tensor_rows
        INNER JOIN tensors ON tensor_rows.tensor == tensors.rowid
        INNER JOIN images ON tensor_rows.image == images.rowid
        WHERE tensors.name == ? AND images.id == ?"""
    SELECT_ROW_COUNT = """SELECT COALESCE(MAX(tensor_row) + 1, 0) FROM tensor_rows
        INNER JOIN tensors ON tensor_rows.tensor == tensors.rowid
        WHERE name == ?"""
    SELECT_ROW_SHAPE = "SELECT row_shape FROM tensors WHERE name == ?"

    def __init__(self, db, name: str):
        self._db = db
        self.name = name
        self._cpu = None
        self._gpu = None

    def path(self):
        return f"{self._db._base_path}-{self.name}.tensor"

    def dtype(self):
        res = self._db.execute(self.SELECT_DTYPE, (self.name,)).fetchone()

        if res is None:
            return None

        (dtype_str,) = res

        return STR_TO_DTYPE[dtype_str]

    def num_rows(self):
        (num_rows,) = self._db.execute(self.SELECT_ROW_COUNT, (self.name,)).fetchone()
        return num_rows

    def row_shape(self):
        res = self._db.execute(self.SELECT_ROW_SHAPE, (self.name,)).fetchone()
        return torch.Size(json.loads(res[0])) if res is not None else []

    def shape(self):
        num_rows = self.num_rows()
        row_shape = self.row_shape()

        return torch.Size([num_rows]) + row_shape

    def image_to_tensor_row(self, image):
        res = self._db.execute(self.SELECT_ROW, (self.name, image.id)).fetchone()

        if res is None:
            return None

        (idx,) = res

        return idx

    def tensor_row_to_image(self, tensor_row):
        res = self._db.execute(self.SELECT_IMAGE, (self.name, tensor_row)).fetchone()

        if res is None:
            return None

        (id,) = res

        return self._db.images[id]

    def set_image_row(self, image, row: torch.Tensor):
        dtype_str = DTYPE_TO_STR[row.dtype]
        shape_str = json.dumps(row.shape)

        self._db.execute(self.INSERT_ROW_SHAPE, (self.name, shape_str, dtype_str))
        self._db.execute(self.INSERT_ROW, {"name": self.name, "image_id": image.id})

        (idx,) = self._db.execute(self.SELECT_ROW, (self.name, image.id)).fetchone()

        tensor = self.cpu()
        tensor[idx] = row.cpu()

    def cpu(self):
        dtype = self.dtype()

        if dtype is None:
            raise ValueError(f"Tensor {self.name} does not have a dtype associated yet")

        shape = self.shape()

        if shape == [0]:
            return torch.tensor([], dtype=dtype)

        if self._cpu is not None:
            assert self._cpu.shape[1:] == shape[1:]

            if self._cpu.shape[0] < shape[0]:
                self._cpu = None

        if self._cpu is None:
            path = self.path()

            self._cpu = mmap_tensor(path, shape, dtype)

        # Whoever requested this tensor may write to it, making a GPU copy invalid.
        self._gpu = None

        return self._cpu[: shape[0]]

    def gpu(self):
        if self._db._cpu:
            return self.cpu()

        if self._gpu is None:
            self._gpu = self.cpu().cuda()

        return self._gpu


class Tensors:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, name: str):
        return Tensor(self._db, name)
