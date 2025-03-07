import numpy as np
import pytest
from elasticsearch import Elasticsearch

from conftest import get_document_store
from haystack import Document, Label, Answer, Span
from haystack.document_store.elasticsearch import ElasticsearchDocumentStore
from haystack.document_store.faiss import FAISSDocumentStore


@pytest.mark.elasticsearch
def test_init_elastic_client():
    # defaults
    _ = ElasticsearchDocumentStore()

    # list of hosts + single port
    _ = ElasticsearchDocumentStore(host=["localhost", "127.0.0.1"], port=9200)

    # list of hosts + list of ports (wrong)
    with pytest.raises(Exception):
        _ = ElasticsearchDocumentStore(host=["localhost", "127.0.0.1"], port=[9200])

    # list of hosts + list
    _ = ElasticsearchDocumentStore(host=["localhost", "127.0.0.1"], port=[9200, 9200])

    # only api_key
    with pytest.raises(Exception):
        _ = ElasticsearchDocumentStore(host=["localhost"], port=[9200], api_key="test")

    # api_key +  id
    _ = ElasticsearchDocumentStore(host=["localhost"], port=[9200], api_key="test", api_key_id="test")


def test_write_with_duplicate_doc_ids(document_store):
    documents = [
        Document(
            content="Doc1",
            id_hash_keys=["key1"]
        ),
        Document(
            content="Doc2",
            id_hash_keys=["key1"]
        )
    ]
    document_store.write_documents(documents, duplicate_documents="skip")
    assert len(document_store.get_all_documents()) == 1
    with pytest.raises(Exception):
        document_store.write_documents(documents, duplicate_documents="fail")


def test_write_with_duplicate_doc_ids_custom_index(document_store):
    documents = [
        Document(
            content="Doc1",
            id_hash_keys=["key1"]
        ),
        Document(
            content="Doc2",
            id_hash_keys=["key1"]
        )
    ]
    document_store.delete_documents(index="haystack_custom_test")
    document_store.write_documents(documents, index="haystack_custom_test", duplicate_documents="skip")
    with pytest.raises(Exception):
        document_store.write_documents(documents, index="haystack_custom_test", duplicate_documents="fail")

    # writing to the default, empty index should still work
    document_store.write_documents(documents, duplicate_documents="fail")

def test_get_all_documents_without_filters(document_store_with_docs):
    documents = document_store_with_docs.get_all_documents()
    assert all(isinstance(d, Document) for d in documents)
    assert len(documents) == 3
    assert {d.meta["name"] for d in documents} == {"filename1", "filename2", "filename3"}
    assert {d.meta["meta_field"] for d in documents} == {"test1", "test2", "test3"}


def test_get_all_document_filter_duplicate_text_value(document_store):
    documents = [
        Document(
            content="Doc1",
            meta={"f1": "0"},
            id_hash_keys=["Doc1", "1"]
        ),
        Document(
            content="Doc1",
            meta={"f1": "1", "meta_id": "0"},
            id_hash_keys=["Doc1", "2"]
        ),
        Document(
            content="Doc2",
            meta={"f3": "0"},
            id_hash_keys=["Doc2", "3"]
        )
    ]
    document_store.write_documents(documents)
    documents = document_store.get_all_documents(filters={"f1": ["1"]})
    assert documents[0].content == "Doc1"
    assert len(documents) == 1
    assert {d.meta["meta_id"] for d in documents} == {"0"}


def test_get_all_documents_with_correct_filters(document_store_with_docs):
    documents = document_store_with_docs.get_all_documents(filters={"meta_field": ["test2"]})
    assert len(documents) == 1
    assert documents[0].meta["name"] == "filename2"

    documents = document_store_with_docs.get_all_documents(filters={"meta_field": ["test1", "test3"]})
    assert len(documents) == 2
    assert {d.meta["name"] for d in documents} == {"filename1", "filename3"}
    assert {d.meta["meta_field"] for d in documents} == {"test1", "test3"}


