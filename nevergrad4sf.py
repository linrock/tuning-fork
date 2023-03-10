"""
Use nevergrad to optimize tunable stockfish parameters

Interfaces between nevergrad, cutechess, and stockfish to optimize
parameters marked for tuning in sf.

See https://github.com/vondele/nevergrad4sf/blob/master/README.md for details.
"""

import math
import sys
import os.path
import shutil
import datetime
import time
import argparse
import json
from pathlib import Path
from pprint import pprint
from subprocess import Popen, PIPE
import textwrap

import nevergrad as ng
from cutechess_batches import CutechessExecutorBatch, calc_stats
from mpi4py import MPI
from mpi4py.futures import MPIPoolExecutor
from concurrent.futures import ThreadPoolExecutor


def get_sf_parameters(stockfish_exe):
    """Run sf to obtain the tunable parameters"""

    process = Popen(stockfish_exe, shell=True, stdin=PIPE, stdout=PIPE)
    output = process.communicate(input=b"quit\n")[0]
    if process.returncode != 0:
        sys.stderr.write("get_sf_parameters: failed to execute command: %s\n" % command)
        sys.exit(1)

    # parse for parameter output
    params = {}
    for line in output.decode("utf-8").split("\n"):
        if "Stockfish" in line:
            continue
        if not "," in line:
            continue
        split_line = line.split(",")
        params[split_line[0]] = [
            int(split_line[1]),
            int(split_line[2]),
            int(split_line[3]),
        ]

    return params


def var2int(**variables):
    """Round variables to ints"""
    for name in variables:
        variables[name] = int(round(variables[name]))
    return variables


