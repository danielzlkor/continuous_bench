#!/usr/bin/env python3

"""
This module contains functions for fitting spherical harmonics to diffusion data.
"""
import warnings

import numpy as np
from dipy.reconst.shm import real_sym_sh_basis
from bench import acquisition

Default_LOG_L = True  # default flag to log transform l measures or not.


def summary_names(bvals, b0_threshold=0.05, summarytype='shm', shm_degree=None, cg=False):
    idx_shells, shells = acquisition.ShellParameters.create_shells(bval=bvals, b0_thresh=b0_threshold)
    if summarytype == 'shm':
        names = []
        for sh in shells:
            names.append(f"b{sh.bval:1.1f}_mean")
            if sh.bval >= b0_threshold:
                for degree in np.arange(2, shm_degree + 1, 2):
                    names.append(f"b{sh.bval:1.1f}_l{degree}")
                if cg:
                    names.append(f"b{sh.bval:1.1f}_l2_cg")

    elif summarytype == 'dti':
        names = []
        for sh in shells:
            names.append(f"b{sh.bval:1.1f}_md")
            names.append(f"b{sh.bval:1.1f}_fa")

    return names


def normalised_shms(bvecs, lmax):
    _, phi, theta = cart2spherical(*bvecs.T)
    y, m, l = real_sym_sh_basis(lmax, theta, phi)
    y = y  # /y[0, 0]  # normalisation is required to make the first summary measure represent mean signal
    return y, l


def fit_shm(signal, bval, bvec, shm_degree, log_l=Default_LOG_L):
    """
    Cumputes summary measurements from spherical harmonics fit.
    :param signal: diffusion signal
    :param bval: bvalues
    :param bvec: gradient directions
    :param shm_degree: maximum degree for summary measurements
    :param log_l: flag for taking the logarithm of l measures or not
    :return: summary measurements
    """
    if signal.ndim == 1:
        signal = signal[np.newaxis, :]

    acq = acquisition.Acquisition.from_bval_bvec(bvals=bval, bvecs=bvec)
    sum_meas = list()
    for shell_idx, this_shell in enumerate(acq.shells):
        dir_idx = acq.idx_shells == shell_idx
        bvecs = acq.bvecs[dir_idx]
        shell_signal = signal[..., dir_idx]

        sum_meas.append(shell_signal.mean(axis=-1))

        if this_shell.bval >= acq.b0_threshold:
            y, l = normalised_shms(bvecs, shm_degree)
            if bvecs.shape[0] < y.shape[1]:
                warnings.warn(f'{this_shell.bval} shell directions is fewer than '
                              f'required coefficients to estimate anisotropy.')

            y_inv = np.linalg.pinv(y.T)
            coeffs = shell_signal @ y_inv
            for degree in np.arange(2, shm_degree + 1, 2):
                x = np.power(coeffs[..., l == degree], 2).mean(axis=-1)
                if log_l:
                    x = np.log(x)
                sum_meas.append(x)

    sum_meas = np.stack(sum_meas, axis=-1)
    return sum_meas


def shm_cov(sum_meas, acq, sph_degree, noise_level):
    if sum_meas.ndim == 1:
        sum_meas = sum_meas[np.newaxis, :]

    variances = np.zeros_like(sum_meas)
    s_idx = 0
    for shell_idx, this_shell in enumerate(acq.shells):
        ng = np.sum(acq.idx_shells == shell_idx)
        variances[:, s_idx] = 1 / ng * (noise_level ** 2)
        s_idx += 1
        if this_shell.lmax > 0:
            y, l = normalised_shms(acq.bvecs[acq.idx_shells == shell_idx], this_shell.lmax)
            c = y[0].T @ y[0]
            for degree in np.arange(2, sph_degree + 1, 2):
                f = (noise_level ** 2) / c
                variances[:, s_idx] = f * (2 * sum_meas[:, s_idx] + f) / (2 * degree + 1)
                s_idx += 1

    sigma_n = np.array([np.diag(v) for v in variances])
    return sigma_n


