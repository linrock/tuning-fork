"""
Compute batches of chess games using cutechess.

The base functionality, provided by cutechess_local_batch essentially
calls cutechess with reasonable arguments and parses the output.
The more interesting version, cutechess_executor_batch, runs multiple
batches asynchronously, using an executor (which can be MPIPoolExecutor).
"""
from concurrent.futures import as_completed
from subprocess import Popen, PIPE
import sys
import math
import random
import re
import json
import argparse
from pprint import pprint
import textwrap

from mpi4py.futures import MPIPoolExecutor
from mpi4py import MPI
from scipy.stats import norm

from stats.sprt import sprt


def elo(score):
    """ convert a score into Elo"""
    epsilon = 1e-6
    score = max(epsilon, min(1 - epsilon, score))
    return -400.0 * math.log10(1.0 / score - 1.0)


def pentanomial_results(result_sequence):
    game_pair_results = []
    for i in range(0, len(result_sequence) - 1, 2):
        game_one, game_two = result_sequence[i], result_sequence[i + 1]
        game_pair_results.append(str(game_one) + str(game_two))
    category = [0, 0, 0, 0, 0]
    for game_pair in game_pair_results:
        if game_pair == "ll":
            category[0] += 1
        if game_pair in ["ld", "dl"]:
            category[1] += 1
        if game_pair in ["dd", "wl", "lw"]:
            category[2] += 1
        if game_pair in ["wd", "dw"]:
            category[3] += 1
        if game_pair == "ww":
            category[4] += 1
    return category


def calc_los(pentanomial):
    sumi, sumi2 = 0, 0
    for i, score in enumerate([0, 0.5, 1, 1.5, 2]):
        N = sum(pentanomial)
        sumi += pentanomial[i] * score / N
        sumi2 += pentanomial[i] * score * score / N
    sigma = math.sqrt(sumi2 - sumi * sumi)
    try:
        t0 = (sumi - 1) / sigma
    except ZeroDivisionError:
        t0 = sumi - 1
    los = norm.cdf(t0)
    return los


def calc_stats(result_sequence):
    """Given a list of "w" "l" "d", compute score, elo and LOS, with error estimates"""
    wld = [0, 0, 0]
    for r in result_sequence:
        if r == "w":
            wld[0] += 1
        if r == "l":
            wld[1] += 1
        if r == "d":
            wld[2] += 1

    games = sum(wld)
    score = (1.0 * wld[0] + 0.0 * wld[1] + 0.5 * wld[2]) / games
    devw = math.pow(1.0 - score, 2.0) * wld[0] / games
    devl = math.pow(0.0 - score, 2.0) * wld[1] / games
    devd = math.pow(0.5 - score, 2.0) * wld[2] / games
    stddev = math.sqrt(devw + devl + devd) / math.sqrt(games)

    if wld[0] != wld[1]:
        a = (wld[0] - wld[1]) / math.sqrt(wld[0] + wld[1])
    else:
        a = 0.0
    los = norm.cdf(a)

    pentanomial = pentanomial_results(result_sequence)
    fishtest_stats = sprt(alpha=0.05, beta=0.05, elo0=0, elo1=2.0, elo_model='normalized')
    fishtest_stats.set_state(pentanomial)

    return {
        "score": score,
        "score_error": 1.95716 * stddev,
        "ldw": [wld[1], wld[2], wld[0]],
        "ldw_los": 100 * los,
        "pentanomial": pentanomial,
        "pentanomial_los": 100 * calc_los(pentanomial),
        "Elo": elo(score),
        "Elo_error": (elo(score + 1.95716 * stddev) - elo(score - 1.95716 * stddev)) / 2,
        "fishtest_stats": fishtest_stats.analytics(p=0.05)
    }


