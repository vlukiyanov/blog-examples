import json
from functools import lru_cache
from typing import List

import pandas as pd
import requests
from haversine import haversine
from pydantic import BaseModel, conint, confloat
from ratelimit import RateLimitException, limits
from tenacity import *
from yarl import URL

from python_api_examples.secrets import APP_ID, APP_KEY


def get_id_key():
    return {"app_id": APP_ID, "app_key": APP_KEY}


@retry(
    wait=wait_exponential(max=60, min=1),
    stop=stop_after_attempt(3),
)
@retry(
    retry=retry_if_exception_type(RateLimitException),
    wait=wait_fixed(1),
    stop=stop_after_delay(60),
)
@limits(calls=500, period=60)
def call_get(url: URL) -> str:
    """
    Make a generic call to the TfL API. This function handles rate limits and retries,
    as well as ensuring that the API call has the app_id and app_key appended to the
    call.

    :param url: URL to make a GET request on for the TfL API
    :return: decoded string of response
    """
    return requests.get(url.update_query(get_id_key())).text


API_ENDPOINT = URL("https://api.tfl.gov.uk/")


@lru_cache()
def tube_line_ids() -> List[str]:
    """
    Get a list of all tube line ids, these can then be used to call endpoints
    of "Line" / line_id for line_id in this list; after the first call this data
    is cached in memory.

    :return: list of string line_ids e.g. "victoria"
    """
    return [
        item["id"]
        for item in json.loads(
            call_get(API_ENDPOINT / "Line" / "Mode" / "tube" / "Route")
        )
    ]


class LineStopPointInfo(BaseModel):
    name: str
    distance: confloat(ge=0)  # from the centre of London, (51.509865, -0.118092)
    connections: conint(ge=0)


def parse_result(result) -> LineStopPointInfo:
    """
    Apply our domain-specific parsing logic to an element of the /Line/line_id/StopPoints
    TfL API call, where line_id is the id of a tube line e.g. "victoria".

    :param result: dictionary representing a single result
    :return: parsed LineStopPointInfo objects
    """
    return LineStopPointInfo(
        name=result["commonName"],
        distance=haversine((51.509865, -0.118092), (result["lat"], result["lon"])),
        connections=len(
            [
                item["id"]
                for item in result.get("lines", [])
                if item["id"] in tube_line_ids()
            ]
        ) - 1,  # one result is always for the given line
    )


def line_stop_points(line_id: str) -> List[LineStopPointInfo]:
    """
    For a give tube line, get a list of stop points, and apply domain-specific parsing logic to get
    a list of LineStopPointInfo objects.

    :param line_id: string line id e.g. "victoria"
    :return: list of parsed LineStopPointInfo objects
    """
    return [
        parse_result(result)
        for result in json.loads(
            call_get(API_ENDPOINT / "Line" / line_id / "StopPoints")
        )
    ]


def line_stop_df(line_id: str) -> pd.DataFrame:
    """
    For a given tube line, get the results of line_stop_points and convert into a pandas DataFrame
    with columns name, distance (from the centre of London) and (number of) connections.

    :param line_id: string line id e.g. "victoria"
    :return: parsed DataFrame with columns name, distance and connections
    """
    return pd.DataFrame([item.dict() for item in line_stop_points(line_id)])


df = pd.concat([line_stop_df(line) for line in tube_line_ids()])
