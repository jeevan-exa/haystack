from pathlib import Path

import json
import math
import pytest

from haystack.document_store.elasticsearch import ElasticsearchDocumentStore
from haystack.pipeline import (
    JoinDocuments,
    Pipeline,
    FAQPipeline,
    DocumentSearchPipeline,
    RootNode,
    SklearnQueryClassifier,
    TransformersQueryClassifier,
    MostSimilarDocumentsPipeline,
)
from haystack.reader import FARMReader
from haystack.retriever.dense import DensePassageRetriever
from haystack.retriever.sparse import ElasticsearchRetriever
from haystack.schema import Document


@pytest.mark.elasticsearch
@pytest.mark.parametrize("document_store", ["elasticsearch"], indirect=True)
def test_load_and_save_yaml(document_store, tmp_path):
    # test correct load of indexing pipeline from yaml
    pipeline = Pipeline.load_from_yaml(
        Path(__file__).parent/"samples"/"pipeline"/"test_pipeline.yaml", pipeline_name="indexing_pipeline"
    )
    pipeline.run(
        file_paths=Path(__file__).parent/"samples"/"pdf"/"sample_pdf_1.pdf",
        params={"Retriever": {"top_k": 10}, "Reader": {"top_k": 3}},
    )
    # test correct load of query pipeline from yaml
    pipeline = Pipeline.load_from_yaml(
        Path(__file__).parent/"samples"/"pipeline"/"test_pipeline.yaml", pipeline_name="query_pipeline"
    )
    prediction = pipeline.run(
        query="Who made the PDF specification?", params={"Retriever": {"top_k": 10}, "Reader": {"top_k": 3}}
    )
    assert prediction["query"] == "Who made the PDF specification?"
    assert prediction["answers"][0].answer == "Adobe Systems"
    assert "_debug" not in prediction.keys()

    # test invalid pipeline name
    with pytest.raises(Exception):
        Pipeline.load_from_yaml(
            path=Path(__file__).parent/"samples"/"pipeline"/"test_pipeline.yaml", pipeline_name="invalid"
        )
    # test config export
    pipeline.save_to_yaml(tmp_path / "test.yaml")
    with open(tmp_path / "test.yaml", "r", encoding="utf-8") as stream:
        saved_yaml = stream.read()
    expected_yaml = """
        components:
        - name: ESRetriever
          params:
            document_store: ElasticsearchDocumentStore
          type: ElasticsearchRetriever
        - name: ElasticsearchDocumentStore
          params:
            index: haystack_test
            label_index: haystack_test_label
          type: ElasticsearchDocumentStore
        - name: Reader
          params:
            model_name_or_path: deepset/roberta-base-squad2
            no_ans_boost: -10
          type: FARMReader
        pipelines:
        - name: query
          nodes:
          - inputs:
            - Query
            name: ESRetriever
          - inputs:
            - ESRetriever
            name: Reader
          type: Pipeline
        version: '0.8'
    """
    assert saved_yaml.replace(" ", "").replace("\n", "") == expected_yaml.replace(
        " ", ""
    ).replace("\n", "")


@pytest.mark.elasticsearch
@pytest.mark.parametrize("document_store_with_docs", ["elasticsearch"], indirect=True)
def test_debug_attributes_global(document_store_with_docs, tmp_path):

    es_retriever = ElasticsearchRetriever(document_store=document_store_with_docs)
    reader = FARMReader(model_name_or_path="deepset/roberta-base-squad2")

    pipeline = Pipeline()
    pipeline.add_node(component=es_retriever, name="ESRetriever", inputs=["Query"])
    pipeline.add_node(component=reader, name="Reader", inputs=["ESRetriever"])

    prediction = pipeline.run(
        query="Who lives in Berlin?",
        params={"ESRetriever": {"top_k": 10}, "Reader": {"top_k": 3}},
        debug=True,
        debug_logs=True
    )
    assert "_debug" in prediction.keys()
    assert "ESRetriever" in prediction["_debug"].keys()
    assert "Reader" in prediction["_debug"].keys()
    assert "input" in prediction["_debug"]["ESRetriever"].keys()
    assert "output" in prediction["_debug"]["ESRetriever"].keys()
    assert "input" in prediction["_debug"]["Reader"].keys()
    assert "output" in prediction["_debug"]["Reader"].keys()
    assert prediction["_debug"]["ESRetriever"]["input"]
    assert prediction["_debug"]["ESRetriever"]["output"]
    assert prediction["_debug"]["Reader"]["input"]
    assert prediction["_debug"]["Reader"]["output"]

    # Avoid circular reference: easiest way to detect those is to use json.dumps
    json.dumps(prediction, default=str)

