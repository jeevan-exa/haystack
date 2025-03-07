import logging
from abc import abstractmethod
from typing import List
from functools import wraps
from time import perf_counter


from haystack import Document, BaseComponent

logger = logging.getLogger(__name__)


class BaseDocumentClassifier(BaseComponent):
    outgoing_edges = 1
    query_count = 0
    query_time = 0

    @abstractmethod
    def predict(self, documents: List[Document]):
        pass

    def run(self, query: str, documents: List[Document]): # type: ignore
        self.query_count += 1
        if documents:
            predict = self.timing(self.predict, "query_time")
            results = predict(documents=documents)
        else:
            results = []

        document_ids = [doc.id for doc in results]
        logger.debug(f"Retrieved documents with IDs: {document_ids}")
        output = {"documents": results}

        return output, "output_1"

    def timing(self, fn, attr_name):
        """Wrapper method used to time functions. """
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if attr_name not in self.__dict__:
                self.__dict__[attr_name] = 0
            tic = perf_counter()
            ret = fn(*args, **kwargs)
            toc = perf_counter()
            self.__dict__[attr_name] += toc - tic
            return ret
        return wrapper

    def print_time(self):
        print("Classifier (Speed)")
        print("---------------")
        if not self.query_count:
            print("No querying performed via Classifier.run()")
        else:
            print(f"Queries Performed: {self.query_count}")
            print(f"Query time: {self.query_time}s")
            print(f"{self.query_time / self.query_count} seconds per query")