def ng4sf(
    stockfish,
    stockfishRef,
    cutechess,
    book,
    tc,
    tcRef,
    nevergrad_evals,
    do_restart,
    games_per_batch,
    batch_increase_per_iter,
    cutechess_concurrency,
    evaluation_concurrency,
    output_dir,
):
    """
    nevergrad for sf: optimize parameters in a tuning enabled stockfish.

    specify binary names, tc, number of points to evaluate, restart or not,
    games per batch, cutechess concurrency, and evaluation batch concurrency
    """

    # ready to run with mpi
    size = MPI.COMM_WORLD.Get_size()
    print()
    if size > 1:
        print(f"Launched ... with {size} mpi ranks (1 master, {size - 1} workers).")
        print(flush=True)
    else:
        sys.stderr.write("ng4sf needs to run under mpi with at least 2 MPI ranks.\n")
        sys.exit(1)

    # print summary
    print("stockfish binary                          : ", stockfish)
    print("stockfish reference binary                : ", stockfishRef)
    print("cutechess binary                          : ", cutechess)
    print("book                                      : ", book)
    print("time control                              : ", tc)
    print("time control reference binary             : ", tcRef)
    print("restart                                   : ", do_restart)
    print("nevergrad batch evaluations               : ", nevergrad_evals)
    print("initial batch size in games               : ", games_per_batch)
    print("batch size increase per ng iteration      : ", batch_increase_per_iter)
    print("cutechess concurrency                     : ", cutechess_concurrency)
    print("batch evaluation concurrency:             : ", evaluation_concurrency)
    print("output dir:                               : ", output_dir)
    print(flush=True)

    # get info from sf
    sf_params = get_sf_parameters(stockfish)
    print(
        "About to optimize the following %d %s:"
        % (
            len(sf_params),
            "parameter" if len(sf_params) == 1 else "parameters",
        )
    )
    pprint(sf_params)
    print(flush=True)

    # our choice of making mpi_subbatches, i.e. mpi processes per batch (this could be tunable for performance?)
    mpi_subbatches = 2 * (
        (size - 1 + evaluation_concurrency - 1) // evaluation_concurrency
    )

    # creating the batch
    def create_cutechess_executor_batch(games_per_batch):
        return CutechessExecutorBatch(
            cutechess=cutechess,
            stockfish=stockfish,
            stockfishRef=stockfishRef,
            book=book,
            tc=tc,
            tcRef=tcRef,
            rounds=((games_per_batch + 1) // 2 + mpi_subbatches - 1) // mpi_subbatches,
            concurrency=cutechess_concurrency,
            batches=mpi_subbatches,
            executor=MPIPoolExecutor(),
        )

    batch = create_cutechess_executor_batch(games_per_batch)

    # paths for experiment output files
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    restart_file_path = str(Path(output_dir, "ng_restart.pkl"))
    all_evalpoints_file_path = str(Path(output_dir, "all_evalpoints.json"))
    all_optimals_file_path = str(Path(output_dir, "all_optimals.json"))
    last_optimal_file_path = str(Path(output_dir, "optimal.json"))

    # Create a dictionary describing to nevergrad the variables of our black box function
    variables = {}
    for v in sf_params:
        if (
            sf_params[v][1] != sf_params[v][2]
        ):  # Let equal bounds imply fixed not a parameter.
            variables[v] = (
                ng.p.Scalar(init=float(sf_params[v][0]))
                .set_bounds(
                    lower=float(sf_params[v][1]),
                    upper=float(sf_params[v][2]),
                    method="constraint",
                )
                .set_mutation(
                    sigma=(float(sf_params[v][2]) - float(sf_params[v][1])) / 4
                )
            )

    # init ng optimizer, restarting as hardcoded
    instrum = ng.p.Instrumentation(**variables)
    if not do_restart:
        optimizer = ng.optimizers.TBPSA(
            parametrization=instrum,
            budget=nevergrad_evals,
            num_workers=evaluation_concurrency,
        )
    else:
        if os.path.isfile(restart_file_path):
            optimizer = ng.optimizers.TBPSA.load(restart_file_path)
        else:
            sys.exit(f"Missing restart file: {restart_file_path}\n")

    start_time = datetime.datetime.now()

    # with this executor, we can parallelize over evaluation_concurrency.
    executor = ThreadPoolExecutor(max_workers=evaluation_concurrency)
    evalpoints = []
    evalpoints_submitted = 0
    evalpoints_running = 0
    for i in range(evaluation_concurrency):
        x = optimizer.ask()
        print(f'optimizer.ask() got params. running batch...')
        evalpoints.append([x, executor.submit(batch.run, var2int(*x.args, **x.kwargs))])
        time.sleep(0.1)  # try to give some time to submit all batches of this point
        evalpoints_submitted = evalpoints_submitted + 1
        evalpoints_running = evalpoints_running + 1

    ng_iter = 0
    eval_of_last_ng_iter = 0
    previous_recommendation = None
    total_games_played = 0
    all_optimals = []
    all_evalpoints = []
    games_accumulator = {}

    # optimizer loop
    while evalpoints_running > 0:

        # find the point which is ready
        ready_batch = -1
        while ready_batch == -1:
            time.sleep(0.1)
            for i in range(evaluation_concurrency):
                if evalpoints[i][1].done():
                    ready_batch = i
                    evalpoints_running = evalpoints_running - 1
                    break

        # use this point to inform the optimizer.
        x = evalpoints[ready_batch][0]
        wld_game_results = evalpoints[ready_batch][1].result()
        num_games_played = len(wld_game_results)
        total_games_played += num_games_played

        params_evaluated = var2int(**x.kwargs)
        params_evaluated = {key: params_evaluated[key] for key in sorted(params_evaluated)}
        params_evaluated_key = str(params_evaluated)

        # accumulate games from the same point so SPRT LLR can give better data
        combined_game_results = wld_game_results.copy()
        if games_accumulator.get(params_evaluated_key):
            prev_game_results = games_accumulator[params_evaluated_key]
            print(f'Found previous evaluation of same point. Adding {len(prev_game_results)} game results')
            combined_game_results.extend(prev_game_results)
        games_accumulator[params_evaluated_key] = combined_game_results.copy()

        stats = calc_stats(combined_game_results)
        # loss = (100 - stats["pentanomial_los"]) / 100.0
        loss = -stats["fishtest_stats"]["LLR"]              # maximize SPRT LLR measured from pentanomial results
        optimizer.tell(x, loss)

        current_time = datetime.datetime.now()
        used_time = current_time - start_time
        evals_done = evalpoints_submitted - evalpoints_running
        a = stats["fishtest_stats"]

        print(f"evaluation: {evals_done} of {nevergrad_evals} (worker {ready_batch+1} of {evaluation_concurrency}, games played: {num_games_played}) ng iter: {ng_iter}, total: {total_games_played} games in {used_time.total_seconds():.3f}s, games/s: {total_games_played / used_time.total_seconds():.3f}")
        print(params_evaluated)
        print(f'   games considered      :   {len(combined_game_results)}')
        print(f'   score                 : {stats["score"] * 100:8.3f} +- {stats["score_error"] * 100:8.3f}')
        print(f'   elo                   : {stats["Elo"]:8.3f} +- {stats["Elo_error"]:8.3f}')
        print(f'   ldw                   :   {str(stats["ldw"]):24}   {stats["ldw_los"]:4.2f}% LOS')
        print(f'   pentanomial           :   {str(stats["pentanomial"]):24}   {stats["pentanomial_los"]:4.2f}% LOS')
        print(f'   LLR [-2.94, 2.94]     : {a["LLR"]:7.2f}                      {a["LOS"]:4.2%} LOS')
        # print("   Elo                   :   {:.2f}".format(a["elo"]))
        # print("   Confidence interval   :   [{:.2f},{:.2f}] (95%)".format(a["ci"][0], a["ci"][1]))
        print(f"   loss                  : {loss:11.6f}")

        # make a backup of the old restart and dump current state
        if os.path.exists(restart_file_path):
            shutil.move(restart_file_path, f"{restart_file_path}.bak")
        optimizer.dump(restart_file_path)

        # export data to json files after each evaluation
        all_evalpoints.append({
            'params': x.kwargs,
            'num_games': num_games_played,
            'stats': stats
        })
        with open(all_evalpoints_file_path, "w") as outfile:
            json.dump(all_evalpoints, outfile, indent=2)

        recommendation = var2int(**optimizer.provide_recommendation().kwargs)
        if recommendation != previous_recommendation:
            ng_iter = ng_iter + 1
            eval_str = "evaluation" if evals_done == 1 else "evaluations"
            print()
            print(f"------- optimal at iter {ng_iter} after {evals_done} {eval_str} and {total_games_played} games : ")
            pprint(recommendation)
            print()
            print(f"Spent {evals_done - eval_of_last_ng_iter} evaluations for this ng iteration")
            eval_of_last_ng_iter = evals_done

            # export optimal recommendations data to json files
            all_optimals.append({
                "evals_done": evals_done,
                "recommendation": recommendation
            })
            with open(all_optimals_file_path, "w") as outfile:
                json.dump(all_optimals_file_path, outfile, indent=2)
            with open(last_optimal_file_path, "w") as outfile:
                json.dump(recommendation, outfile, indent=2)

            # increase the games per batch after each iteration beyond the first
            if ng_iter > 1 and batch_increase_per_iter > 0:
                games_per_batch += batch_increase_per_iter
                print(f'Increasing games per batch by {batch_increase_per_iter} to: {games_per_batch}')
                batch = create_cutechess_executor_batch(games_per_batch)

            print('-------')

        # queue the next point for evaluation.
        if evalpoints_submitted < nevergrad_evals:
            x = optimizer.ask()
            evalpoints[ready_batch] = [
                x,
                executor.submit(batch.run, var2int(*x.args, **x.kwargs)),
            ]
            evalpoints_submitted = evalpoints_submitted + 1
            evalpoints_running = evalpoints_running + 1

        print(flush=True)
        previous_recommendation = recommendation

    print("Parameter optimization inputs:")
    print(sf_params)
    print(f"Optimization finished with optimal parameters (ng iteration: {ng_iter}) :")
    pprint(recommendation)


if __name__ == "__main__":

    class MyFormatter(
        argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter
    ):
        pass

    parser = argparse.ArgumentParser(
        formatter_class=MyFormatter,
        description=textwrap.dedent(
            """\
                  Use nevergrad to optimize tunable stockfish parameters.

                  This program requires mpi to run. A typical invocation could be:
                     mpirun -np 3 python3 -m mpi4py.futures nevergrad4sf.py -tc 1.0+0.01 -g 2 -cc 2 -ec 3 --ng 10

                  More documentation at:
                     https://github.com/vondele/nevergrad4sf/blob/master/README.md

                  """
        ),
    )
    parser.add_argument(
        "--stockfish",
        type=str,
        default="stockfish",
        help="Name of the stockfish binary to be optimized",
    )
    parser.add_argument(
        "--stockfishRef",
        type=str,
        default=None,
        help="Optional, name of the reference stockfish binary to be used, defaults to the --stockfish argument.",
    )
    parser.add_argument(
        "--cutechess",
        type=str,
        default="cutechess-cli",
        help="Name of the cutechess binary",
    )
    parser.add_argument(
        "--book",
        type=str,
        default="./UHO_XXL_+0.90_+1.19.epd",
        help="opening book in epd or pgn fomat",
    )
    parser.add_argument(
        "-tc", "--tc", type=str, default="10.0+0.1", help="time control"
    )
    parser.add_argument(
        "-tcRef",
        "--tcRef",
        type=str,
        default=None,
        help="time control of the reference stockfish, defaults to the --tc argument.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="",
        help="Directory for output experiment data files",
    )
    parser.add_argument(
        "-g",
        "--games_per_batch",
        type=int,
        default=256,
        help="Number of games per evaluation point",
    )
    parser.add_argument(
        "-b",
        "--batch_increase_per_iter",
        type=int,
        default=64,
        help="Increase in number of games per evaluation after each nevergrad iteration",
    )
    parser.add_argument(
        "-cc",
        "--cutechess_concurrency",
        type=int,
        default=8,
        help="Number of concurrent games per cutechess worker",
    )
    parser.add_argument(
        "-ec",
        "--evaluation_concurrency",
        type=int,
        default=3,
        help="Number of concurrently evaluated points",
    )
    parser.add_argument(
        "-ng",
        "--ng_evals",
        type=int,
        default=10000,
        help="Number of nevergrad evaluation points",
    )
    parser.add_argument(
        "--restart", action="store_true", help="Restart a previous optimization"
    )
    args = parser.parse_args()

    ng4sf(
        args.stockfish,
        args.stockfishRef if args.stockfishRef else args.stockfish,
        args.cutechess,
        args.book,
        args.tc,
        args.tcRef if args.tcRef else args.tc,
        args.ng_evals,
        args.restart,
        args.games_per_batch,
        args.batch_increase_per_iter,
        args.cutechess_concurrency,
        args.evaluation_concurrency,
        args.output_dir,
    )