@pytest.mark.elasticsearch
@pytest.mark.parametrize("document_store_with_docs", ["elasticsearch"], indirect=True)
def test_debug_attributes_per_node(document_store_with_docs, tmp_path):

    es_retriever = ElasticsearchRetriever(document_store=document_store_with_docs)
    reader = FARMReader(model_name_or_path="deepset/roberta-base-squad2")

    pipeline = Pipeline()
    pipeline.add_node(component=es_retriever, name="ESRetriever", inputs=["Query"])
    pipeline.add_node(component=reader, name="Reader", inputs=["ESRetriever"])

    prediction = pipeline.run(
        query="Who lives in Berlin?",
        params={
            "ESRetriever": {"top_k": 10, "debug": True, "debug_logs":True},
            "Reader": {"top_k": 3}
        },
    )
    assert "_debug" in prediction.keys()
    assert "ESRetriever" in prediction["_debug"].keys()
    assert "Reader" not in prediction["_debug"].keys()
    assert "input" in prediction["_debug"]["ESRetriever"].keys()
    assert "output" in prediction["_debug"]["ESRetriever"].keys()
    assert prediction["_debug"]["ESRetriever"]["input"]
    assert prediction["_debug"]["ESRetriever"]["output"]

    # Avoid circular reference: easiest way to detect those is to use json.dumps
    json.dumps(prediction, default=str)


@pytest.mark.elasticsearch
@pytest.mark.parametrize("document_store_with_docs", ["elasticsearch"], indirect=True)
def test_global_debug_attributes_override_node_ones(document_store_with_docs, tmp_path):

    es_retriever = ElasticsearchRetriever(document_store=document_store_with_docs)
    reader = FARMReader(model_name_or_path="deepset/roberta-base-squad2")

    pipeline = Pipeline()
    pipeline.add_node(component=es_retriever, name="ESRetriever", inputs=["Query"])
    pipeline.add_node(component=reader, name="Reader", inputs=["ESRetriever"])

    prediction = pipeline.run(
        query="Who lives in Berlin?",
        params={
            "ESRetriever": {"top_k": 10, "debug": True, "debug_logs":True},
            "Reader": {"top_k": 3, "debug": True}
        },
        debug=False
    )
    assert "_debug" not in prediction.keys()

    prediction = pipeline.run(
        query="Who lives in Berlin?",
        params={
            "ESRetriever": {"top_k": 10, "debug": False},
            "Reader": {"top_k": 3, "debug": False}
        },
        debug=True
    )
    assert "_debug" in prediction.keys()
    assert "ESRetriever" in prediction["_debug"].keys()
    assert "Reader" in prediction["_debug"].keys()
    assert "input" in prediction["_debug"]["ESRetriever"].keys()
    assert "output" in prediction["_debug"]["ESRetriever"].keys()
    assert "input" in prediction["_debug"]["Reader"].keys()
    assert "output" in prediction["_debug"]["Reader"].keys()
    assert prediction["_debug"]["ESRetriever"]["input"]
    assert prediction["_debug"]["ESRetriever"]["output"]
    assert prediction["_debug"]["Reader"]["input"]
    assert prediction["_debug"]["Reader"]["output"]