class CutechessLocalBatch:
    """Compute a batch of games using cutechess"""

    def __init__(
        self,
        cutechess="./cutechess-cli",
        stockfish="./stockfish",
        stockfishRef="./stockfish",
        book="noob_3moves.epd",
        tc="10.0+1.0",
        tcRef="10.0+1.0",
        rounds=100,
        concurrency=2,
    ):
        """Basic properties of the batch of games can be specified"""
        self.cutechess = cutechess
        self.stockfish = stockfish
        self.stockfishRef = stockfishRef
        self.book = book
        self.tc = tc
        self.tcRef = tcRef
        self.rounds = rounds
        self.concurrency = concurrency
        self.total_games = 2 * rounds

    def run(self, variables):
        """Run a batch of games returning a list  containing 'w' 'l' 'd' results

        The results are show from the point of view of test, which is the version that is
        setup using the options set using the variables.
        """

        # The engine whose parameters will be optimized
        fcp = "name=test cmd=%s tc=%s" % (self.stockfish, self.tc)

        # The reference engine
        scp = "name=base cmd=%s tc=%s" % (self.stockfishRef, self.tcRef)

        # Parse the parameters that should be optimized
        for name in variables:
            # Make sure the parameter value is numeric
            try:
                float(variables[name])
            except ValueError:
                sys.exit(
                    "invalid value for parameter %s: %s\n" % (argv[i], argv[i + 1])
                )

            initstr = "option.{name}={value}".format(name=name, value=variables[name])
            fcp += ' "%s"' % initstr

        extension = None
        m = re.compile("(pgn|epd)$").search(self.book)
        if m:
            extension = m.group(1)

        if not extension:
            sys.exit("books must have epd or pgn extension: %s" % self.book)

        cutechess_base_args = (
            "-games 2 -repeat "
            + " -openings file=%s format=%s order=random" % (self.book, extension)
            + " -draw movenumber=50 movecount=8 score=5 -resign movecount=3 score=600"
        )
        cutechess_args = "-engine %s -engine %s -each proto=uci option.Hash=16 -rounds %d -concurrency %d -srand %d" % (
            fcp,
            scp,
            self.rounds,
            self.concurrency,
            random.SystemRandom().randint(0, 2 ** 31 - 1),
        )
        command = "%s %s %s" % (self.cutechess, cutechess_base_args, cutechess_args)

        # Run cutechess-cli and wait for it to finish
        process = Popen(command, shell=True, stdout=PIPE)
        output = process.communicate()[0]
        if process.returncode != 0:
            sys.exit("failed to execute command: %s\n" % command)

        # Convert Cutechess-cli's result into W/L/D (putting game pairs together)
        lines = []
        for line in output.decode("utf-8").splitlines():
            if line.startswith("Finished game"):
                lines.append(line)

        lines.sort(key=lambda l: float(l.split()[2]))

        # Convert cutechess-cli game results into a sequence of W/L/D from the test engine's perspective
        result_sequence = []
        for line in lines:
            if line.find(": 1-0") != -1:
                if line.find("test vs base") != -1:
                    result_sequence.append("w")
                if line.find("base vs test") != -1:
                    result_sequence.append("l")
            elif line.find(": 0-1") != -1:
                if line.find("test vs base") != -1:
                    result_sequence.append("l")
                if line.find("base vs test") != -1:
                    result_sequence.append("w")
            elif line.find(": 1/2-1/2") != -1:
                result_sequence.append("d")
            else:
                # ignore for now.
                print("The game did not terminate properly!")

        return result_sequence


class CutechessExecutorBatch:
    def __init__(
        self,
        cutechess="./cutechess-cli",
        stockfish="./stockfish",
        stockfishRef="./stockfish",
        book="noob_3moves.epd",
        tc="10.0+0.1",
        tcRef="10.0+0.1",
        rounds=2,
        concurrency=2,
        batches=1,
        executor=None,
    ):
        """Compute a batch of games using cutechess, specifying an executor

        The executor (e.g. MPIPoolExecutor) allows for concurrency, in evaluating batches
        """

        self.local_batch = CutechessLocalBatch(
            cutechess, stockfish, stockfishRef, book, tc, tcRef, rounds, concurrency
        )
        self.batches = batches
        self.total_games = self.batches * self.local_batch.total_games
        self.executor = executor

    def run(self, variables):
        """Run a batch of games returning a list containing 'w' 'l' 'd' results

        The results are shown from the point of view of test, which is the version that is
        setup using the options set using the variables.
        """
        score = []
        fs = []

        for i in range(0, self.batches):
            fs.append(self.executor.submit(self.local_batch.run, variables))

        for f in as_completed(fs):
            score = score + f.result()

        return score


# mpirun -np 3 python3 -m mpi4py.futures cutechess_batches.py
# will lauch 2 workers (1 master).
if __name__ == "__main__":

    class MyFormatter(
        argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter
    ):
        pass

    parser = argparse.ArgumentParser(
        formatter_class=MyFormatter,
        description=textwrap.dedent(
            """\
                  Compute batches of chess games using cutechess.

                  This program requires mpi to run. A typical invocation could be:
                     mpirun -np 3 python3 -m mpi4py.futures cutechess_batches.py -tc 1.0+0.01 -g 10000 -cc 8

                  More documentation at:
                     https://github.com/vondele/nevergrad4sf/blob/master/README.md

                  """
        ),
    )
    parser.add_argument(
        "--stockfish",
        type=str,
        default="stockfish",
        help="Name of the stockfish binary to which options can be passed",
    )
    parser.add_argument(
        "--stockfishRef",
        type=str,
        default=None,
        help="Name of reference engine, used without options. Default to the value of the --stockfish argument.",
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
        help="time control for reference, defaults to the argument of --tc",
    )
    parser.add_argument(
        "-g",
        "--games_per_batch",
        type=int,
        default=5000,
        help="Number of games per evaluation point",
    )
    parser.add_argument(
        "-cc",
        "--cutechess_concurrency",
        type=int,
        default=8,
        help="Number of concurrent games per cutechess worker",
    )
    parser.add_argument(
        "--parameters",
        type=str,
        default="optimal.json",
        help="A dictionary containingthe parameters at which evaluation should happen",
    )
    args = parser.parse_args()

    workers = MPI.COMM_WORLD.Get_size() - 1

    with open(args.parameters, "r") as infile:
        variables = json.load(infile)

    print(
        "Starting evaluation (%d games, tc %s) with %d workers for parameter set:"
        % (args.games_per_batch, args.tc, workers),
        flush=True,
    )
    print(variables, flush=True)

    batch = CutechessExecutorBatch(
        cutechess=args.cutechess,
        stockfish=args.stockfish,
        stockfishRef=args.stockfishRef if args.stockfishRef else args.stockfish,
        book=args.book,
        tc=args.tc,
        tcRef=args.tcRef if args.tcRef else args.tc,
        rounds=((args.games_per_batch + 1) // 2 + workers - 1) // workers,
        concurrency=args.cutechess_concurrency,
        batches=workers,
        executor=MPIPoolExecutor(),
    )
    results = batch.run(variables)
    pprint(calc_stats(results))
