#!/bin/bash

stockfish quit
echo
mpiexec -np 12 python3 \
  -m mpi4py.futures cutechess_batches.py \
  -tc "10000+10000 nodes=5000" \
  -g 10000 \
  -cc 4