# @pytest.mark.slow
# @pytest.mark.elasticsearch
# @pytest.mark.parametrize(
#     "retriever_with_docs, document_store_with_docs",
#     [("elasticsearch", "elasticsearch")],
#     indirect=True,
# )
@pytest.mark.parametrize(
    "retriever_with_docs,document_store_with_docs",
    [
        ("dpr", "elasticsearch"),
        ("dpr", "faiss"),
        ("dpr", "memory"),
        ("dpr", "milvus"),
        ("embedding", "elasticsearch"),
        ("embedding", "faiss"),
        ("embedding", "memory"),
        ("embedding", "milvus"),
        ("elasticsearch", "elasticsearch"),
        ("es_filter_only", "elasticsearch"),
        ("tfidf", "memory"),
    ],
    indirect=True,
)
def test_graph_creation(retriever_with_docs, document_store_with_docs):
    pipeline = Pipeline()
    pipeline.add_node(name="ES", component=retriever_with_docs, inputs=["Query"])

    with pytest.raises(AssertionError):
        pipeline.add_node(
            name="Reader", component=retriever_with_docs, inputs=["ES.output_2"]
        )

    with pytest.raises(AssertionError):
        pipeline.add_node(
            name="Reader", component=retriever_with_docs, inputs=["ES.wrong_edge_label"]
        )

    with pytest.raises(Exception):
        pipeline.add_node(
            name="Reader", component=retriever_with_docs, inputs=["InvalidNode"]
        )

    with pytest.raises(Exception):
        pipeline = Pipeline()
        pipeline.add_node(
            name="ES", component=retriever_with_docs, inputs=["InvalidNode"]
        )


def test_invalid_run_args():
    pipeline = Pipeline.load_from_yaml(
        Path(__file__).parent/"samples"/"pipeline"/"test_pipeline.yaml", pipeline_name="query_pipeline"
    )
    with pytest.raises(Exception) as exc:
        pipeline.run(params={"ESRetriever": {"top_k": 10}})
    assert "run() missing 1 required positional argument: 'query'" in str(exc.value)

    with pytest.raises(Exception) as exc:
        pipeline.run(invalid_query="Who made the PDF specification?", params={"ESRetriever": {"top_k": 10}})
    assert "run() got an unexpected keyword argument 'invalid_query'" in str(exc.value)

    with pytest.raises(Exception) as exc:
        pipeline.run(query="Who made the PDF specification?", params={"ESRetriever": {"invalid": 10}})
    assert "Invalid parameter 'invalid' for the node 'ESRetriever'" in str(exc.value)


@pytest.mark.parametrize(
    "retriever,document_store",
    [
        ("embedding", "memory"),
        ("embedding", "faiss"),
        ("embedding", "milvus"),
        ("embedding", "elasticsearch"),
    ],
    indirect=True,
)
def test_faq_pipeline(retriever, document_store):
    documents = [
        {
            "content": "How to test module-1?",
            "meta": {"source": "wiki1", "answer": "Using tests for module-1"},
        },
        {
            "content": "How to test module-2?",
            "meta": {"source": "wiki2", "answer": "Using tests for module-2"},
        },
        {
            "content": "How to test module-3?",
            "meta": {"source": "wiki3", "answer": "Using tests for module-3"},
        },
        {
            "content": "How to test module-4?",
            "meta": {"source": "wiki4", "answer": "Using tests for module-4"},
        },
        {
            "content": "How to test module-5?",
            "meta": {"source": "wiki5", "answer": "Using tests for module-5"},
        },
    ]

    document_store.write_documents(documents)
    document_store.update_embeddings(retriever)

    pipeline = FAQPipeline(retriever=retriever)

    output = pipeline.run(query="How to test this?", params={"top_k": 3})
    assert len(output["answers"]) == 3
    assert output["query"].startswith("How to")
    assert output["answers"][0].answer.startswith("Using tests")

    if isinstance(document_store, ElasticsearchDocumentStore):
        output = pipeline.run(query="How to test this?", params={"filters": {"source": ["wiki2"]}, "top_k": 5})
        assert len(output["answers"]) == 1


