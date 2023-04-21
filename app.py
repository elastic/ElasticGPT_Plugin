import json
import requests
import urllib.parse

import quart
import quart_cors
from quart import request

import os
import openai
from elasticsearch import Elasticsearch

app = quart_cors.cors(quart.Quart(__name__), allow_origin="*")

# JEFF THIS IS WHERE YOU WANT TO ADD YOUR CODE !!

openai.api_key = os.environ['openai_api']
model = "gpt-3.5-turbo-0301"


# Connect to Elastic Cloud cluster
def es_connect(cid, user, passwd):
  es = Elasticsearch(cloud_id=cid, http_auth=(user, passwd))
  return es


# Search ElasticSearch index and return body and URL of the result
def ESSearch(query_text):
  cid = os.environ['cloud_id']
  cp = os.environ['cloud_pass']
  cu = os.environ['cloud_user']
  es = es_connect(cid, cu, cp)

  # Elasticsearch query (BM25) and kNN configuration for hybrid search
  query = {
    "bool": {
      "must": [{
        "match": {
          "title": {
            "query": query_text,
            "boost": 1
          }
        }
      }],
      "filter": [{
        "exists": {
          "field": "title-vector"
        }
      }]
    }
  }

  knn = {
    "field": "title-vector",
    "k": 1,
    "num_candidates": 20,
    "query_vector_builder": {
      "text_embedding": {
        "model_id": "sentence-transformers__all-distilroberta-v1",
        "model_text": query_text
      }
    },
    "boost": 24
  }

  fields = ["title", "body_content", "url"]
  index = 'search-elastic-docs'
  resp = es.search(index=index,
                   query=query,
                   knn=knn,
                   fields=fields,
                   size=1,
                   source=False)

  body = resp['hits']['hits'][0]['fields']['body_content'][0]
  url = resp['hits']['hits'][0]['fields']['url'][0]

  return body, url


def truncate_text(text, max_tokens):
  tokens = text.split()
  if len(tokens) <= max_tokens:
    return text

  return ' '.join(tokens[:max_tokens])


# Generate a response from ChatGPT based on the given prompt
def chat_gpt(prompt,
             model="gpt-3.5-turbo",
             max_tokens=1024,
             max_context_tokens=4000,
             safety_margin=5):
  # Truncate the prompt content to fit within the model's context length
  truncated_prompt = truncate_text(
    prompt, max_context_tokens - max_tokens - safety_margin)

  response = openai.ChatCompletion.create(model=model,
                                          messages=[{
                                            "role":
                                            "system",
                                            "content":
                                            "You are a helpful assistant."
                                          }, {
                                            "role": "user",
                                            "content": truncated_prompt
                                          }])

  return response["choices"][0]["message"]["content"]


@app.get("/search")
async def search():
  query = request.args.get("query")
  print(query)

  negResponse = "I'm unable to answer the question based on the information I have from Elastic Docs."

    
  resp, url = ESSearch(query)
  prompt = f"Answer this question: {query}\nUsing only the information from this Elastic Doc: {resp}\nIf the answer is not contained in the supplied doc reply '{negResponse}' and nothing else"
  answer = chat_gpt(prompt)

  #negResponse = "I'm unable to answer the question based on the information I have from Elastic Docs."

  if negResponse in answer:
    response = answer.strip()
  else:
    response = f"ChatGPT: {answer.strip()}\n\nDocs: {url}"

  return quart.Response(response=response, status=200)


# DO NOT TOUCH ANYTHING BELOW THIS COMMENT!
@app.get("/logo.png")
async def plugin_logo():
  filename = 'logo.png'
  return await quart.send_file(filename, mimetype='image/png')


# https://elasticdocplugin.bahaaldineazarm.repl.co/.well-known/ai-plugin.json


@app.get("/.well-known/ai-plugin.json")
async def plugin_manifest():
  host = request.headers['Host']
  with open("./.well-known/ai-plugin.json") as f:
    text = f.read()
    text = text.replace("PLUGIN_HOSTNAME", f"https://{host}")
    return quart.Response(text, mimetype="text/json")


@app.get("/openapi.yaml")
async def openapi_spec():
  host = request.headers['Host']
  with open("openapi.yaml") as f:
    text = f.read()
    text = text.replace("PLUGIN_HOSTNAME", f"https://{host}")
    return quart.Response(text, mimetype="text/yaml")


def main():
  app.run(debug=True, host="0.0.0.0", port=5001)


if __name__ == "__main__":
  main()
