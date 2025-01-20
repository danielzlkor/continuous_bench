# Continuous BENCH

## What is it?

Taken from [BENCH](https://git.fmrib.ox.ac.uk/hossein/bench). Please refer to this library for more details on how does it work.

"BENCH (Bayesian EstimatioN of CHange) is a toolbox implemented in python for identifying and estimating changes in the parameters of a biophysical model between two groups of data (e.g. patients and controls). It is an alternative to model inversion, where one estimates the parameters for each group separately and compares the estimations between the groups (e.g. using a GLM). The advantage is that BENCH allows for using over-parameterised models where the model inversion approaches fail because of parameter degeneracies. Currently, BENCH only supports microstructural models of diffusion MRI, but it is extendable to other domains"

This library modifies a version of BENCH to work with continuous variables (named "**Continuous BENCH**")

Here, we specifically apply it to link changes in dMRI signals to **microscopy-derived metrics**. Here, the microscopy-derived metrics are taken from the [Bigmac dataset](https://pages.fmrib.ox.ac.uk/amyh/bigmacdocumentation/microscopy.html). 

## Installation

This assumes you have conda (https://docs.conda.io/en/latest/) already installed.

1. Git clone this repository

```
git clone https://git.fmrib.ox.ac.uk/spet4877/continuous_bench.git
```

2. Create a new conda environment

```
conda create -n cbench_env
conda activate cbench_env
```

3. Navigate to directory and install necessary packages

```
cd continuous_bench
conda install --file requirements.txt --channel conda-forge

```

## How to use it?

This library is divided into three primary components: **Training**, **GLM**, and **Inference**.

The scripts we show here is what we have used to analyse ex-vivo macaque brain data and simulation data, as published [here](https://www.biorxiv.org/content/10.1101/2024.09.30.615704v1) 

---

### Data files

This library relies on several key data files during training and inference. These include acquisition parameters, dMRI data, and microscopy data.
Below is a summary of the important files:


1. **Acquisition files**:
   - Ex Vivo: `acquisition_params_for_exvivo_data.npz` 
   - Simulation: `acquisition_params_for_simulation_data.npz`

   These files contain acquisition parameters such as gradient strengths, directions, and b-values used to acquire or simulate the dMRI data.

2. **Input Data**:
   - dMRI Data: `dwi_for_exvivo_data.npz` **This file is available upon request.**
   - Microscopy Data: `microscopy_for_exvivo_data.npz`

   These files are what we analyse to link dMRI data to microscopy data.

### **1. Training**

#### **Description**
The training scripts are used to generate change models. In the paper, we trained change models for ex-vivo data and simulated data. These models are trained using pre-defined acquisition parameters and a specified number of samples.

Feel free to tailor these scripts according to your application.

### **Usage**

Training is performed using the following bash scripts:

- **Ex Vivo Data**: `script_for_training_change_model_for_exvivo_data.sh`
- **Simulated Data**: `script_for_training_change_model_for_simulation_data.sh`

Each script defines the necessary paths and parameters for training and invokes the corresponding Python training script.

#### **Example Commands**

1. **Training change models for ex-vivo data**:
   ```bash
   ./script_for_training_change_model_for_exvivo_data.sh
   ```
   Parameters:
   - Acquisition file: `data/acquisition_params_for_exvivo_data.npz`
   - Number of samples: 20,000
   - Output directory: `change_model/`

2. **Training change models for simulation data**:
   ```bash
   ./script_for_training_change_model_for_simulation_data.sh
   ```
   Parameters:
   - Acquisition file: `data/acquisition_params_for_exvivo_data.npz`
   - Number of samples: 20,000
   - Output directory: `change_model/`

#### **Python Scripts**

- `training_change_model_for_exvivo_data.py`
- `training_change_model_for_simulation_data.py`

These python scripts are called by the shell scripts.
The python scripts trained change models that characterise the distribution of change vectors (i.e. how dMRI summary measures change, given a change in biophysical model parameter).  

---

## **2. GLM (Generalised Linear Model)**

### **Description**
A GLM is used to model the change in the dMRI signal with respect to continuous variable-of-interest.
This has been incorporated with the next inference step into a jupyter notebook (see below)


## **3. Inference**

### **Description**
The inference scripts apply the trained models to ex-vivo or simulated datasets, inferring predictions from changes. These scripts also incorporate the GLM.

### **Usage**

Inference is performed using the following Jupyter Notebooks:

- `inferences_for_exvivo_data.ipynb`
- `inferences_for_simulation_data.ipynb`

These notebooks:

1. Load the trained change models. **As part of the paper, we currently have two models we have already trainings**:
   - Ex Vivo: `change_model_for_exvivo_data`
   - Simulation: `change_model_for_simulation_data`
2. Load the data files.
3. Perform inference on ex vivo or simulated datasets. 

#### **Steps to Use**

1. Open the desired notebook in JupyterLab or another compatible environment.
2. Configure paths and parameters, such as:
   - Input data files.
   - Model paths.
   - Output directories.
3. Execute the cells step-by-step to perform inference and analysis.

---

## **Dependencies**


Install all dependencies using:
```bash
pip install -r requirements.txt
```

## How to cite this material

D. Z. L. Kor et al., “Linking microscopy to diffusion MRI with degenerate biophysical models: an application of the Bayesian EstimatioN of CHange (BENCH) framework,” Oct. 01, 2024, bioRxiv. doi: 10.1101/2024.09.30.615704.

## Contact

For any requests and/or queries, please contact me at daniel.zl.kor@gmail.com.

## License

Distributed under a CC-BY-4.0 license for research but not commerical use.

## Copyright

Copyright (c), 2024, University of Oxford. All rights reserved