def test_get_all_documents_with_correct_filters_legacy_sqlite(test_docs_xs):
    document_store_with_docs = get_document_store("sql")
    document_store_with_docs.write_documents(test_docs_xs)

    document_store_with_docs.use_windowed_query = False
    documents = document_store_with_docs.get_all_documents(filters={"meta_field": ["test2"]})
    assert len(documents) == 1
    assert documents[0].meta["name"] == "filename2"

    documents = document_store_with_docs.get_all_documents(filters={"meta_field": ["test1", "test3"]})
    assert len(documents) == 2
    assert {d.meta["name"] for d in documents} == {"filename1", "filename3"}
    assert {d.meta["meta_field"] for d in documents} == {"test1", "test3"}


def test_get_all_documents_with_incorrect_filter_name(document_store_with_docs):
    documents = document_store_with_docs.get_all_documents(filters={"incorrect_meta_field": ["test2"]})
    assert len(documents) == 0


def test_get_all_documents_with_incorrect_filter_value(document_store_with_docs):
    documents = document_store_with_docs.get_all_documents(filters={"meta_field": ["incorrect_value"]})
    assert len(documents) == 0


def test_get_documents_by_id(document_store_with_docs):
    documents = document_store_with_docs.get_all_documents()
    doc = document_store_with_docs.get_document_by_id(documents[0].id)
    assert doc.id == documents[0].id
    assert doc.content == documents[0].content


def test_get_document_count(document_store):
    documents = [
        {"content": "text1", "id": "1", "meta_field_for_count": "a"},
        {"content": "text2", "id": "2", "meta_field_for_count": "b"},
        {"content": "text3", "id": "3", "meta_field_for_count": "b"},
        {"content": "text4", "id": "4", "meta_field_for_count": "b"},
    ]
    document_store.write_documents(documents)
    assert document_store.get_document_count() == 4
    assert document_store.get_document_count(filters={"meta_field_for_count": ["a"]}) == 1
    assert document_store.get_document_count(filters={"meta_field_for_count": ["b"]}) == 3


def test_get_all_documents_generator(document_store):
    documents = [
        {"content": "text1", "id": "1", "meta_field_for_count": "a"},
        {"content": "text2", "id": "2", "meta_field_for_count": "b"},
        {"content": "text3", "id": "3", "meta_field_for_count": "b"},
        {"content": "text4", "id": "4", "meta_field_for_count": "b"},
        {"content": "text5", "id": "5", "meta_field_for_count": "b"},
    ]

    document_store.write_documents(documents)
    assert len(list(document_store.get_all_documents_generator(batch_size=2))) == 5


@pytest.mark.parametrize("update_existing_documents", [True, False])
def test_update_existing_documents(document_store, update_existing_documents):
    original_docs = [
        {"content": "text1_orig", "id": "1", "meta_field_for_count": "a"},
    ]

    updated_docs = [
        {"content": "text1_new", "id": "1", "meta_field_for_count": "a"},
    ]

    document_store.write_documents(original_docs)
    assert document_store.get_document_count() == 1

    if update_existing_documents:
        document_store.write_documents(updated_docs, duplicate_documents="overwrite")
    else:
        with pytest.raises(Exception):
            document_store.write_documents(updated_docs, duplicate_documents="fail")

    stored_docs = document_store.get_all_documents()
    assert len(stored_docs) == 1
    if update_existing_documents:
        assert stored_docs[0].content == updated_docs[0]["content"]
    else:
        assert stored_docs[0].content == original_docs[0]["content"]


