#!/bin/bash

mpiexec -np 8 python3 \
  -m mpi4py.futures nevergrad4sf.py \
  --output_dir ./ng-tuning \
  --tc "10000+10000 nodes=5000" \
  --games_per_batch 256 \
  --batch_increase_per_iter 64 \
  --cutechess_concurrency 8 \
  --evaluation_concurrency 3 \
  --ng_evals 256
