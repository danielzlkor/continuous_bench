#!/usr/bin/env python3
"""
This module is to parse inputs from commandline and call the proper functions from other modules.
"""

import argparse
import glob
import os
from warnings import warn
import numpy as np
from fsl.utils.run import run
from bench import change_model, glm, summary_measures, diffusion_models, acquisition, image_io
from joblib import delayed, Parallel


def main(argv=None):
    """
    Wrapper function to parse the input from commandline and run the requested pipeline.

    :param argv: string from command line containing all required inputs 
    :return: saves the output images to the specified path
    """
    args = parse_args(argv)

    if args.commandname == 'diff-train':
        submit_train(args)
    elif args.commandname == 'diff-summary':
        submit_summary(args)
    elif args.commandname == 'diff-single-summary':
        submit_summary_single_subject(args)
    elif args.commandname == 'diff-normalize':
        print('Normalization is performed while loading the data.')
        # submit_normalize(args)
    elif args.commandname == 'glm':
        submit_glm(args)
    elif args.commandname == 'inference':
        submit_inference(args)
    else:
        print_avail_commands()


def print_avail_commands():
    print('BENCH: Bayesian EstimatioN of CHange')
    print('usage: bench <command> [options]')
    print('')
    print('available commands: diff-train, diff-summary,diff-single-summary,diff-normalize,glm,inference')


def parse_args(argv):
    """
    Parses the commandline input anc checks for the consistency of inputs
    :param argv: input string from commandline
    :return: arg namespce from argparse
    :raises: if the number of provided files do not match with other arguments
    """

    parser = argparse.ArgumentParser("BENCH: Bayesian EstimatioN of CHange")
    subparsers = parser.add_subparsers(dest='commandname')

    diff_train_parser = subparsers.add_parser('diff-train')
    diff_summary_parser = subparsers.add_parser('diff-summary')
    diff_single_subj_summary_parser = subparsers.add_parser('diff-single-summary')
    diff_normalize_parse = subparsers.add_parser('diff-normalize')
    glm_parser = subparsers.add_parser('glm')
    inference_parser = subparsers.add_parser('inference')

    # train arguments:
    train_required = diff_train_parser.add_argument_group("required arguments")
    available_models = list(diffusion_models.prior_distributions.keys())
    train_required.add_argument("--model",
                                help=f"name of the forward model. Available models:\n{available_models}", required=True)
    train_required.add_argument("--output", help="name of the trained model", required=True)
    train_required.add_argument("--bval", required=True)

    train_optional = diff_train_parser.add_argument_group("optional arguments")
    train_optional.add_argument("-n", default=10000, type=int, help="number of training samples (default=10000)",
                                required=False)
    train_optional.add_argument("-p", default=2, type=int, help="polynomial degree for mu design matrix (default=2)",
                                required=False)
    train_optional.add_argument("-ps", default=1, type=int, help="polynomial degree for sigma design matrix(default=1)",
                                required=False)
    train_optional.add_argument("-d", default=4, type=int,
                                help=" maximum degree for summary measures (must be even numbers, default=4)",
                                required=False)
    train_optional.add_argument("--alpha", default=0.0, type=float,
                                help="regularisation weight (default=0)", required=False)
    train_optional.add_argument("--change-vecs", help="vectors of change", default=None, required=False)
    train_optional.add_argument("--summary", default='shm', type=str,
                                help='type of summary measurements. Either shm (spherical harmonic model)'
                                     ' or dtm (diffusion tensor model) (default shm)', required=False)
    train_optional.add_argument('--verbose', help='flag for printing optimisation outputs', dest='verbose',
                                action='store_true', default=False)
    # fit summary arguments:
    diff_summary_parser.add_argument("--mask",
                                     help="Mask in standard space indicating which voxels to analyse", required=True)
    diff_summary_parser.add_argument("--data", nargs='+', help="List of dMRI data in subject native space",
                                     required=True)
    diff_summary_parser.add_argument("--xfm",
                                     help="Non-linear warp fields from diffusion space to the standard",
                                     nargs='+', metavar='xfm.nii', required=True)
    diff_summary_parser.add_argument("--bvecs", nargs='+', metavar='bvec', required=True,
                                     help="Gradient orientations for each subject")
    diff_summary_parser.add_argument("--bval", nargs='+', metavar='bval', required=True,
                                     help="b_values (should be the same for all subjects")
    diff_summary_parser.add_argument("--shm-degree", default=2,
                                     help=" Degree for spherical harmonics summary measurements",
                                     required=False, type=int)
    diff_summary_parser.add_argument("--study-dir", help="Path to the output directory", required=True)
    diff_summary_parser.add_argument('--force-local',
                                     help='forces running computions locally rather than submitting'
                                          ' to the available cluster', dest='force_local',
                                     action='store_true', default=False)
    # single subject summary:
    diff_single_subj_summary_parser.add_argument('subj_idx')
    diff_single_subj_summary_parser.add_argument('diff_add')
    diff_single_subj_summary_parser.add_argument('bvec_add')
    diff_single_subj_summary_parser.add_argument('bval_add')
    diff_single_subj_summary_parser.add_argument('mask_add')
    diff_single_subj_summary_parser.add_argument('xfm_add')
    diff_single_subj_summary_parser.add_argument('output_add')
    diff_single_subj_summary_parser.add_argument('shm_degree', type=int, default=2)

    # normalization args
    diff_normalize_parse.add_argument('--study-dir', default=None,
                                      help='Path to the un-normalized summary measurements', required=True)

    # glm arguments:
    glm_parser.add_argument("--design-mat", help="Design matrix for the group glm", required=False)
    glm_parser.add_argument("--design-con", help="Design contrast for the group glm", required=False)
    glm_parser.add_argument('--paired', dest='paired', action='store_true')
    glm_parser.add_argument("--study-dir", help='Path to save the outputs', default='./')
    glm_parser.add_argument("--mask", help='Path to the mask', required=True)

    # inference arguments:
    inference_parser.add_argument("--model", help="Forward model, either name of a standard model or full path to"
                                                  "a trained change model file", default=None, required=True)
    inference_parser.add_argument('--study-dir', help="Path to store posterior probability maps")
    inference_parser.add_argument("--mask", help='Path to the mask', default=None, required=False)
    inference_parser.add_argument("--integral-bound",
                                  help='The bound for integrating over the amount of change(default=1)',
                                  default=1.0, required=False)

    args = parser.parse_args(argv)

    return args


