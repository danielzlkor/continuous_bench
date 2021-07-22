# BENCH
Bayesian EstimatioN of CHange

## What is it?
BENCH is a toolbox for identifying and estimating changes in parameters of a biophysical model between two groups of data (e.g. patients and controls). It is an alternative for model inversion, that is estimating the parameters for each group separately and compare the estimations. The advantage is that BENCH allows for using over parameterised models where the model inversion approaches fail because of parameter degeneraceis. Currently, BENCH only supports microstructural models for diffusion MRI, but it is extendable to other domains.    

## When it is useful?
Bench is usful when the aim is comparing two groups of data in terms of parameters of a biophysical model; but not estimating the parameters pre.se. It is particularly advantagous when the model has more free parameters than what can be estimated given the measurements.  

## How it works?
Using simulated data, we generate models of change that can predict how a baseline measurement changes if any of the parameters of the model changes. Then, in a bayesian framework, we estimate which of the "change models" can better explain the observed change between two groups. For more details about the method, please refer to the paper (link). 


## How to install it?
Here are the steps to install BENCH: 

1. clone the project from github. 
2. open a command line and ``cd`` to the downloded directory (that contains setup.py file)
3. run ``python setup.py install`` 

## What are the required inputs?
As bench is an alternative to model fitting, anything that is needed to fit models to two groups is needed for bench as well. Currently, bench only supports diffusion MRI data and microstructural models. This includes:

1. Preprocessed diffusion data for each subject in two groups. 
2. Transformations from native diffusion space to a standard structual space, e.g. MNI.
3. A ROI mask in the standard space that defines voxels to analyse. 
4. b-value and b-vec files. (the same format as accepted in FDT)
5. Design.mat and contranst.mat files generated by Glm_gui. (refer to glm section below)

## How to use it?
BENCH runs in multiple steps that are explained as follows:

### Train change models:
 This step is for taining change models for parameters of a specific biophysical model with a given acquisition protocol. It doesnt require any data, and once the training is done the models can be used with any data with the same acquisition protocol. Generally, this step requires a forward model that can map parameters to measurements and prior distribution for each of them. Currently a few forward models have been implemented. Please refer to the paper for the details about the forward model and the priors for the parameters. You can add your model or update the priors in the [diffusion_models.py](bench/diffusion_models.py). 

 To train models of change you need to run the following command:

```
bench diff-train --model <model_name> --bval <path_to_bvalue_file> --output <name_of_output_file>
```

run `` bench diff-train --help`` to see the full list of optional parameters. This command generates a pickle file that contains trained machine learning models.


### Compute the summary measurements:
This stage estimates rotationally invariante summary measurements from dMRI data for each subject. We assume all the subjects have the same b-values, that is used for the training models of changes, but the b-vectors and ordering of measurements can vary across subjects.

Run the following command to estimate the summary measurements:
``` 
    bench diff-summary --data <list of all subjects diffusion data> 
    --xfm <list of all subjects warp fileds from native to standard space>
    --bval <a single bval or a list of bval file.>
    --bvec <list of bvecs for all subject>
    --mask <ROI mask in standard space>
    --study_dir <path to save summary measurements>
```
This command will make a `SummaryMeasurements` directory inside the specified `study_dir` that contains summary measurements per subject, numbered based on the ordering of input from 0 to the number of subjects.
  
### Run GLM:
This steps runs group glm to compute the baseline measurements, the change between groups and the noise covariance matrices. 

```
bench glm
--design-mat <Design matrix for the group glm>
--design-con <Design contrast for the group glm>
--study-dir <study directory>
```
`study dir` must contain the `SummaryMeasurements` directory.The design matrix must have one row per subject (with the smae order as the input for the previous step) and arbitrary number of columns. The contrast matrix must have two rows where the first one should correspond to the baseline measurement and the second one the group difference. In the simplest case, where there is no confounding variables the design matrix has two columns that have group memberships and the contrast is `[1 0, -1 1]`.    
 
This step produces a directory in the `study dir` that contains data.nii.gz, delta_data.nii.gz, variances.nii.gz, valid_mask.nii.gz. The valid mask contains all the voxels that all subjects had valid data, as some of the voxels from the standard mask can lie out of the brain masks for specific subjects.

### Make inference:
This final stage computes for each voxel the posterior probability for any of the change models trained in the first stage using the results of glm. 
```
bench inference
 --model <change model file>
  --study-dir <study directory>
```

`study directory` must contain the Glm folder produced in the earlier stage with the folder. This stage produces "Results" folder in the study directory that contains a folder for each forward model, e.g. `study_dir/Results/watson_noddi/`.  
## What are the outputs?
The results contain these outputs:
1. one preobability map per parameter of the forward model named '<pname_probability.nii.gz>. This contains per voxel the probability that change in that parameter can explain the observed change between the two groups.
2. one estimated change map parameter of the forward model named '<pname_amount.nii.gz>, which contains the estimated amount of change for the corresponding parameter.
3. best explaining model of change in each voxel '<inferred_change.nii.gz>'. This shows the index of the parameter that can best explain the observed change. The ordering is matched with the order of appearance in the prior distributions in [diffusion_models.py](bench/diffusion_models.py) 


## Usage for non-diffusion models and data
We designed BENCH to be as modular as possible, meaning that any stage is a separate module that can be replaced by user defined codes. Particularly to apply it to other domains one needs to provide the followings:
1. A biophysical model that maps parameters to summary measurements. (a callable function)
2. Prior distribution of the parameters of the model (a dictionary with keys being the parameters and values scipy stats distribution objects)
3. A script that computes summary measurements from raw data.