@pytest.mark.parametrize("retriever_with_docs", ["embedding"], indirect=True)
def test_document_search_pipeline(retriever, document_store):
    documents = [
        {"content": "Sample text for document-1", "meta": {"source": "wiki1"}},
        {"content": "Sample text for document-2", "meta": {"source": "wiki2"}},
        {"content": "Sample text for document-3", "meta": {"source": "wiki3"}},
        {"content": "Sample text for document-4", "meta": {"source": "wiki4"}},
        {"content": "Sample text for document-5", "meta": {"source": "wiki5"}},
    ]

    document_store.write_documents(documents)
    document_store.update_embeddings(retriever)

    pipeline = DocumentSearchPipeline(retriever=retriever)
    output = pipeline.run(query="How to test this?", params={"top_k": 4})
    assert len(output.get("documents", [])) == 4

    if isinstance(document_store, ElasticsearchDocumentStore):
        output = pipeline.run(query="How to test this?", params={"filters": {"source": ["wiki2"]}, "top_k": 5})
        assert len(output["documents"]) == 1


@pytest.mark.elasticsearch
@pytest.mark.parametrize("document_store_with_docs", ["elasticsearch"], indirect=True)
@pytest.mark.parametrize("reader", ["farm"], indirect=True)
def test_join_document_pipeline(document_store_with_docs, reader):
    es = ElasticsearchRetriever(document_store=document_store_with_docs)
    dpr = DensePassageRetriever(
        document_store=document_store_with_docs,
        query_embedding_model="facebook/dpr-question_encoder-single-nq-base",
        passage_embedding_model="facebook/dpr-ctx_encoder-single-nq-base",
        use_gpu=False,
    )
    document_store_with_docs.update_embeddings(dpr)

    query = "Where does Carla live?"

    # test merge without weights
    join_node = JoinDocuments(join_mode="merge")
    p = Pipeline()
    p.add_node(component=es, name="R1", inputs=["Query"])
    p.add_node(component=dpr, name="R2", inputs=["Query"])
    p.add_node(component=join_node, name="Join", inputs=["R1", "R2"])
    results = p.run(query=query)
    assert len(results["documents"]) == 3

    # test merge with weights
    join_node = JoinDocuments(join_mode="merge", weights=[1000, 1], top_k_join=2)
    p = Pipeline()
    p.add_node(component=es, name="R1", inputs=["Query"])
    p.add_node(component=dpr, name="R2", inputs=["Query"])
    p.add_node(component=join_node, name="Join", inputs=["R1", "R2"])
    results = p.run(query=query)
    assert math.isclose(results["documents"][0].score, 0.5350644373470798, rel_tol=0.0001)
    assert len(results["documents"]) == 2

    # test concatenate
    join_node = JoinDocuments(join_mode="concatenate")
    p = Pipeline()
    p.add_node(component=es, name="R1", inputs=["Query"])
    p.add_node(component=dpr, name="R2", inputs=["Query"])
    p.add_node(component=join_node, name="Join", inputs=["R1", "R2"])
    results = p.run(query=query)
    assert len(results["documents"]) == 3

    # test join_node with reader
    join_node = JoinDocuments()
    p = Pipeline()
    p.add_node(component=es, name="R1", inputs=["Query"])
    p.add_node(component=dpr, name="R2", inputs=["Query"])
    p.add_node(component=join_node, name="Join", inputs=["R1", "R2"])
    p.add_node(component=reader, name="Reader", inputs=["Join"])
    results = p.run(query=query)
    #check whether correct answer is within top 2 predictions
    assert results["answers"][0].answer == "Berlin" or results["answers"][1].answer == "Berlin"


def test_debug_info_propagation():
    class A(RootNode):
        def run(self):
            test = "A"
            return {"test": test, "_debug": {"debug_key_a": "debug_value_a"}}, "output_1"

    class B(RootNode):
        def run(self, test):
            test += "B"
            return {"test": test, "_debug": {"debug_key_b": "debug_value_b"}}, "output_1"

    class C(RootNode):
        def run(self, test):
            test += "C"
            return {"test": test}, "output_1"

    class D(RootNode):
        def run(self, test, _debug):
            test += "C"
            assert _debug["B"]["debug_key_b"] == "debug_value_b"
            return {"test": test}, "output_1"

    pipeline = Pipeline()
    pipeline.add_node(name="A", component=A(), inputs=["Query"])
    pipeline.add_node(name="B", component=B(), inputs=["A"])
    pipeline.add_node(name="C", component=C(), inputs=["B"])
    pipeline.add_node(name="D", component=D(), inputs=["C"])
    output = pipeline.run(query="test")
    assert output["_debug"]["A"]["debug_key_a"] == "debug_value_a"
    assert output["_debug"]["B"]["debug_key_b"] == "debug_value_b"


