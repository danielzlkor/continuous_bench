from bench import diffusion_models as dm, summary_measures, user_interface, acquisition, change_model
import numpy as np
import os
from scipy import optimize
from fsl.data.image import Image
import glob
import fsl.utils.fslsub as fslsub
from fsl.utils.run import run
import sys
from fsl.data.featdesign import loadDesignMat
from warnings import warn
import scipy.stats as st
from typing import Union, Callable, List
from progressbar import ProgressBar
import argparse


def log_likelihood(params, model, acq, sph_degree, y, noise_level):
    expected = np.squeeze(model(acq, sph_degree, 0, **params))
    sigma_n = summary_measures.shm_cov(expected, acq, sph_degree, noise_level)
    return change_model.log_mvnpdf(mean=expected, cov=sigma_n, x=np.squeeze(y))


def log_prior(params, priors):
    return np.sum([np.log(priors[k].pdf(params[k]))
                   for k in params.keys()])


def log_posterior(params, priors, model, acq, sph_degree, y, sigma_n):
    param_dict = {k: v for k, v in zip(priors.keys(), params)}
    return -(log_likelihood(param_dict, model, acq, sph_degree, y, sigma_n)
             + log_prior(param_dict, priors))


def map_fit(model: Callable, acq: acquisition.Acquisition, sph_degree: int,
            priors: dict, y: np.ndarray, noise_level):
    x0 = np.array([v.mean() for v in priors.values()])
    bounds = [v.interval(1 - 1e-6) for v in priors.values()]
    p = optimize.minimize(log_posterior,
                          args=(priors, model, acq, sph_degree, y, noise_level),
                          x0=x0,  bounds=bounds, options={'disp': False})

    return p.x


def fit_model(diffusion_sig, forward_model_name, bvals, bvecs, sph_degree):
    forward_model_name = forward_model_name.lower()
    available_models = list(dm.prior_distributions.keys())
    funcdict = {name: f for (name, f) in dm.__dict__.items() if name in available_models}

    if forward_model_name in available_models:
        priors = dm.prior_distributions[forward_model_name]
        func = dm.bench_decorator(funcdict[forward_model_name])
    else:
        raise ValueError('Forward model is not available in the library.')

    idx_shells, shells = acquisition.ShellParameters.create_shells(bval=bvals)
    acq = acquisition.Acquisition(shells, idx_shells, bvecs)
    y, sigma_n = summary_measures.fit_shm(diffusion_sig, acq, sph_degree, esitmate_cov=True)
    pbar = ProgressBar()
    pe = np.zeros((y.shape[0], len(priors)))
    for i in pbar(range(y.shape[0])):
        pe[i] = map_fit(func, acq, sph_degree, priors, y[i], sigma_n[i])

    return pe


def read_pes(pe_dir, mask_add):
    mask_img = Image(mask_add)
    n_subj = len(glob.glob(pe_dir + '/subj_*.nii.gz'))
    pes = list()
    for subj_idx in range(n_subj):
        f = f'{pe_dir}/subj_{subj_idx}.nii.gz'
        pes.append(Image(f).data[mask_img.data > 0, :])

    print(f'loaded summaries from {n_subj} subjects')
    pes = np.array(pes)
    invalids = np.any(np.isnan(pes), axis=(0, 2))
    pes = pes[:, invalids == 0, :]
    if invalids.sum() > 0:
        warn(f'{invalids.sum()} voxels are dropped because of lying outside of brain mask in some subjects.')
    return pes, invalids


