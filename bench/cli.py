"""Command-line entry point: `bench <command>`."""

import argparse

from bench.config import load_config
from bench.prepare import ARMS, prepare


def main() -> None:
    parser = argparse.ArgumentParser(prog="bench")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser(
        "prepare", help="create isolated X/Y arms for one comparison"
    )
    prepare_parser.add_argument("tag", help="snapshot tag, bench/<feature>")
    prepare_parser.add_argument("champion_sha", help="setup commit of the champion")
    prepare_parser.add_argument("candidate_sha", help="setup commit of the candidate")

    args = parser.parse_args()
    config = load_config()
    comparison_id = prepare(config, args.tag, args.champion_sha, args.candidate_sha)
    run_dir = config.workspace / comparison_id
    print(f"comparison: {comparison_id}")
    for arm in ARMS:
        print(f"arm {arm}: source {run_dir / arm / 'env.sh'} && claude")


if __name__ == "__main__":
    main()
