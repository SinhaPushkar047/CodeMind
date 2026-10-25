from langchain_nvidia_ai_endpoints import ChatNVIDIA,NVIDIAEmbeddings
from langchain_community.document_loaders import GithubFileLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from dotenv import load_dotenv,dotenv_values
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from IPython.display import display, Markdown
from fastapi import FastAPI

app=FastAPI()

load_dotenv()

GITHUB_ACCESS_TOKEN = dotenv_values(".env")["GITHUB_ACCESS_TOKEN"]

#***************************************************DOC LOADER*********************************************
def load(url:str):
    loader=GithubFileLoader(
        repo=url,
        access_token=GITHUB_ACCESS_TOKEN,
        file_filter=None
    )

    docs=loader.load()

    docs=[doc for doc in docs if "\x00" not in doc.page_content]

    return docs

#**************************************************DOC SPLITTER************************************************
def split(docs):
    splitter=RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=250
    )

    chunks=splitter.split_documents(docs)

    return chunks

#***************************************************RETIREiVER****************************************************
def retriev(chunks,vector_store):
    bm25_retriever = BM25Retriever.from_documents(chunks)
    bm25_retriever.k = 8

    chroma_retriever = vector_store.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 8, "fetch_k": 30, "lambda_mult": 0.7}
    )

    retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, chroma_retriever],
        weights=[0.4, 0.6]
    )

    return retriever

#************************************************DOC STORE*****************************************************

def store(chunks,model):
    vector_store=Chroma.from_documents(
        documents=chunks,
        embedding=model,
        collection_name='CodeMind',
        persist_directory="./chroma_db"
    )

    return vector_store


#**********************************************context**************************************************************
def context(question,retriever,prompt):
    retriever_docs=retriever.invoke(question)
    context_text = "\n\n".join(doc.page_content for doc in retriever_docs)
    final_prompt = prompt.invoke({"context": context_text, "question": question})

    return final_prompt

#*****************************************************API BUILD*************************************************

@app.get('/')
def hello():
    return 'CODEMIND API WORKING'



server_memory={}

@app.get('/URL')
def get_url(github_url:str):

    model=NVIDIAEmbeddings(model='nvidia/nemotron-3-embed-1b')

    user_input=github_url

    doc_loader=load(user_input)

    doc_split=split(doc_loader)

    doc_store=store(doc_split,model)

    doc_retriev=retriev(doc_split,doc_store)

    server_memory['my_retriever'] = doc_retriev

    return {'message':'Docs retrieved successfully'}

@app.get('/Questions')
def ask(user_q:str):

    question=user_q

    llm=ChatNVIDIA(model='nvidia/nemotron-3-ultra-550b-a55b',temperature=0.8)

    prompt = PromptTemplate(
        template="""
        You are an expert software engineer analyzing a codebase.
        Explain the codebase functionality based on the provided code snippets and their file locations.
        If the context only shows part of the implementation, describe what is clearly visible first, and note what external dependencies or functions are referenced.

        Code Context:
        {context}

        Question: {question}
        """,
        input_variables=['context', 'question']
    )

    retriever = server_memory.get('my_retriever')

    answer=llm.invoke(context(question,retriever,prompt)).content

    return {'answer':answer}