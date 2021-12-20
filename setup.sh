#!/bin/bash

PYTHON_VERSION="3.7.3"
PROJECT_NAME="canyonlands"

pyenv install $PYTHON_VERSION -s

source virtualenvwrapper.sh

rmvirtualenv $PROJECT_NAME
mkvirtualenv \
    -a . \
    -p ~/.pyenv/versions/$PYTHON_VERSION/bin/python \
    -r requirements-dev.txt \
    $PROJECT_NAME

