#!/bin/sh

ruff_check_src_code=$(ruff check --show-fixes --no-fix src)
ruff_check_tests_code=$(ruff check --show-fixes --no-fix tests)
ruff_format_src_code=$(ruff format --check src)
ruff_format_tests_code=$(ruff format --check tests)
isort_src_code=$(isort --check src)
isort_tests_code=$(isort --check tests)


if [ "$ruff_check_src_code" = "0" ] &
  [ "$ruff_check_tests_code" = "0" ] &
  [ "$ruff_format_src_code" = "0" ] &
  [ "$ruff_format_tests_code" = "0" ] &
  [ "$isort_src_code" = "0" ] &
  [ "$isort_tests_code" = "0" ]
then
  exit 0
else
  exit 1
fi
