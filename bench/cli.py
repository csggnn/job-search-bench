"""Command-line entry point: `bench <command>`."""

import argparse

from bench.config import load_config
from bench.prepare import ARMS, parse_setup, prepare
from bench.run import run
from bench.score import score


def main() -> None:
    parser = argparse.ArgumentParser(prog="bench")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser(
        "prepare", help="create isolated X/Y arms for one comparison"
    )
    prepare_parser.add_argument("tag", help="snapshot tag, bench/<feature>")
    prepare_parser.add_argument(
        "setups",
        nargs=2,
        metavar="SHA:LABEL",
        help="setup commit and a label naming it, e.g. 715c15d:cc-hook",
    )

    run_parser = commands.add_parser("run", help="run code generation headless in both arms")
    run_parser.add_argument("comparison", help="comparison id")
    run_parser.add_argument("--change", required=True, help="OpenSpec change to apply")
    run_parser.add_argument(
        "--skip-task",
        action="append",
        default=[],
        metavar="ID",
        help="task the arms leave undone, e.g. 5.2; repeatable",
    )

    score_parser = commands.add_parser("score", help="score both arms and write the results")
    score_parser.add_argument("comparison", help="comparison id")

    args = parser.parse_args()
    config = load_config()
    if args.command == "prepare":
        setups = dict(parse_setup(text) for text in args.setups)
        if len(setups) != len(args.setups):
            parser.error("setup labels must differ")
        comparison_id = prepare(config, args.tag, setups)
        run_dir = config.workspace / comparison_id
        print(f"comparison: {comparison_id}")
        for arm in ARMS:
            print(f"arm {arm}: source {run_dir / arm / 'env.sh'} && claude")
        print(f"judge: CLAUDE_CONFIG_DIR={run_dir / 'judge-config'} claude")
    elif args.command == "run":
        run(config, args.comparison, args.change, args.skip_task)
    else:
        for metrics in score(config, args.comparison):
            print(f"arm {metrics.arm}: {metrics.setup}")


if __name__ == "__main__":
    main()