def submit_train(args):
    available_models = list(diffusion_models.prior_distributions.keys())
    if args.model in available_models:
        param_prior_dists = diffusion_models.prior_distributions[args.model]
        p_names = [i for p in param_prior_dists.keys() for i in ([p] if isinstance(p, str) else p)]
        print(f'Parameters of {args.model}:{p_names}')
    else:
        model_names = ', '.join(list(diffusion_models.prior_distributions.keys()))
        raise ValueError(f'model {args.model} is not defined in the library. '
                         f'Defined models are:\n {model_names}')

    funcdict = {name: f for (name, f) in diffusion_models.__dict__.items() if name in available_models}
    forward_model = funcdict[args.model]
    param_dist = diffusion_models.prior_distributions[args.model]

    bvals = np.genfromtxt(args.bval)
    idx_shells, shells = acquisition.ShellParameters.create_shells(bval=bvals)

    bvecs = np.array(diffusion_models.spherical2cart(
        *diffusion_models.uniform_sampling_sphere(len(idx_shells)))).T

    acq = acquisition.Acquisition(shells, idx_shells, bvecs)
    func_args = {'acq': acq, 'noise_level': 0}
    if args.summary == 'shm':
        func_args['shm_degree'] = args.d

    if args.change_vecs is not None:
        with open(args.change_vecs, 'r') as reader:
            args.change_vecs = [line.rstrip() for line in reader]

    summary_names = summary_measures.summary_names(acq, shm_degree=args.d)
    trainer = change_model.Trainer(
        forward_model=diffusion_models.bench_decorator(forward_model, summary_type=args.summary),
        kwargs=func_args,
        change_vecs=args.change_vecs,
        summary_names=summary_names,
        param_prior_dists=param_dist)

    ch_model = trainer.train_ml(n_samples=int(args.n),
                                mu_poly_degree=int(args.p),
                                sigma_poly_degree=int(args.ps),
                                alpha=float(args.alpha),
                                parallel=True,
                                verbose=args.verbose)

    ch_model.forward_model_name = forward_model.__name__
    ch_model.meausrement_names = summary_measures.summary_names(acq, args.d)
    ch_model.save(path='', file_name=args.output)
    print('All change models were trained successfully')