def test_write_document_meta(document_store):
    documents = [
        {"content": "dict_without_meta", "id": "1"},
        {"content": "dict_with_meta", "meta_field": "test2", "name": "filename2", "id": "2"},
        Document(content="document_object_without_meta", id="3"),
        Document(content="document_object_with_meta", meta={"meta_field": "test4", "name": "filename3"}, id="4"),
    ]
    document_store.write_documents(documents)
    documents_in_store = document_store.get_all_documents()
    assert len(documents_in_store) == 4

    assert not document_store.get_document_by_id("1").meta
    assert document_store.get_document_by_id("2").meta["meta_field"] == "test2"
    assert not document_store.get_document_by_id("3").meta
    assert document_store.get_document_by_id("4").meta["meta_field"] == "test4"


def test_write_document_index(document_store):
    documents = [
        {"content": "text1", "id": "1"},
        {"content": "text2", "id": "2"},
    ]
    document_store.write_documents([documents[0]], index="haystack_test_1")
    assert len(document_store.get_all_documents(index="haystack_test_1")) == 1

    document_store.write_documents([documents[1]], index="haystack_test_2")
    assert len(document_store.get_all_documents(index="haystack_test_2")) == 1

    assert len(document_store.get_all_documents(index="haystack_test_1")) == 1
    assert len(document_store.get_all_documents()) == 0


def test_document_with_embeddings(document_store):
    documents = [
        {"content": "text1", "id": "1", "embedding": np.random.rand(768).astype(np.float32)},
        {"content": "text2", "id": "2", "embedding": np.random.rand(768).astype(np.float64)},
        {"content": "text3", "id": "3", "embedding": np.random.rand(768).astype(np.float32).tolist()},
        {"content": "text4", "id": "4", "embedding": np.random.rand(768).astype(np.float32)},
    ]
    document_store.write_documents(documents, index="haystack_test_1")
    assert len(document_store.get_all_documents(index="haystack_test_1")) == 4

    documents_without_embedding = document_store.get_all_documents(index="haystack_test_1", return_embedding=False)
    assert documents_without_embedding[0].embedding is None

    documents_with_embedding = document_store.get_all_documents(index="haystack_test_1", return_embedding=True)
    assert isinstance(documents_with_embedding[0].embedding, (list, np.ndarray))


