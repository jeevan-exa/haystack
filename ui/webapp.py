import os
import sys

import logging
import pandas as pd
import streamlit as st
from annotated_text import annotated_text

# streamlit does not support any states out of the box. On every button click, streamlit reload the whole page
# and every value gets lost. To keep track of our feedback state we use the official streamlit gist mentioned
# here https://gist.github.com/tvst/036da038ab3e999a64497f42de966a92
import SessionState
from utils import feedback_doc, haystack_is_ready, retrieve_doc, upload_doc

# Adjust to a question that you would like users to see in the search bar when they load the UI:
DEFAULT_QUESTION_AT_STARTUP = "Who is the father of Arya Stark?"


def annotate_answer(answer, context):
    """ If we are using an extractive QA pipeline, we'll get answers
    from the API that we highlight in the given context"""
    start_idx = context.find(answer)
    end_idx = start_idx + len(answer)
    # calculate dynamic height depending on context length
    height = int(len(context) * 0.50) + 5
    annotated_text(context[:start_idx], (answer, "ANSWER", "#8ef"), context[end_idx:], height=height)


def show_plain_documents(text):
    """ If we are using a plain document search pipeline, i.e. only retriever, we'll get plain documents
    from the API that we just show without any highlighting"""
    st.markdown(text)


def random_questions(df):
    """
    Helper to get one random question + gold random_answer from the user's CSV 'eval_labels_example'.
    This can then be shown in the UI when the evaluation mode is selected. Users can easily give feedback on the
    model's results and "enrich" the eval dataset with more acceptable labels
    """
    random_row = df.sample(1)
    random_question = random_row["Question Text"].values[0]
    random_answer = random_row["Answer"].values[0]
    return random_question, random_answer


def main():
    # Define state
    state_question = SessionState.get(
        random_question=DEFAULT_QUESTION_AT_STARTUP, random_answer="", next_question="false", run_query="false"
    )

    # Initialize variables
    eval_mode = False
    random_question = DEFAULT_QUESTION_AT_STARTUP
    eval_labels = os.getenv("EVAL_FILE", "eval_labels_example.csv")

    # UI search bar and sidebar
    st.write("# Exafluence Demo")
    st.sidebar.header("Options")
    top_k_reader = st.sidebar.slider("Max. number of answers", min_value=1, max_value=10, value=3, step=1)
    top_k_retriever = st.sidebar.slider(
        "Max. number of documents from retriever", min_value=1, max_value=10, value=3, step=1
    )
    eval_mode = st.sidebar.checkbox("Evaluation mode")
    debug = st.sidebar.checkbox("Show debug info")

    st.sidebar.write("## File Upload:")
    data_files = st.sidebar.file_uploader("", type=["pdf", "txt", "docx"], accept_multiple_files=True)
    for data_file in data_files:
        # Upload file
        if data_file:
            raw_json = upload_doc(data_file)
            st.sidebar.write(raw_json)
            if debug:
                st.subheader("REST API JSON response")
                st.sidebar.write(raw_json)

    # load csv into pandas dataframe
    if eval_mode:
        try:
            df = pd.read_csv(eval_labels, sep=";")
        except Exception:
            sys.exit("The eval file was not found. Please check the README for more information.")
        if (
            state_question
            and hasattr(state_question, "next_question")
            and hasattr(state_question, "random_question")
            and state_question.next_question
        ):
            random_question = state_question.random_question
            random_answer = state_question.random_answer
        else:
            random_question, random_answer = random_questions(df)
            state_question.random_question = random_question
            state_question.random_answer = random_answer

    # Get next random question from the CSV
    if eval_mode:
        next_question = st.button("Load new question")
        if next_question:
            random_question, random_answer = random_questions(df)
            state_question.random_question = random_question
            state_question.random_answer = random_answer
            state_question.next_question = True
            state_question.run_query = False
        else:
            state_question.next_question = False

    # Search bar
    question = st.text_input("Please provide your query:", value=random_question)
    if state_question and state_question.run_query:
        run_query = state_question.run_query
        st.button("Run")
    else:
        run_query = st.button("Run")
        state_question.run_query = run_query

    raw_json_feedback = ""

    with st.spinner("⌛️ &nbsp;&nbsp; Setting up..."):
        if not haystack_is_ready():
            st.error("🚫 &nbsp;&nbsp; Connection Error. Is Haystack running?")
            run_query = False

    # Get results for query
    if run_query:
        with st.spinner(
            "🧠 &nbsp;&nbsp; Performing neural search on documents... \n "
            "Do you want to optimize speed or accuracy? Look for optimization documentation"
        ):
            try:
                results, raw_json = retrieve_doc(question, top_k_reader=top_k_reader, top_k_retriever=top_k_retriever)
            except Exception as e:
                logging.exception(e)
                st.error("🐞 &nbsp;&nbsp; An error occurred during the request. Check the logs in the console to know more.")
                return

        # Show if we use a question of the given set
        if question == random_question and eval_mode:
            st.write("## Correct answers:")
            random_answer

        st.write("## Results:")

        # Make every button key unique
        count = 0

        for result in results:
            if result["answer"]:
                annotate_answer(result["answer"], result["context"])
            else:
                show_plain_documents(result["context"])
            st.write("**Relevance:** ", result["relevance"], "**Source:** ", result["source"])
            if eval_mode:
                # Define columns for buttons
                button_col1, button_col2, button_col3, button_col4 = st.columns([1, 1, 1, 6])
                if button_col1.button("👍", key=(result["context"] + str(count) + "1"), help="Correct answer"):
                    raw_json_feedback = feedback_doc(
                        question, "true", result["document_id"], 1, "true", result["answer"], result["offset_start_in_doc"]
                    )
                    st.success("Thanks for your feedback")
                if button_col2.button("👎", key=(result["context"] + str(count) + "2"), help="Wrong answer and wrong passage"):
                    raw_json_feedback = feedback_doc(
                        question,
                        "false",
                        result["document_id"],
                        1,
                        "false",
                        result["answer"],
                        result["offset_start_in_doc"],
                    )
                    st.success("Thanks for your feedback!")
                if button_col3.button("👎👍", key=(result["context"] + str(count) + "3"), help="Wrong answer, but correct passage"):
                    raw_json_feedback = feedback_doc(
                        question, "false", result["document_id"], 1, "true", result["answer"], result["offset_start_in_doc"]
                    )
                    st.success("Thanks for your feedback!")
                count += 1
            st.write("___")
        if debug:
            st.subheader("REST API JSON response")
            st.write(raw_json)

main()
