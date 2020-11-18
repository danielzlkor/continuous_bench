"""
This module is to parse inputs from commandline and call the proper functions from other modules.
"""
import argparse
import os
from warnings import warn
import numpy as np
from bench import inference, change_model, glm, summary_measures, diffusion_models, simulator
from fsl.data.image import Image
import nibabel as nib


def from_command_line(argv=None):
    """
    Wrapper function to parse input and run main.
    :param argv: string from command line containing all required inputs 
    :return: saves the output images to the specified path
    """
    
    args = parse_args(argv)
    main(args)


def main(args):
    """
    Main function that calls all the required steps.
    :param args: output namespace from argparse from commandline input  
    :return: runs the process and save images to the specified path
    :raises: when the input files are not available
    """
    
    ch_mdl = change_model.ChangeModel.load(args.model)

    if not os.path.isdir(args.output):
        os.makedirs(args.output)

    # if summaries are not provided fit summaries:
    if args.sm_dir is None:
        args.sm_dir = f'{args.output}/SummaryMeasures'
        summary_measures.fit_summary(diff=args.data, bvecs=args.bvecs,
                                     bvals=args.bval, xfms=args.xfm, output=args.sm_dir)

    summaries, invalid_vox = summary_measures.read_summaries(path=args.summary_dir)

    # perform glm:
    data, delta_data, sigma_n = glm.group_glm(summaries, args.design_mat, args.design_con)

    # perform inference:
    sets, posteriors, _ = inference.compute_posteriors(change_model, args.prior_change, data, delta_data, sigma_n)

    # save the results:
    maps_dir = f'{args.output}/PosteriorMaps/{ch_mdl.model_name}'
    inference.write_nifti(sets, posteriors, args.mask, maps_dir, invalid_vox)
    print(f'Analysis completed successfully, the posterior probability maps are stored in {maps_dir}')


def parse_args(argv):
    """
    Parses the commandline input anc checks for the consistency of inputs
    :param argv: input string from commandline
    :return: arg namespce from argparse
    :raises: if the number of provided files do not match with other arguments
    """

    parser = argparse.ArgumentParser("BENCH: Bayesian EstimatioN of CHange")

    required = parser.add_argument_group("required arguments")
    required.add_argument("--mask", help="Mask in standard space indicating which voxels to analyse", required=True)
    required.add_argument("--design-mat", help="Design matrix for the group glm", required=True)
    required.add_argument("--design-con", help="Design contrast for the group glm", required=True)
    required.add_argument("--model", help="Forward model, either name of a standard model or full path to "
                                          "a trained model json file", required=True)
    required.add_argument("--output", help="Path to the output directory", required=True)

    required.add_argument('--summary-dir', help='Path to the pre-computed summary measurements', required=False)
    required.add_argument("--data", nargs='+', help="List of dMRI data in subject native space", required=True)
    required.add_argument("--xfm", help="Non-linear warp fields mapping subject diffusion space to the mask space",
                          nargs='+', metavar='xfm.nii', required=True)
    required.add_argument("--bvecs", nargs='+', metavar='bvec', required=True,
                          help="Gradient orientations for each subject")

    optional = parser.add_argument_group("optional arguments")
    optional.add_argument("--sigma-v", default=0.1,
                          help="Standard deviation for prior change in parameters (default = 0.1)", required=False)

    summary_measures.ShellParameters.add_to_parser(parser)

    args = parser.parse_args(argv)

    # fix the problem of getting a single arg for list arguments:
    if len(args.xfm) == 1:
        args.xfm = args.xfm[0].split()
    if len(args.data) == 1:
        args.data = args.data[0].split()
    if len(args.bvecs) == 1:
        args.bvecs = args.bvecs[0].split()

    for subj_idx, (nl, d, bv) in enumerate(zip(args.xfm, args.data, args.bvecs), 1):
        print(f'Scan {subj_idx}: dMRI ({d} with {bv}); transform ({nl})')
    print('')

    n_subjects = min(len(args.xfm), len(args.data), len(args.bvecs))
    if len(args.data) > n_subjects:
        raise ValueError(f"Got more diffusion MRI dataset than transformations/bvecs: {args.data[n_subjects:]}")
    if len(args.xfm) > n_subjects:
        raise ValueError(f"Got more transformations than diffusion MRI data/bvecs: {args.xfm[n_subjects:]}")
    if len(args.bvecs) > n_subjects:
        raise ValueError(f"Got more bvecs than diffusion MRI data/transformations: {args.bvecs[n_subjects:]}")
    if os.path.isdir(args.output):
        warn('Output directory already exists, contents might be overwritten.')
    else:
        os.makedirs(args.output, exist_ok=True)

    return args


