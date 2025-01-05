#!/usr/bin/env python3

import contextlib
import functools as ft
import operator as op
import os

import numpy as np
import torch


class TensorFile:
    def __init__(self, path: str, shape: tuple[int], cpu=False, dtype=np.float32, grow_increment=32):
        self.path = path
        self.shape = shape
        self.cpu = cpu
        self.dtype = dtype
        self.grow_increment = grow_increment

        self._rw = None
        self._ro = None

    def grow_rows(self, rows):
        rows = (rows + self.grow_increment - 1) // self.grow_increment * self.grow_increment

        if rows > self.shape[0]:
            self.shape = (rows, *self.shape[1:])
            self._rw = None
            self._ro = None

    def grow(self, shape):
        assert shape[1:] == self.shape[1:]

        self.grow_rows(shape[0])

    def read_write(self):
        if self._rw is None:
            bytes_per_elem = self.dtype(0).itemsize
            elems_per_row = ft.reduce(op.mul, self.shape[1:])
            bytes_per_row = bytes_per_elem * elems_per_row

            min_rows = self.shape[0]
            min_size = min_rows * bytes_per_row

            with contextlib.suppress(FileExistsError), open(self.path, "x") as fd:
                fd.close()

            current_size = os.stat(self.path).st_size

            assert current_size % bytes_per_row == 0

            if current_size < min_size:
                os.truncate(self.path, min_size)
                current_size = min_size

            if current_size > 0:
                self.shape = (current_size // bytes_per_row, *self.shape[1:])

                mmap = np.memmap(self.path, self.dtype, "r+", 0, self.shape)
                self._rw = torch.from_numpy(mmap)

        # Invalidate the read only copy of the tensor that may reside
        # on the GPU.
        self._ro = None

        return self._rw

    def read_only(self):
        if self._ro is None:
            rw = self.read_write()
            self._ro = rw if self.cpu else rw.cuda()

        return self._ro