@pytest.mark.parametrize("retriever", ["embedding"], indirect=True)
def test_update_embeddings(document_store, retriever):
    documents = []
    for i in range(6):
        documents.append({"content": f"text_{i}", "id": str(i), "meta_field": f"value_{i}"})
    documents.append({"content": "text_0", "id": "6", "meta_field": "value_0"})

    document_store.write_documents(documents, index="haystack_test_1")
    document_store.update_embeddings(retriever, index="haystack_test_1", batch_size=3)
    documents = document_store.get_all_documents(index="haystack_test_1", return_embedding=True)
    assert len(documents) == 7
    for doc in documents:
        assert type(doc.embedding) is np.ndarray

    documents = document_store.get_all_documents(
        index="haystack_test_1",
        filters={"meta_field": ["value_0"]},
        return_embedding=True,
    )
    assert len(documents) == 2
    for doc in documents:
        assert doc.meta["meta_field"] == "value_0"
    np.testing.assert_array_almost_equal(documents[0].embedding, documents[1].embedding, decimal=4)

    documents = document_store.get_all_documents(
        index="haystack_test_1",
        filters={"meta_field": ["value_0", "value_5"]},
        return_embedding=True,
    )
    np.testing.assert_raises(
        AssertionError,
        np.testing.assert_array_equal,
        documents[0].embedding,
        documents[1].embedding
    )

    doc = {"content": "text_7", "id": "7", "meta_field": "value_7",
           "embedding": retriever.embed_queries(texts=["a random string"])[0]}
    document_store.write_documents([doc], index="haystack_test_1")

    documents = []
    for i in range(8, 11):
        documents.append({"content": f"text_{i}", "id": str(i), "meta_field": f"value_{i}"})
    document_store.write_documents(documents, index="haystack_test_1")

    doc_before_update = document_store.get_all_documents(index="haystack_test_1", filters={"meta_field": ["value_7"]})[0]
    embedding_before_update = doc_before_update.embedding

    # test updating only documents without embeddings
    document_store.update_embeddings(retriever, index="haystack_test_1", batch_size=3, update_existing_embeddings=False)
    doc_after_update = document_store.get_all_documents(index="haystack_test_1", filters={"meta_field": ["value_7"]})[0]
    embedding_after_update = doc_after_update.embedding
    np.testing.assert_array_equal(embedding_before_update, embedding_after_update)

    # test updating with filters
    if isinstance(document_store, FAISSDocumentStore):
        with pytest.raises(Exception):
            document_store.update_embeddings(
                retriever, index="haystack_test_1", update_existing_embeddings=True, filters={"meta_field": ["value"]}
            )
    else:
        document_store.update_embeddings(
            retriever, index="haystack_test_1", batch_size=3, filters={"meta_field": ["value_0", "value_1"]}
        )
        doc_after_update = document_store.get_all_documents(index="haystack_test_1", filters={"meta_field": ["value_7"]})[0]
        embedding_after_update = doc_after_update.embedding
        np.testing.assert_array_equal(embedding_before_update, embedding_after_update)

    # test update all embeddings
    document_store.update_embeddings(retriever, index="haystack_test_1", batch_size=3, update_existing_embeddings=True)
    assert document_store.get_embedding_count(index="haystack_test_1") == 11
    doc_after_update = document_store.get_all_documents(index="haystack_test_1", filters={"meta_field": ["value_7"]})[0]
    embedding_after_update = doc_after_update.embedding
    np.testing.assert_raises(AssertionError, np.testing.assert_array_equal, embedding_before_update, embedding_after_update)

    # test update embeddings for newly added docs
    documents = []
    for i in range(12, 15):
        documents.append({"content": f"text_{i}", "id": str(i), "meta_field": f"value_{i}"})
    document_store.write_documents(documents, index="haystack_test_1")
    document_store.update_embeddings(retriever, index="haystack_test_1", batch_size=3, update_existing_embeddings=False)
    assert document_store.get_embedding_count(index="haystack_test_1") == 14


def test_delete_all_documents(document_store_with_docs):
    assert len(document_store_with_docs.get_all_documents()) == 3

    document_store_with_docs.delete_documents()
    documents = document_store_with_docs.get_all_documents()
    assert len(documents) == 0


def test_delete_documents(document_store_with_docs):
    assert len(document_store_with_docs.get_all_documents()) == 3

    document_store_with_docs.delete_documents()
    documents = document_store_with_docs.get_all_documents()
    assert len(documents) == 0

    
def test_delete_documents_with_filters(document_store_with_docs):
    document_store_with_docs.delete_documents(filters={"meta_field": ["test1", "test2"]})
    documents = document_store_with_docs.get_all_documents()
    assert len(documents) == 1
    assert documents[0].meta["meta_field"] == "test3"


def test_labels(document_store):
    label = Label(
        query="question",
        answer=Answer(answer="answer",
                      type="extractive",
                      score=0.0,
                      context="something",
                      offsets_in_document=[Span(start=12, end=14)],
                      offsets_in_context=[Span(start=12, end=14)],
                      ),
        is_correct_answer=True,
        is_correct_document=True,
        document=Document(content="something", id="123"),
        no_answer=False,
        origin="gold-label",
    )
    document_store.write_labels([label], index="haystack_test_label")
    labels = document_store.get_all_labels(index="haystack_test_label")
    assert len(labels) == 1
    assert label == labels[0]

    # different index
    labels = document_store.get_all_labels()
    assert len(labels) == 0

    # write second label + duplicate
    label2 = Label(
        query="question",
        answer=Answer(answer="another answer",
                      type="extractive",
                      score=0.0,
                      context="something",
                      offsets_in_document=[Span(start=12, end=14)],
                      offsets_in_context=[Span(start=12, end=14)],
                      ),
        is_correct_answer=True,
        is_correct_document=True,
        document=Document(content="something", id="324"),
        no_answer=False,
        origin="gold-label",
    )
    document_store.write_labels([label, label2], index="haystack_test_label")
    labels = document_store.get_all_labels(index="haystack_test_label")

    # duplicate should not be there
    assert len(labels) == 2
    assert label in labels
    assert label2 in labels


