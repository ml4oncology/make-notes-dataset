[![Project generated with PyScaffold](https://img.shields.io/badge/-PyScaffold-005CA0?logo=pyscaffold)](https://pyscaffold.org/)
<!-- These are examples of badges you might also want to add to your README. Update the URLs accordingly.
[![Built Status](https://api.cirrus-ci.com/github/<USER>/make_notes_dataset.svg?branch=main)](https://cirrus-ci.com/github/<USER>/make_notes_dataset)
[![ReadTheDocs](https://readthedocs.org/projects/make_notes_dataset/badge/?version=latest)](https://make_notes_dataset.readthedocs.io/en/stable/)
[![Coveralls](https://img.shields.io/coveralls/github/<USER>/make_notes_dataset/main.svg)](https://coveralls.io/r/<USER>/make_notes_dataset)
[![PyPI-Server](https://img.shields.io/pypi/v/make_notes_dataset.svg)](https://pypi.org/project/make_notes_dataset/)
[![Conda-Forge](https://img.shields.io/conda/vn/conda-forge/make_notes_dataset.svg)](https://anaconda.org/conda-forge/make_notes_dataset)
[![Monthly Downloads](https://pepy.tech/badge/make_notes_dataset/month)](https://pepy.tech/project/make_notes_dataset)
[![Twitter](https://img.shields.io/twitter/url/http/shields.io.svg?style=social&label=Twitter)](https://twitter.com/make_notes_dataset)
-->

# make_notes_dataset

> Generate clinical notes dataset from EMR data.

Python and bash scripts to process the clinical notes data set extracted by CDI into a more usable form.

## Installation

In order to set up the necessary environment:

1. review and uncomment what you need in `environment.yml` and create an environment `make_notes_dataset` with the help of [conda]:
   ```
   conda env create -f environment.yml
   ```
2. activate the new environment with:
   ```
   conda activate make_notes_dataset
   ```

> **_NOTE:_**  The conda environment will have make_notes_dataset installed in editable mode.
> Some changes, e.g. in `setup.cfg`, might require you to run `pip install -e .` again.


Optional and needed only once after `git clone`:

3. install [nbstripout] git hooks to remove the output cells of committed notebooks with:
   ```bash
   nbstripout --install --attributes notebooks/.gitattributes
   ```
   This is useful to avoid large diffs due to plots in your notebooks.
   A simple `nbstripout --uninstall` will revert these changes.


Then take a look into the `scripts` and `notebooks` folders.

## Dependency Management & Reproducibility

1. Always keep your abstract (unpinned) dependencies updated in `environment.yml` and eventually
   in `setup.cfg` if you want to ship and install your package via `pip` later on.
2. Create concrete dependencies as `environment.lock.yml` for the exact reproduction of your
   environment with:
   ```bash
   conda env export -n make_notes_dataset -f environment.lock.yml
   ```
   For multi-OS development, consider using `--no-builds` during the export.
3. Update your current environment with respect to a new `environment.lock.yml` using:
   ```bash
   conda env update -f environment.lock.yml --prune
   ```
## Project Organization

```
├── AUTHORS.md              <- List of developers and maintainers.
├── CHANGELOG.md            <- Changelog to keep track of new features and fixes.
├── CONTRIBUTING.md         <- Guidelines for contributing to this project.
├── Dockerfile              <- Build a docker container with `docker build .`.
├── LICENSE.txt             <- License as chosen on the command-line.
├── README.md               <- The top-level README for developers.
├── configs                 <- Directory for configurations of model & application.
├── docs                    <- Directory for Sphinx documentation in rst or md.
├── environment.yml         <- The conda environment file for reproducibility.
├── notebooks               <- Jupyter notebooks. Naming convention is a number (for
│                              ordering), the creator's initials and a description,
│                              e.g. `1.0-fw-initial-data-exploration`.
├── pyproject.toml          <- Build configuration. Don't change! Use `pip install -e .`
│                              to install for development or to build `tox -e build`.
├── references              <- Data dictionaries, manuals, and all other materials.
├── scripts                 <- Analysis and production scripts which import the
│                              actual PYTHON_PKG, e.g. train_model.
├── setup.cfg               <- Declarative configuration of your project.
├── setup.py                <- [DEPRECATED] Use `python setup.py develop` to install for
│                              development or `python setup.py bdist_wheel` to build.
└── src                     <- Actual Python package where the main functionality goes.
```

## Notebook description

This is a brief description of the notebooks in this repository.

* 0.EDA-checkMetaData.ipynb 
   - Investigate the column names, their contents, and the relevant metadata with clinical notes in the processed CSV files provided by CDI.
* 1.validation-DateInNote_vs_EPRdate.ipynb
   - Extract the date of visit from the clinical note, if possible, and compare it with the EPR date.
* 1.1-wy-EDA-missing-notes.ipynb
   - Obtain random sample of notes between January 1, 2008 and February 28, 2018 to calculate statistics on missingness with respect to EPR.
* 1.2-wy-EDA-plot-counts.ipynb
   - Produce plots to validate counts of clinical notes in the dataset.

## Procedure for cleaning the data set

* Visit date: Use date extracted from the clinical note, if possible. Otherwise, use EPR date. If extracted date is out of bounds, use EPR date instead. In general, the date extracted from the clinical note precedes the EPR date.

* Duplicates: Only drop duplicate clinical notes if job number can be extracted. For clinical notes with the same procedure name and same job number, only retain the clinical note with the most recent last updated date.

* Filtering patients to study period: Drop all records outside the study period. Drop patients whose first visit is outside the study period



<!-- pyscaffold-notes -->

## Note

This project has been set up using [PyScaffold] 4.5 and the [dsproject extension] 0.7.2.

[conda]: https://docs.conda.io/
[pre-commit]: https://pre-commit.com/
[Jupyter]: https://jupyter.org/
[nbstripout]: https://github.com/kynan/nbstripout
[Google style]: http://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings
[PyScaffold]: https://pyscaffold.org/
[dsproject extension]: https://github.com/pyscaffold/pyscaffoldext-dsproject
