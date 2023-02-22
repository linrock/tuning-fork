#!/bin/bash

stockfish quit
echo

mpi_concurrency=$(( $(nproc) / 8 ))
mpiexec -np $mpi_concurrency python3 \
  -m mpi4py.futures cutechess_batches.py \
  -tc "10000+10000 nodes=5000" \
  -g 20000 \
  -cc 8
