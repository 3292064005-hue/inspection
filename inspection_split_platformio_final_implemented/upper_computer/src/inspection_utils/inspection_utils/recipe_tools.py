from __future__ import annotations
import argparse
from .config import load_yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('recipe')
    args = parser.parse_args()
    print(load_yaml(args.recipe))
