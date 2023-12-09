#!/bin/sh

ruff check --show-fixes --no-fix src
ruff check --show-fixes --no-fix tests
ruff format --check src
ruff format --check tests
isort --check src
isort --check tests