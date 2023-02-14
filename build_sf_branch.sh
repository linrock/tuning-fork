#!/bin/bash
set -eu -o pipefail
if [ "$#" -ne 1 ]; then
  echo "Usage: ./build_sf_branch.sh <branch_name>"
  exit
fi

cd stockfish/src
git checkout -t origin/$1
make -j profile-build ARCH=x86-64-bmi2
