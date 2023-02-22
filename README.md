## Tuning fork

Linux container for tuning stockfish params with [nevergrad](https://github.com/facebookresearch/nevergrad) TBPSA via a modified version of [nevergrad4sf](https://github.com/vondele/nevergrad4sf). The objective function uses SPRT LLR calculated from pentanomial game results. This appears to reduce the compute needed to converge on good parameters during optimization.

To use, either start a docker container and attach to its shell or reference `./Dockerfile` to set up a local environment.

```bash
docker compose up --build -d
docker exec -it tuning-fork bash
./run_nevergrad.sh
```

### Resources

https://github.com/vondele/nevergrad4sf
https://github.com/facebookresearch/nevergrad
https://github.com/glinscott/fishtest/tree/master/server/fishtest/stats