def test_multilabel(document_store):
    labels =[
        Label(
            id="standard",
            query="question",
            answer=Answer(answer="answer1",
                          offsets_in_document=[Span(start=12, end=18)]),
            document=Document(content="some", id="123"),
            is_correct_answer=True,
            is_correct_document=True,
            no_answer=False,
            origin="gold-label",
        ),
        # different answer in same doc
        Label(
            id="diff-answer-same-doc",
            query="question",
            answer=Answer(answer="answer2",
                          offsets_in_document=[Span(start=12, end=18)]),
            document=Document(content="some", id="123"),
            is_correct_answer=True,
            is_correct_document=True,
            no_answer=False,
            origin="gold-label",
        ),
        # answer in different doc
        Label(
            id="diff-answer-diff-doc",
            query="question",
            answer=Answer(answer="answer3",
                          offsets_in_document=[Span(start=12, end=18)]),
            document=Document(content="some other", id="333"),
            is_correct_answer=True,
            is_correct_document=True,
            no_answer=False,
            origin="gold-label",
        ),
        # 'no answer', should be excluded from MultiLabel
        Label(
            id="4-no-answer",
            query="question",
            answer=Answer(answer="",
                          offsets_in_document=[Span(start=0, end=0)]),
            document=Document(content="some", id="777"),
            is_correct_answer=True,
            is_correct_document=True,
            no_answer=True,
            origin="gold-label",
        ),
        # is_correct_answer=False, should be excluded from MultiLabel if "drop_negatives = True"
        Label(
            id="5-negative",
            query="question",
            answer=Answer(answer="answer5",
                          offsets_in_document=[Span(start=12, end=18)]),
            document=Document(content="some", id="123"),
            is_correct_answer=False,
            is_correct_document=True,
            no_answer=False,
            origin="gold-label",
        ),
    ]
    document_store.write_labels(labels, index="haystack_test_multilabel")
    # regular labels - not aggregated
    list_labels = document_store.get_all_labels(index="haystack_test_multilabel")
    assert list_labels == labels
    assert len(list_labels) == 5

    # Currently we don't enforce writing (missing) docs automatically when adding labels and there's no DB relationship between the two.
    # We should introduce this when we refactored the logic of "index" to be rather a "collection" of labels+documents
    # docs = document_store.get_all_documents(index="haystack_test_multilabel")
    # assert len(docs) == 3

    # Multi labels (open domain)
    multi_labels_open = document_store.get_all_labels_aggregated(index="haystack_test_multilabel",
                                                                 open_domain=True, drop_negative_labels=True)

    # for open-domain we group all together as long as they have the same question
    assert len(multi_labels_open) == 1
    # all labels are in there except the negative one
    assert len(multi_labels_open[0].answers) == 4
    assert "5-negative" not in [l.id for l in multi_labels_open[0].labels]

    # Don't drop the negative label
    multi_labels_open = document_store.get_all_labels_aggregated(index="haystack_test_multilabel", open_domain=True,
                                                                 drop_no_answers=False, drop_negative_labels=False)
    assert len(multi_labels_open[0].answers) == 5

    # Drop no answer + negative
    multi_labels_open = document_store.get_all_labels_aggregated(index="haystack_test_multilabel", open_domain=True,
                                                                 drop_no_answers=True, drop_negative_labels=True)
    assert len(multi_labels_open[0].answers) == 3

    # for closed domain we group by document so we expect 3 multilabels with 2,1,1 labels each (negative dropped again)
    multi_labels = document_store.get_all_labels_aggregated(index="haystack_test_multilabel",
                                                            open_domain=False, drop_negative_labels=True)
    assert len(multi_labels) == 3
    label_counts = set([len(ml.labels) for ml in multi_labels])
    assert label_counts == set([2,1,1])

    assert len(multi_labels[0].answers) == len(multi_labels[0].document_ids)


    # make sure there' nothing stored in another index
    multi_labels = document_store.get_all_labels_aggregated()
    assert len(multi_labels) == 0
    docs = document_store.get_all_documents()
    assert len(docs) == 0


