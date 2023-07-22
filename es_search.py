def find_all(es, index_name):
    match_all = {
        "size": 20,
        "query": {
            "match_all": {}
        }
    }

    records = []

    # make a search() request to get all docs in the index
    resp = es.search(
        index=index_name,
        body=match_all,
        scroll='2s'  # length of time to keep search context
    )

    # keep track of pass scroll _id
    old_scroll_id = resp['_scroll_id']

    # use a 'while' iterator to loop over document 'hits'
    while len(resp['hits']['hits']):
        # keep track of pass scroll _id
        old_scroll_id = resp['_scroll_id']

        # iterate over the document hits for each 'scroll'
        for doc in resp['hits']['hits']:
            records.append(doc["_source"])

        # make a request using the Scroll API
        resp = es.scroll(
            scroll_id=old_scroll_id,
            scroll='2s'  # length of time to keep search context
        )
    return records


def find_by_name(es, index_name, field, value):
    match_all = {
        "size": 20,
        "query": {
            "match": {
                field: value
            }
        }
    }

    records = []

    # make a search() request to get all docs in the index
    resp = es.search(
        index=index_name,
        body=match_all,
        scroll='2s'  # length of time to keep search context
    )

    # iterate over the document hits for each 'scroll'
    for doc in resp['hits']['hits']:
        records.append(doc["_source"])
    if len(records) > 0:
        return records[0]
    return None