def shm_jacobian(signal, bvecs, lmax=6, max_degree=4):
    assert lmax == 0 or lmax >= max_degree

    y, l = normalised_shms(bvecs, lmax)
    y_inv = np.linalg.pinv(y.T)

    def derivatives(degree):
        if lmax == 0 and degree > 0:
            return None
        else:
            if degree == 0:
                return y_inv[..., l == 0]
            else:
                return 2 * (signal.dot(y_inv[..., l == degree])).dot((y_inv[..., l == degree]).T) / np.sum(l == degree)

    der = np.array([derivatives(deg) for deg in np.arange(0, max_degree + 1, 2)])
    return der


def cart2spherical(x, y, z):
    """
    Converts to spherical coordinates

    :param x: x-component of the vector
    :param y: y-component of the vector
    :param z: z-component of the vector
    :return: tuple with (r, phi, theta)-coordinates
    """
    vectors = np.array([x, y, z])
    r = np.sqrt(np.sum(vectors ** 2, 0))
    theta = np.arccos(vectors[2] / r)
    phi = np.arctan2(vectors[1], vectors[0])
    if vectors.ndim == 1:
        if r == 0:
            phi = 0
            theta = 0
    else:
        phi[r == 0] = 0
        theta[r == 0] = 0
    return r, phi, theta


def nan_mat(shape):
    a = np.empty(shape)
    if len(shape) > 0:
        a[:] = np.NAN
    else:
        a = np.NAN
    return a


def normalise_summaries(y1: np.ndarray, names, dy=None, sigma_n=None, log_l=Default_LOG_L):
    """
    Normalises summary measures for all subjects. (divide by average attenuation)
    :param names: name of summaries, is required for knowing how to normalise
    :param y1: array of summaries for baseline measurements
    :param dy: array of summaries for second group, or the change
    :param sigma_n: array or list of covariance matrices
    :param log_l: flag for logarithm l2
    :return: normalised summaries
    """
    assert len(names) == y1.shape[-1], f'Number of summary measurements doesnt match. ' \
                                       f'Expected {len(names)} measures but got {y1.shape[-1]}.'
    y1 = np.array(y1)
    b0_idx = names.index('b0.0_mean')
    summary_type = [l.split('_')[1] for l in names]
    mean_b0 = np.atleast_1d(y1[..., b0_idx])
    y1_norm = np.zeros_like(y1)

    for smm_idx, l in enumerate(summary_type):
        if l == 'mean':
            y1_norm[..., smm_idx] = y1[..., smm_idx] / mean_b0
        else:
            if log_l:
                y1_norm[..., smm_idx] = y1[..., smm_idx] - 2 * np.log(mean_b0)
            else:
                y1_norm[..., smm_idx] = y1[..., smm_idx] / (mean_b0 ** 2)

    y1_norm = np.delete(y1_norm, b0_idx, axis=-1)
    res = [y1_norm]
    if dy is not None:
        dy = np.array(dy)
        dy_norm = np.zeros_like(dy)
        for smm_idx, l in enumerate(summary_type):
            if l == 'mean':
                dy_norm[..., smm_idx] = dy[..., smm_idx] / mean_b0
            else:
                if log_l:
                    dy_norm[..., smm_idx] = dy[..., smm_idx]
                else:
                    dy_norm[..., smm_idx] = dy[..., smm_idx] / (mean_b0 ** 2)
        res.append(dy_norm)

    if sigma_n is not None:
        sigma_n = np.array(sigma_n)
        sigma_n_norm = sigma_n.copy()
        for smm_idx, l in enumerate(summary_type):
            if l == 'mean':
                sigma_n_norm[..., smm_idx, :] = sigma_n_norm[..., smm_idx, :] / mean_b0[:, np.newaxis]
                sigma_n_norm[..., :, smm_idx] = sigma_n_norm[..., :, smm_idx] / mean_b0[:, np.newaxis]
            else:
                if not log_l:
                    sigma_n_norm[..., smm_idx, :] = sigma_n_norm[..., smm_idx, :] / (mean_b0[:, np.newaxis] ** 2)
                    sigma_n_norm[..., :, smm_idx] = sigma_n_norm[..., :, smm_idx] / (mean_b0[:, np.newaxis] ** 2)

        res.append(sigma_n_norm)

    if dy is None and sigma_n is None:
        return y1_norm
    else:
        return tuple(res)
