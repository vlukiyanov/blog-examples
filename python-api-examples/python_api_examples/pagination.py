import itertools
from datetime import datetime
from typing import Any, Dict, Iterable

import cytoolz
import pydantic
import requests
from pydantic import BaseModel
from ratelimit import RateLimitException, limits
from tenacity import *
from yarl import URL

from python_api_examples.secrets import GUARDIAN_API_KEY


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    wait=wait_exponential(max=60, min=1),
    stop=stop_after_attempt(3),
)
@retry(
    retry=retry_if_exception_type(RateLimitException),
    wait=wait_fixed(1),
    stop=stop_after_delay(60),
)
@limits(calls=12, period=1)
def call_get(url: URL) -> Dict[str, Any]:
    """
    Given a URL to call the Guardian API, inject the API key, make the call
    and return the resulting parsed JSON; this function handles per second
    rate limits and retries.

    :param url: URL to make a GET request on for the Guardian API
    :return: parsed JSON result, as a dictionary
    """
    return requests.get(url.update_query({"api-key": GUARDIAN_API_KEY})).json()


def iter_call_get(url: URL, page_size: int = 50) -> Iterable[Dict[str, Any]]:
    """
    Given a URL to call the Guardian API, paginate in page size of page_size,
    yielding the results of the search one by one until no more data is
    available; the API documents the results ordered by the publication date.

    :param url: URL to paginate, like URL("https://content.guardianapis.com/search?q=debates")
    :param page_size: page size for the API, default 50, maximum 50
    :return: dictionary results of the nested list "response" -> "results"
    """
    for page in itertools.count(1):
        result = call_get(url.update_query({"page_size": page_size, "page": page}))
        yield from result["response"].get("results", [])
        if page == result["response"]["pages"]:
            return


class SearchResult(BaseModel):
    id: str
    type: str
    sectionId: str
    sectionName: str
    webPublicationDate: datetime
    webTitle: str
    webUrl: pydantic.AnyUrl
    apiUrl: pydantic.AnyUrl
    isHosted: bool
    pillarId: str
    pillarName: str


def iter_search(q: str) -> Iterable[SearchResult]:
    """
    Given a search query like "boris OR johnson", as documented on the Guardian
    API, return an iterable of SearchResult objects; the API documents the
    results ordered by the publication date.

    :param q: query, for example "boris OR johnson"
    :return: iterable of SearchResult objects
    """
    url = (URL("https://content.guardianapis.com") / "search").with_query({"q": q})
    return map(SearchResult.parse_obj, iter_call_get(url))


# Example query, first 10 results in the "Politics" section
first_10_politics = cytoolz.take(10, (
    item for item in iter_search("boris OR johnson") if item.sectionName == "Politics"
))

from cytoolz.curried import *

first_10_politics_fancy = map(
    compose(take(10), filter(lambda x: x.sectionName == "Politics")), iter_search("boris OR johnson")
)

print(list(first_10_politics_fancy))
