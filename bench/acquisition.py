#!/usr/bin/env python3

"""
This module contains functions to simulate diffusion signals using diffusion_models.py and compute summary measures
using summary_measures.py
"""
import argparse
from dataclasses import dataclass, fields
import numpy as np
from typing import List, Optional, Sequence

b0_thresh = 0.1


@dataclass
class ShellParameters:
    """
    Acquisition parameters for a single shell of diffusion MRI data
    """
    bval: Optional[float] = None
    qval: Optional[float] = None
    diffusion_time: Optional[float] = None
    gradient_duration: Optional[float] = None
    TE: Optional[float] = None
    TR: Optional[float] = None
    TI: Optional[float] = None
    b_delta: float = 1.
    b_eta: float = 0.
    lmax: Optional[int] = 8
    anisotropy: Optional[bool] = False

    def __post_init__(self):
        if self.bval is None:
            self.bval = self.qval ** 2 * self.diffusion_time
        if self.no_anisotropy:
            self.lmax = 0

    @property
    def no_anisotropy(self):
        return (self.anisotropy is False) or (self.b_delta == 0)

    @classmethod
    def add_to_parser(cls, parser: argparse.ArgumentParser):
        """
        Adds the acquisition parameters to the given parsers

        :param parser: parser that will be updated with a new group of acquisition parameter arguments
        """
        group = parser.add_argument_group(
            "Acquisition parameters",
            "Text files or floats defining the acquisition parameters of each volume. " +
            "Text files should have a single row or single column and contain a single value per volume.",
        )
        for var in fields(cls):
            group.add_argument('--' + var.name)

    @classmethod
    def from_parser_args(cls, args):
        """
        Creates shells based on command line arguments.

        Extracts the command line arguments added by :meth:`add_to_parser`

        :param args: Namespace with acquisition parameter arguments from the command line
        :return: Tuple with:

            - 1D array with the index of the shell for each volume
            - List with the individual shells
        """
        to_shell = {}
        for var in fields(cls):
            if getattr(args, var.name, None) is None:
                continue
            try:
                to_shell[var.name] = float(getattr(args, var.name))
            except ValueError:
                to_shell[var.name] = np.genfromtxt(getattr(args, var.name))
        return cls.create_shells(**to_shell)

    @classmethod
    def create_shells(cls, **parameters):
        """
        Creates multiple shells from a sequence of parameters

        :param parameters: floats or sequence with values of the acquisition parameters for every volume
        :return: Tuple with:

            - 1D array with the index of the shell for each volume
            - List with the individual shells
        """
        nparams = None
        ref = None
        for name, params in parameters.items():
            if np.array(params).size == 1:
                continue
            if nparams is None:
                nparams = len(params)
                ref = name
            elif nparams != len(params):
                raise ValueError("Found inconsistent number of volumes: " +
                                 f"{nparams} for {ref} and {len(params)} for {name}")

        if nparams is None:
            raise ValueError("None of the parameters vary between volumes, so can not define shells")

        if parameters['bval'].max() > 100:
            parameters['bval'] /= 1e3
            parameters['bval'] = np.round(parameters['bval'], 1)

        parameters['bval'][parameters['bval'] < b0_thresh] = 0

        within_range = np.ones((nparams, nparams), dtype='bool')
        for name, params in parameters.items():
            arr = np.array(params)
            if arr.size == 1:
                continue
            if name == 'bval':
                within_range &= abs(arr[:, None] - arr[None, :]) < b0_thresh
            else:
                within_range &= arr[:, None] == arr[None, :]

        indices = -np.ones(nparams, dtype='int')
        while (indices == -1).any():
            nshell = 0
            new_shell = np.zeros(within_range.shape[0], dtype='bool')
            new_shell[np.where(indices == -1)[0][0]] = True
            while nshell != new_shell.sum():
                nshell = new_shell.sum()
                new_shell = within_range[new_shell, :].any(0)
            indices[new_shell] = max(indices) + 1

        shells = []
        for idx in np.unique(indices):
            use = idx == indices
            shell_params = {}
            for name, params in parameters.items():
                if np.array(params).size == 1:
                    shell_params[name] = params
                else:
                    shell_params[name] = np.median(np.array(params)[use])
            shells.append(cls(**shell_params))
        return indices, shells


