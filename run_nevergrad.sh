#!/bin/bash

mpiexec -np 12 python3 \
  -m mpi4py.futures nevergrad4sf.py \
  --cutechess cutechess-cli \
  --stockfish stockfish \
  --book UHO_XXL_+0.90_+1.19.epd \
  --tc 10+0.1 \
  --games_per_batch 48 \
  --cutechess_concurrency 8 \
  --evaluation_concurrency 3 \
  --ng_evals 100