def train_from_command_line(argv=None):
    args = parse_args(argv)
    available_models = list(diffusion_models.prior_distributions.keys())
    funcdict = {name: f for (name, f) in diffusion_models.__dict__.items() if f in available_models}
    forward_model = funcdict[args.model]

    idx_shells, shells = summary_measures.ShellParameters.from_parser_args(args)
    bvecs = np.zeros((len(idx_shells), 3))
    acq = simulator.Acquisition(shells, idx_shells, bvecs)
    change_models = change_model(forward_model=forward_model, x=acq,
                                       n_samples=int(args.n), k=int(args.k), sph_degree=int(args.d),
                                       poly_degree=int(args.p), regularization=float(args.alpha))
    change_models.save(path='', file_name=args.output)
    print('Change model trained successfully')


def train_parse_args(argv):
    parser = argparse.ArgumentParser("BENCH Train: Training models of change")

    required = parser.add_argument_group("required arguments")
    required.add_argument("--model", help="Forward model name", required=True)
    required.add_argument("--output", help="name of the trained model", required=True)

    optional = parser.add_argument_group("optional arguments")
    optional.add_argument("-k", default="100", help="number of nearest neighbours", required=False)
    optional.add_argument("-n", default="10000", help="number of training samples", required=False)
    optional.add_argument("-p", default="2", help="polynomial degree for design matrix", required=False)
    optional.add_argument("-d", default="4", help="spherical harmonics degree", required=False)
    optional.add_argument("--alpha", default="0.5", help="regularization weight", required=False)
    optional.add_argument("--mdfa", default=False, help="include MD and FA in summary measures", required=False)

    summary_measures.ShellParameters.add_to_parser(parser)
    args = parser.parse_args(argv)

    # handle the problem of getting single arg for list arguments:
    if args.model in diffusion_models.prior_distributions.keys():
        print('The change models will be trained for the follwing parameters:')
        print(list(diffusion_models.prior_distributions[args.model].keys()))
    else:
        model_names = ', '.join(list(diffusion_models.prior_distributions.keys()))
        raise ValueError(f'The forward model is not defined in the library. '
                         f'Defined models are:\n {model_names}')

    return args


def write_nifti(set_name, posteriors, mask_add, path='.', invalids=None):
    """
    Writes the results to nifti files per change model.

    """
    if os.path.isdir(path):
        warn('Output directory already exists, contents might be overwritten.')
    else:
        os.makedirs(path, exist_ok=True)
    winner = np.argmax(posteriors, axis=1)
    mask = Image(mask_add)

    std_indices = np.array(np.where(mask.data > 0)).T
    std_indices_valid = std_indices[[not v for v in invalids]]
    std_indices_invalid = std_indices[invalids]

    for s_i, s_name in enumerate(set_name):
        data = posteriors[:, s_i]
        tmp1 = np.zeros(mask.shape)
        tmp1[tuple(std_indices_valid.T)] = data
        tmp1[tuple(std_indices_invalid.T)] = np.nan
        tmp2 = np.zeros(mask.shape)
        tmp2[tuple(std_indices_valid.T)] = winner == s_i
        tmp2[tuple(std_indices_invalid.T)] = np.nan
        mat = np.concatenate([tmp1, tmp2], axis=-1)

        fname = f"{path}/{s_name}.nii.gz"
        nib.Nifti1Image(mat, mask.nibImage.affine).to_filename(fname)