def pipeline(argv=None):
    args = inference_parse_args(argv)
    os.makedirs(args.output, exist_ok=True)
    pe_dir = f'{args.output}/pes/{args.model}'
    os.makedirs(pe_dir, exist_ok=True)

    if len(glob.glob(pe_dir + '/subj_*.nii.gz')) < len(args.data):
        py_file_path = os.path.realpath(__file__)
        task_list = list()
        for subj_idx, (x, d, bv) in enumerate(zip(args.xfm, args.data, args.bvecs)):
            task_list.append(
                f'python3 {py_file_path} {subj_idx} {d} {x} {bv} {args.bval} {args.mask} {args.model} {pe_dir}')
        # uncomment to debug:
        parse_args_and_fit(f'{py_file_path} {subj_idx} {d} {x} {bv} {args.bval} {args.mask} {args.model} {pe_dir}'.split())

        if 'SGE_ROOT' in os.environ.keys():
            print('Submitting jobs to SGE ...')
            with open(f'{args.output}/tasklist.txt', 'w') as f:
                for t in task_list:
                    f.write("%s\n" % t)
                f.close()

                job_id = run(f'fsl_sub -t {args.output}/tasklist.txt '
                             f'-q short.q -N bench_inversion -l {pe_dir}/log -s openmp,2')
                print('jobs submitted to SGE ...')
                fslsub.hold(job_id)
        else:
            os.system('; '.join(task_list))

        if len(glob.glob(pe_dir + '/subj_*.nii.gz')) == len(args.data):
            print(f'model fitted to {len(args.data)} subjects.')
        else:
            n_fails = len(args.data) - len(glob.glob(pe_dir + '/subj_*.nii.gz'))
            raise ValueError(f'model fitting failed for {n_fails} subjects.')
    else:
        print('parameter estimates already exist in the specified path')

    # apply glm:
    if args.design_mat is not None:
        param_names = dm.prior_distributions[args.model].keys()
        fit_results, invalids = read_pes(pe_dir, args.mask)
        x = loadDesignMat(args.design_mat)
        if not fit_results.shape[0] == x.shape[0]:
            raise ValueError(f'Design matrix with {x.shape[0]} subjects does not match with '
                             f'loaded parameters for {fit_results.shape[0]} subjects.')

        pe1 = fit_results[x[:, 0] == 1, :, :len(param_names)].mean(axis=0)
        pe2 = fit_results[x[:, 1] == 1, :, :len(param_names)].mean(axis=0)

        varpe1 = fit_results[x[:, 0] == 1, :, :len(param_names)].var(axis=0)
        varpe2 = fit_results[x[:, 1] == 1, :, :len(param_names)].var(axis=0)

        z_values = (pe2 - pe1) / np.sqrt(varpe1/np.sqrt(x[:, 0].sum()) + varpe2 / np.sqrt(x[:, 1].sum()))
        p_values = st.norm.sf(abs(z_values)) * 2  # two-sided

        # _, delta, sigma = group_glm(pes, args.design_mat, args.design_con)
        # zvals = delta / np.sqrt(np.diagonal(sigma, axis1=1, axis2=2))
        for d, p in zip(p_values, param_names):
            fname = f'{args.output}/zmaps/{p}'
            user_interface.write_nifti(d, args.mask, fname=fname , invalids=invalids)
        print(f'Analysis completed sucessfully, the z-maps are stored at {args.output}')


def single_sub_fit(subj_idx, diff_add, xfm_add, bvec_add, bval_add, mask_add, mdl_name, output_add):
    print('diffusion data address:' + diff_add)
    print('xfm address:' + xfm_add)
    print('bvec address: ' + bvec_add)
    print('bval address: ' + bval_add)
    print('mask address: ' + mask_add)
    print('model name: ' + mdl_name)
    print('output path: ' + output_add)

    bvals = np.genfromtxt(bval_add)
    bvals = np.round(bvals/1000, 1)
    bvecs = np.genfromtxt(bvec_add)
    if bvecs.shape[1] > bvecs.shape[0]:
        bvecs = bvecs.T

    def_field_dir = f"{output_add}/def_fields/"
    os.makedirs(def_field_dir, exist_ok=True)
    def_field = f"{def_field_dir}/{subj_idx}.nii.gz"
    data, valid_vox = summary_measures.sample_from_native_space(diff_add, xfm_add, mask_add, def_field)
    data = data / 1000
    params = fit_model(data, mdl_name, bvals, bvecs, sph_degree=4)
    print(f'subject {subj_idx} parameters estimated.')

    # write down [pes, vpes] to 4d files
    fname = f"{output_add}/subj_{subj_idx}.nii.gz"
    user_interface.write_nifti(params, mask_add, fname, np.logical_not(valid_vox))
    print(' Model fitted to subject')


