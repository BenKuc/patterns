#!/bin/sh

ruff check --fix src
ruff check --fix tests
ruff format src
ruff format tests
isort src
isort tests
