"""Create durable LLM jobs for unprocessed articles (release step). Dry run unless --apply."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write the jobs; otherwise only count them')
    args = parser.parse_args(argv)
    with create_app().app_context():
        from app.llm import article_jobs
        count = article_jobs.backfill(apply=args.apply)
    print(f'{"Created" if args.apply else "Would create"} {count} article LLM jobs')


if __name__ == '__main__':
    main()