def test_multilabel_no_answer(document_store):

    labels = [
        Label(
            query="question",
            answer=Answer(answer=""),
            is_correct_answer=True,
            is_correct_document=True,
            document=Document(content="some", id="777"),
            no_answer=True,
            origin="gold-label",
        ),
        # no answer in different doc
        Label(
            query="question",
            answer=Answer(answer=""),
            is_correct_answer=True,
            is_correct_document=True,
            document=Document(content="some", id="123"),
            no_answer=True,
            origin="gold-label",
        ),
        # no answer in same doc, should be excluded
        Label(
            query="question",
            answer=Answer(answer=""),
            is_correct_answer=True,
            is_correct_document=True,
            document=Document(content="some", id="777"),
            no_answer=True,
            origin="gold-label",
        ),
        # no answer with is_correct_answer=False, should be excluded
        Label(
            query="question",
            answer=Answer(answer=""),
            is_correct_answer=False,
            is_correct_document=True,
            document=Document(content="some", id="777"),
            no_answer=True,
            origin="gold-label",
        ),
    ]

    document_store.write_labels(labels, index="haystack_test_multilabel_no_answer")


    labels = document_store.get_all_labels(index="haystack_test_multilabel_no_answer")
    assert len(labels) == 4

    multi_labels = document_store.get_all_labels_aggregated(index="haystack_test_multilabel_no_answer",
                                                            open_domain=True,
                                                            drop_no_answers=False,
                                                            drop_negative_labels=True)
    assert len(multi_labels) == 1
    assert multi_labels[0].no_answer == True
    assert len(multi_labels[0].document_ids) == 2
    assert len(multi_labels[0].answers) == 2

    multi_labels = document_store.get_all_labels_aggregated(index="haystack_test_multilabel_no_answer",
                                                            open_domain=True,
                                                            drop_no_answers=False,
                                                            drop_negative_labels=False)
    assert len(multi_labels) == 1
    assert multi_labels[0].no_answer == True
    assert len(multi_labels[0].document_ids) == 3
    assert len(multi_labels[0].labels) == 3
    assert len(multi_labels[0].answers) == 3


@pytest.mark.parametrize("document_store", ["elasticsearch", "faiss"], indirect=True)
# Currently update_document_meta() is not implemented for Memory doc store
def test_update_meta(document_store):
    documents = [
        Document(
            content="Doc1",
            meta={"meta_key_1": "1", "meta_key_2": "1"}
        ),
        Document(
            content="Doc2",
            meta={"meta_key_1": "2", "meta_key_2": "2"}
        ),
        Document(
            content="Doc3",
            meta={"meta_key_1": "3", "meta_key_2": "3"}
        )
    ]
    document_store.write_documents(documents)
    document_2 = document_store.get_all_documents(filters={"meta_key_2": ["2"]})[0]
    document_store.update_document_meta(document_2.id, meta={"meta_key_1": "99", "meta_key_2": "2"})
    updated_document = document_store.get_document_by_id(document_2.id)
    assert len(updated_document.meta.keys()) == 2
    assert updated_document.meta["meta_key_1"] == "99"
    assert updated_document.meta["meta_key_2"] == "2"