def parse_args_and_fit(args):
    args.pop(0)  # python file name
    single_sub_fit(*args)


if __name__ == '__main__':
    parse_args_and_fit(sys.argv)


def inference_parse_args(argv):
    """
    Parses the commandline input anc checks for the consistency of inputs
    :param argv: input string from commandline
    :return: arg namespce from argparse
    :raises: if the number of provided files do not match with other arguments
    """

    parser = argparse.ArgumentParser("BENCH: Bayesian EstimatioN of CHange")
    parser.add_argument("--mask", help="Mask in standard space indicating which voxels to analyse", required=True)
    parser.add_argument("--output", help="Path to the output directory", required=True)

    inference = parser.add_argument_group("Inference arguments")
    inference.add_argument("--design-mat", help="Design matrix for the group glm", required=False)
    inference.add_argument("--design-con", help="Design contrast for the group glm", required=False)
    inference.add_argument("--model", help="Forward model, either name of a standard model or full path to"
                                           "a trained model json file", default=None, required=False)

    # pre-processing arguments:
    preproc = parser.add_argument_group("Summary fit arguments")
    preproc.add_argument('--summary-dir', default=None,
                         help='Path to the pre-computed summary measurements', required=False)
    preproc.add_argument("--data", nargs='+', help="List of dMRI data in subject native space", required=False)
    preproc.add_argument("--xfm", help="Non-linear warp fields mapping subject diffusion space to the mask space",
                         nargs='+', metavar='xfm.nii', required=False)
    preproc.add_argument("--bvecs", nargs='+', metavar='bvec', required=False,
                         help="Gradient orientations for each subject")
    preproc.add_argument("--bval", metavar='bval', required=False,
                         help="b_values (should be the same for all subjects")
    preproc.add_argument("--sph_degree", default=4, help=" Degree for spherical harmonics summary measurements",
                         required=False, type=int)

    args = parser.parse_args(argv)

    if not os.path.exists(args.mask):
        raise FileNotFoundError('Mask file was not found.')

    if os.path.isdir(args.output):
        warn('Output directory already exists, contents might be overwritten.')
        if not os.access(args.output, os.W_OK):
            raise PermissionError('user does not have permission to write in the output location.')
    else:
        os.makedirs(args.output, exist_ok=True)

    if args.summary_dir is None:
        n_subjects = min(len(args.xfm), len(args.data), len(args.bvecs))
        if len(args.data) > n_subjects:
            raise ValueError(f"Got more diffusion MRI dataset than transformations/bvecs: {args.data[n_subjects:]}")
        if len(args.xfm) > n_subjects:
            raise ValueError(f"Got more transformations than diffusion MRI data/bvecs: {args.xfm[n_subjects:]}")
        if len(args.bvecs) > n_subjects:
            raise ValueError(f"Got more bvecs than diffusion MRI data/transformations: {args.bvecs[n_subjects:]}")

        for subj_idx, (nl, d, bv) in enumerate(zip(args.xfm, args.data, args.bvecs), 1):
            print(f'Scan {subj_idx}: dMRI ({d} with {bv}); transform ({nl})')
            for f in [nl, d, bv]:
                if not os.path.exists(f):
                    raise FileNotFoundError(f'{f} not found. Please check the input files.')

        if not os.path.exists(args.bval):
            raise FileNotFoundError(f'{args.bval} not found. Please check the paths for input files.')

    if args.model is not None:
        if args.design_mat is None:
            raise RuntimeError('For inference you have to provide a design matrix file.')
        elif not os.path.exists(args.design_mat):
            raise FileNotFoundError(f'{args.design_mat} file not found.')

        if args.design_con is None:
            raise RuntimeError('For inference you need to provide a design contrast file.')
        elif not os.path.exists(args.design_con):
            raise FileNotFoundError(f'{args.design_con} file not found.')

    return args