def submit_summary(args):
    """
    submits jobs to cluster (or runs serially) to compute summary measurements for the given subjects
    :param args: namespace form parseargs output that contains all addresses to the required files
    (masks, transformations, diffusion data, bvalues, and bvecs) and output folder
    :return: job ids (the results are saved to files once the jobs are done)
    """
    if not os.path.exists(args.mask):
        raise FileNotFoundError('Mask file was not found.')

    if os.path.isdir(args.study_dir):
        warn('Output directory already exists, contents might be overwritten.')
        if not os.access(args.study_dir, os.W_OK):
            raise PermissionError('User does not have permission to write in the output location.')
    else:
        os.makedirs(args.study_dir, exist_ok=True)

    n_subjects = min(len(args.xfm), len(args.data), len(args.bvecs))
    if len(args.data) > n_subjects:
        raise ValueError(f"Got more diffusion MRI dataset than transformations/bvecs: {args.data[n_subjects:]}")
    if len(args.xfm) > n_subjects:
        raise ValueError(f"Got more transformations than diffusion MRI data/bvecs: {args.xfm[n_subjects:]}")
    if len(args.bvecs) > n_subjects:
        raise ValueError(f"Got more bvecs than diffusion MRI data/transformations: {args.bvecs[n_subjects:]}")

    if len(args.bval) == 1:  # if a single bval passed.
        args.bval = args.bval * len(args.bvecs)

    for subj_idx, (nl, d, bvec, bval) in \
            enumerate(zip(args.xfm, args.data, args.bvecs, args.bval), 1):
        print(f'Scan {subj_idx}: dMRI ({d} with {bvec} and {bval}); transform ({nl})')
        for f in [nl, d, bvec, bval]:
            if not os.path.exists(f):
                raise FileNotFoundError(f'{f} not found.')

    summary_dir = f'{args.study_dir}/SummaryMeasurements'

    os.makedirs(summary_dir, exist_ok=True)

    if len(glob.glob(summary_dir + '/subj_*.nii.gz')) == len(args.data):
        print('Summary measurements already exist in the specified path.'
              'If you want to re-compute them, delete the current files.')
        job_id = 0
    else:
        task_list = list()
        for subj_idx, (x, d, bval, bvec) in enumerate(zip(args.xfm, args.data, args.bval, args.bvecs)):
            cmd = f'bench diff-single-summary {subj_idx} {d} {bvec} ' \
                  f'{bval} {args.mask} {x} {args.study_dir} {args.shm_degree}'
            task_list.append(cmd)
        # main(cmd.split()[1:]) # just for debugging.

        if 'SGE_ROOT' in os.environ.keys() and not args.force_local:
            with open(f'{args.study_dir}/summary_tasklist.txt', 'w') as f:
                for t in task_list:
                    f.write("%s\n" % t)
                f.close()

                job_id = run(f'fsl_sub --export PATH -t {args.study_dir}/summary_tasklist.txt '
                             f'-T 200 -R 4 -N bench_summary -l {args.study_dir}/log',
                             env=os.environ, exitcode=True, stderr=True)

                print(f'Jobs were submitted to SGE with job id {job_id[0]}.')
        else:
            print(f'No clusters were found. The jobs are running locally.')

            # processes = [subprocess.Popen(t.split(), shell=False, env=os.environ) for t in task_list]
            # [p.wait() for p in processes]

            def func(subj_idx):
                x, d, bval, bvec = args.xfm[subj_idx], args.data[subj_idx], args.bval[subj_idx], args.bvecs[subj_idx]
                summary_measures.fit_summary_single_subject(diff_add=d, bvec_add=bvec, bval_add=bval,
                                                            mask_add=args.mask, xfm_add=x,
                                                            shm_degree=args.shm_degree, subj_idx=subj_idx,
                                                            output_add=f'{args.study_dir}/SummaryMeasurements')

            res = Parallel(n_jobs=-1, verbose=True)(delayed(func)(i) for i in range(len(args.data)))
            #for i in range(len(args.data)):
            #    func(i)

            job_id = 0

    return job_id