def test_parallel_paths_in_pipeline_graph():
    class A(RootNode):
        def run(self):
            test = "A"
            return {"test": test}, "output_1"

    class B(RootNode):
        def run(self, test):
            test += "B"
            return {"test": test}, "output_1"

    class C(RootNode):
        def run(self, test):
            test += "C"
            return {"test": test}, "output_1"

    class D(RootNode):
        def run(self, test):
            test += "D"
            return {"test": test}, "output_1"

    class E(RootNode):
        def run(self, test):
            test += "E"
            return {"test": test}, "output_1"

    class JoinNode(RootNode):
        def run(self, inputs):
            test = (
                inputs[0]["test"] + inputs[1]["test"]
            )
            return {"test": test}, "output_1"

    pipeline = Pipeline()
    pipeline.add_node(name="A", component=A(), inputs=["Query"])
    pipeline.add_node(name="B", component=B(), inputs=["A"])
    pipeline.add_node(name="C", component=C(), inputs=["B"])
    pipeline.add_node(name="E", component=E(), inputs=["C"])
    pipeline.add_node(name="D", component=D(), inputs=["B"])
    pipeline.add_node(name="F", component=JoinNode(), inputs=["D", "E"])
    output = pipeline.run(query="test")
    assert output["test"] == "ABDABCE"

    pipeline = Pipeline()
    pipeline.add_node(name="A", component=A(), inputs=["Query"])
    pipeline.add_node(name="B", component=B(), inputs=["A"])
    pipeline.add_node(name="C", component=C(), inputs=["B"])
    pipeline.add_node(name="D", component=D(), inputs=["B"])
    pipeline.add_node(name="E", component=JoinNode(), inputs=["C", "D"])
    output = pipeline.run(query="test")
    assert output["test"] == "ABCABD"


def test_parallel_paths_in_pipeline_graph_with_branching():
    class AWithOutput1(RootNode):
        outgoing_edges = 2

        def run(self):
            output = "A"
            return {"output": output}, "output_1"

    class AWithOutput2(RootNode):
        outgoing_edges = 2

        def run(self):
            output = "A"
            return {"output": output}, "output_2"

    class AWithOutputAll(RootNode):
        outgoing_edges = 2

        def run(self):
            output = "A"
            return {"output": output}, "output_all"

    class B(RootNode):
        def run(self, output):
            output += "B"
            return {"output": output}, "output_1"

    class C(RootNode):
        def run(self, output):
            output += "C"
            return {"output": output}, "output_1"

    class D(RootNode):
        def run(self, output):
            output += "D"
            return {"output": output}, "output_1"

    class E(RootNode):
        def run(self, output):
            output += "E"
            return {"output": output}, "output_1"

    class JoinNode(RootNode):
        def run(self, output=None, inputs=None):
            if inputs:
                output = ""
                for input_dict in inputs:
                    output += input_dict["output"]
            return {"output": output}, "output_1"

    pipeline = Pipeline()
    pipeline.add_node(name="A", component=AWithOutput1(), inputs=["Query"])
    pipeline.add_node(name="B", component=B(), inputs=["A.output_1"])
    pipeline.add_node(name="C", component=C(), inputs=["A.output_2"])
    pipeline.add_node(name="D", component=E(), inputs=["B"])
    pipeline.add_node(name="E", component=D(), inputs=["B"])
    pipeline.add_node(name="F", component=JoinNode(), inputs=["D", "E", "C"])
    output = pipeline.run(query="test")
    assert output["output"] == "ABEABD"

    pipeline = Pipeline()
    pipeline.add_node(name="A", component=AWithOutput2(), inputs=["Query"])
    pipeline.add_node(name="B", component=B(), inputs=["A.output_1"])
    pipeline.add_node(name="C", component=C(), inputs=["A.output_2"])
    pipeline.add_node(name="D", component=E(), inputs=["B"])
    pipeline.add_node(name="E", component=D(), inputs=["B"])
    pipeline.add_node(name="F", component=JoinNode(), inputs=["D", "E", "C"])
    output = pipeline.run(query="test")
    assert output["output"] == "AC"

    pipeline = Pipeline()
    pipeline.add_node(name="A", component=AWithOutputAll(), inputs=["Query"])
    pipeline.add_node(name="B", component=B(), inputs=["A.output_1"])
    pipeline.add_node(name="C", component=C(), inputs=["A.output_2"])
    pipeline.add_node(name="D", component=E(), inputs=["B"])
    pipeline.add_node(name="E", component=D(), inputs=["B"])
    pipeline.add_node(name="F", component=JoinNode(), inputs=["D", "E", "C"])
    output = pipeline.run(query="test")
    assert output["output"] == "ACABEABD"


