from retriever import benchmark_indexing, benchmark_querying
from reader import benchmark_reader
from utils import load_config
import argparse

params, filenames = load_config(config_filename="config.json", ci=True)

parser = argparse.ArgumentParser()

parser.add_argument('--reader', default=False, action="store_true",
                    help='Perform Reader benchmarks')
parser.add_argument('--retriever_index', default=False, action="store_true",
                    help='Perform Retriever indexing benchmarks')
parser.add_argument('--retriever_query', default=False, action="store_true",
                    help='Perform Retriever querying benchmarks')
parser.add_argument('--ci', default=False, action="store_true",
                    help='Perform a smaller subset of benchmarks that are quicker to run')

args = parser.parse_args()

if args.retriever_index:
    benchmark_indexing(**params, **filenames, ci=args.ci)
if args.retriever_query:
    benchmark_querying(**params, **filenames, ci=args.ci)
if args.retriever_reader:
    benchmark_reader(**params, **filenames, ci=args.ci)