def submit_summary_single_subject(args):
    """
        Wrapper function that parses the input from commandline
        :param args: list of strings containing all required parameters for fit_summary_single_subj()
        """
    output_add = args.output_add + '/SummaryMeasurements'
    summary_measures.fit_summary_single_subject(diff_add=args.diff_add, bvec_add=args.bvec_add, bval_add=args.bval_add,
                                                mask_add=args.mask_add, xfm_add=args.xfm_add,
                                                shm_degree=args.shm_degree,
                                                subj_idx=args.subj_idx, output_add=output_add)


def submit_glm(args):
    """
    Runs glm on the summary meausres.
    :param args: output from argparse, should contain desing matrix anc contrast addresss, summary_dir and masks
    :return:
    """
    assert args.paired or (args.design_mat is not None and args.design_con is not None)

    glm_dir = f'{args.study_dir}/Glm'
    if os.path.exists(args.study_dir + '/SummaryMeasurements'):
        summary_dir = args.study_dir + '/SummaryMeasurements'
    else:
        summary_dir = args.study_dir

    if not os.path.isdir(glm_dir):
        os.makedirs(glm_dir)

    summaries, invalid_vox, summary_names = image_io.read_summary_images(
        summary_dir=summary_dir, mask=args.mask)

    summaries = summaries[:, invalid_vox == 0, :]

    if args.paired:
        data, delta_data, sigma_n = glm.group_glm_paired(summaries)
    else:
        if args.design_mat is None:
            raise RuntimeError('For inference you have to provide a design matrix file.')
        elif not os.path.exists(args.design_mat):
            raise FileNotFoundError(f'{args.design_mat} file not found.')

        if args.design_con is None:
            raise RuntimeError('For inference you need to provide a design contrast file.')
        elif not os.path.exists(args.design_con):
            raise FileNotFoundError(f'{args.design_con} file not found.')

        data, delta_data, sigma_n = glm.group_glm(summaries, args.design_mat, args.design_con)

    image_io.write_glm_results(data, delta_data, sigma_n, args.mask,
                               invalid_vox, glm_dir)
    y_norm, dy_norm, sigma_n_norm = \
        summary_measures.normalize_summaries(data, summary_names, delta_data, sigma_n)

    image_io.write_glm_results(y_norm, dy_norm, sigma_n_norm, args.mask, invalid_vox, glm_dir + '_normalised')
    print(f'GLM is done. Results are in written in {args.glm_dir}')


def submit_inference(args):
    glm_dir = f'{args.study_dir}/Glm/'
    data, delta_data, sigma_n = image_io.read_glm_results(glm_dir)

    # perform inference:
    ch_mdl = change_model.ChangeModel.load(args.model)
    posteriors, predictions, peaks, bad_samples = ch_mdl.infer(data, delta_data, sigma_n,
                                                               integral_bound=float(args.integral_bound), parallel=True)

    # save the results:
    maps_dir = f'{args.study_dir}/Results/{ch_mdl.forward_model_name}'
    image_io.write_inference_results(maps_dir, ch_mdl.model_names, predictions, posteriors, peaks,
                                     f'{args.study_dir}/Glm/valid_mask')

    dv, offset, deviation = ch_mdl.estimate_quality_of_fit(data, delta_data, sigma_n, predictions, peaks)
    image_io.write_nifti(deviation[:, np.newaxis], f'{args.study_dir}/Glm/valid_mask',
                         f'{maps_dir}/sigma_deviations.nii.gz')

    print(f'Analysis completed successfully, the posterior probability maps are stored in {maps_dir}')


if __name__ == '__main__':
    print('This is bench user interface.')