@pytest.mark.parametrize("document_store_type", ["elasticsearch", "memory"])
def test_custom_embedding_field(document_store_type):
    document_store = get_document_store(
        document_store_type=document_store_type, embedding_field="custom_embedding_field"
    )
    doc_to_write = {"content": "test", "custom_embedding_field": np.random.rand(768).astype(np.float32)}
    document_store.write_documents([doc_to_write])
    documents = document_store.get_all_documents(return_embedding=True)
    assert len(documents) == 1
    assert documents[0].content == "test"
    np.testing.assert_array_equal(doc_to_write["custom_embedding_field"], documents[0].embedding)


@pytest.mark.parametrize("document_store", ["elasticsearch"], indirect=True)
def test_get_meta_values_by_key(document_store):
    documents = [
        Document(
            content="Doc1",
            meta={"meta_key_1": "1", "meta_key_2": "11"}
        ),
        Document(
            content="Doc2",
            meta={"meta_key_1": "2", "meta_key_2": "22"}
        ),
        Document(
            content="Doc3",
            meta={"meta_key_1": "3", "meta_key_2": "33"}
        )
    ]
    document_store.write_documents(documents)

    # test without filters or query
    result = document_store.get_metadata_values_by_key(key="meta_key_1")
    for bucket in result:
        assert bucket["value"] in ["1", "2", "3"]
        assert bucket["count"] == 1

    # test with filters but no query
    result = document_store.get_metadata_values_by_key(key="meta_key_1", filters={"meta_key_2": ["11", "22"]})
    for bucket in result:
        assert bucket["value"] in ["1", "2"]
        assert bucket["count"] == 1

    # test with filters & query
    result = document_store.get_metadata_values_by_key(key="meta_key_1", query="Doc1")
    for bucket in result:
        assert bucket["value"] in ["1"]
        assert bucket["count"] == 1


@pytest.mark.elasticsearch
def test_elasticsearch_custom_fields(elasticsearch_fixture):
    client = Elasticsearch()
    client.indices.delete(index='haystack_test_custom', ignore=[404])
    document_store = ElasticsearchDocumentStore(index="haystack_test_custom", content_field="custom_text_field",
                                                embedding_field="custom_embedding_field")

    doc_to_write = {"custom_text_field": "test", "custom_embedding_field": np.random.rand(768).astype(np.float32)}
    document_store.write_documents([doc_to_write])
    documents = document_store.get_all_documents(return_embedding=True)
    assert len(documents) == 1
    assert documents[0].content == "test"
    np.testing.assert_array_equal(doc_to_write["custom_embedding_field"], documents[0].embedding)


@pytest.mark.elasticsearch
def test_get_document_count_only_documents_without_embedding_arg():
    documents = [
        {"content": "text1", "id": "1", "embedding": np.random.rand(768).astype(np.float32), "meta_field_for_count": "a"},
        {"content": "text2", "id": "2", "embedding": np.random.rand(768).astype(np.float64), "meta_field_for_count": "b"},
        {"content": "text3", "id": "3", "embedding": np.random.rand(768).astype(np.float32).tolist()},
        {"content": "text4", "id": "4", "meta_field_for_count": "b"},
        {"content": "text5", "id": "5", "meta_field_for_count": "b"},
        {"content": "text6", "id": "6", "meta_field_for_count": "c"},
        {"content": "text7", "id": "7", "embedding": np.random.rand(768).astype(np.float64), "meta_field_for_count": "c"},
    ]

    _index: str = "haystack_test_count"
    document_store = ElasticsearchDocumentStore(index=_index)
    document_store.delete_documents(index=_index)

    document_store.write_documents(documents)

    assert document_store.get_document_count() == 7
    assert document_store.get_document_count(only_documents_without_embedding=True) == 3
    assert document_store.get_document_count(only_documents_without_embedding=True,
                                             filters={"meta_field_for_count": ["c"]}) == 1
    assert document_store.get_document_count(only_documents_without_embedding=True,
                                             filters={"meta_field_for_count": ["b"]}) == 2
