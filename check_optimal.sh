#!/bin/bash

mpiexec -np 16 python3 -m mpi4py.futures cutechess_batches.py -tc 10+0.1 -g 1000 -cc 8