def test_query_keyword_statement_classifier():
    class KeywordOutput(RootNode):
        outgoing_edges = 2

        def run(self, **kwargs):
            kwargs["output"] = "keyword"
            return kwargs, "output_1"

    class QuestionOutput(RootNode):
        outgoing_edges = 2

        def run(self, **kwargs):
            kwargs["output"] = "question"
            return kwargs, "output_2"

    pipeline = Pipeline()
    pipeline.add_node(
        name="SkQueryKeywordQuestionClassifier",
        component=SklearnQueryClassifier(),
        inputs=["Query"],
    )
    pipeline.add_node(
        name="KeywordNode",
        component=KeywordOutput(),
        inputs=["SkQueryKeywordQuestionClassifier.output_2"],
    )
    pipeline.add_node(
        name="QuestionNode",
        component=QuestionOutput(),
        inputs=["SkQueryKeywordQuestionClassifier.output_1"],
    )
    output = pipeline.run(query="morse code")
    assert output["output"] == "keyword"

    output = pipeline.run(query="How old is John?")
    assert output["output"] == "question"

    pipeline = Pipeline()
    pipeline.add_node(
        name="TfQueryKeywordQuestionClassifier",
        component=TransformersQueryClassifier(),
        inputs=["Query"],
    )
    pipeline.add_node(
        name="KeywordNode",
        component=KeywordOutput(),
        inputs=["TfQueryKeywordQuestionClassifier.output_2"],
    )
    pipeline.add_node(
        name="QuestionNode",
        component=QuestionOutput(),
        inputs=["TfQueryKeywordQuestionClassifier.output_1"],
    )
    output = pipeline.run(query="morse code")
    assert output["output"] == "keyword"

    output = pipeline.run(query="How old is John?")
    assert output["output"] == "question"


@pytest.mark.parametrize(
        "retriever,document_store",
        [
            ("embedding", "faiss"),
            ("embedding", "milvus"),
            ("embedding", "elasticsearch"),
        ],
        indirect=True,
)
def test_document_search_pipeline(retriever, document_store):
    documents = [
        {"id": "a", "content": "Sample text for document-1", "meta": {"source": "wiki1"}},
        {"id": "b", "content": "Sample text for document-2", "meta": {"source": "wiki2"}},
        {"content": "Sample text for document-3", "meta": {"source": "wiki3"}},
        {"content": "Sample text for document-4", "meta": {"source": "wiki4"}},
        {"content": "Sample text for document-5", "meta": {"source": "wiki5"}},
    ]

    document_store.write_documents(documents)
    document_store.update_embeddings(retriever)

    docs_id: list = ["a", "b"]
    pipeline = MostSimilarDocumentsPipeline(document_store=document_store)
    list_of_documents = pipeline.run(document_ids=docs_id)

    assert len(list_of_documents[0]) > 1
    assert isinstance(list_of_documents, list)
    assert len(list_of_documents) == len(docs_id)

    for another_list in list_of_documents:
        assert isinstance(another_list, list)
        for document in another_list:
            assert isinstance(document, Document)
            assert isinstance(document.id, str)
            assert isinstance(document.content, str)
