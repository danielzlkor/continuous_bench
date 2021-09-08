#!/usr/bin/env python
"""The setup script."""

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('requirements.txt', 'r') as f:
    requirements = [line.strip() for line in f.readlines() if len(line.strip()) > 0]

test_requirements = ['pytest', ]


setup(
    author="Hossein Rafipoor, Michiel Cottaar, Saad Jbabdi",
    author_email='hossein.rafipoor@ndcn.ox.ac.uk',
    python_requires='>=3.6',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    entry_points={
        'console_scripts': [
            'bench=bench.user_interface:main',
            'bench_train=bench.user_interface:submit_train',
            'bench_preproc=bench.user_interface:submit_summary',
            'bench_fit_summary=bench.user_interface:submit_summary_single_subject',
        ],
    },
    install_requires=requirements,
    long_description=readme,
    include_package_data=True,
    name='bench',
    packages=find_packages(include=['bench', 'bench.*']),
    test_suite='bench.tests',
    tests_require=test_requirements,
    url='https://git.fmrib.ox.ac.uk/hossein/bench.git',
    version='0.0.1',
)
