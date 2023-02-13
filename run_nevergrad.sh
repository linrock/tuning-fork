#!/bin/bash

mpiexec -np 12 python3 \
  -m mpi4py.futures nevergrad4sf.py \
  --tc "10000+10000 nodes=5000" \
  --games_per_batch 96 \
  --cutechess_concurrency 8 \
  --evaluation_concurrency 2 \
  --ng_evals 128