def to_string(shells: Sequence[ShellParameters]):
    """
    Writes the shells as a table

    :param shells: individual shells
    """
    used_fields = set()
    for field in fields(ShellParameters):
        for shell in shells:
            if getattr(shell, field.name) is not None:
                used_fields.add(field.name)
                break
    used_fields = sorted(used_fields)

    len_column = max(max(len(name) for name in used_fields) + 2, 8)

    fmt = '{{:{}s}}'.format(len_column)
    res = "|".join(fmt.format(name) for name in used_fields)
    res = res + '\n' + '-' * len(res)

    fmt = '{{:{}f}}'.format(len_column)
    for shell in shells:
        parts = []
        for name in used_fields:
            value = getattr(shell, name)
            if value is None:
                parts.append(' ' * len_column)
            else:
                parts.append(fmt.format(value))
        res = res + '\n' + '|'.join(parts)
    return res


@dataclass
class Acquisition:
    """
    Class that contains acquisition protocol.
    """
    shells: List[ShellParameters]
    idx_shells: np.ndarray
    bvals: np.array
    bvecs: np.ndarray
    name: str
    b0_threshold: float = b0_thresh

    @classmethod
    def load(cls, name, acq_path, b0_threshold=b0_thresh):
        """
        reads acquisition protocol parameters from bval and bvec text files
        :param name: name of acq protocol
        :param acq_path: path to acquisition files
        :param b0_threshold: threshold to compute anisotropy measures.
        :return acq: an acquisition object containing shells, shell indices of
        each measurement, and gradient directions
        """

        bvec_path = acq_path + '/' + name + '/bvecs'
        bval_path = acq_path + '/' + name + '/bvals'
        args = argparse.Namespace(bvec=bvec_path, bval=bval_path)

        idx_shells, shells = ShellParameters.from_parser_args(args)
        bvals = read_bvals(args.bval)
        bvecs = np.genfromtxt(args.bvec).T

        print('loaded input shells:')
        print(to_string(shells))
        print('')
        return cls(shells, idx_shells, bvals, bvecs, name, b0_threshold)

    @classmethod
    def from_bval_bvec(cls, bval_path, bvec_path, b0_threshold=b0_thresh):
        bvecs = read_bvecs(bvec_path)
        bvals = read_bvals(bval_path)
        idx_shells, shells = ShellParameters.create_shells(bval=bvals)
        return cls(shells, idx_shells, bvals, bvecs, ' ', b0_threshold)

    @classmethod
    def generate(cls, n_b0=10, n_dir=64, b=(1, 2, 3)):
        """
        Generates diffusion protocol.
        :param n_b0: number of b0 images
        :param n_dir: number of directions per shell
        :param b: bvalues for each shell (tuple)
        :return: acquisition class.
        """
        bvals = np.zeros(n_b0)
        bvecs = fibonacci_sphere(n_b0)

        for b_ in b:
            bvals = np.concatenate([bvals, np.ones(n_dir) * b_])
            bvecs = np.concatenate([bvecs, fibonacci_sphere(n_dir)])
        idx_shells, shells = ShellParameters.create_shells(bval=bvals)
        return cls(shells, idx_shells, bvals, bvecs, ' ', b0_thresh)


def read_bvals(fname, b0thresh=b0_thresh, maxb=100, scale=1000):
    bvals = np.genfromtxt(fname)
    if bvals.max() > maxb:
        bvals /= scale

    bvals[bvals < b0thresh] = 0
    bvals = np.around(bvals, 2)
    return bvals


def read_bvecs(fname):
    bvecs = np.genfromtxt(fname)
    if bvecs.shape[1] > bvecs.shape[0]:
        bvecs = bvecs.T

    return bvecs


def fibonacci_sphere(samples=1):
    """
    Creates N points uniformly-ish distributed on the sphere

    Args:
        samples : int
    """
    phi = np.pi * (3. - np.sqrt(5.))  # golden angle in radians

    i = np.arange(samples)
    y = 1 - 2. * (i / float(samples - 1))
    r = np.sqrt(1 - y * y)
    t = phi * i
    x = np.cos(t) * r
    z = np.sin(t) * r

    points = np.asarray([x, y, z]).T

    return points
