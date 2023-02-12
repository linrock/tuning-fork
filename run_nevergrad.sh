#!/bin/bash

mpiexec -np 12 python3 \
  -m mpi4py.futures nevergrad4sf.py \
  --tc "10000+10000 depth=16" \
  --games_per_batch 96 \
  --cutechess_concurrency 4 \
  --evaluation_concurrency 1 \
  --ng_evals 100
