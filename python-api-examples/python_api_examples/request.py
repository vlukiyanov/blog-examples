import json
from typing import List

import pandas as pd
import requests
from pydantic import BaseModel
from ratelimit import RateLimitException, limits
from tenacity import *
from yarl import URL

from data_from_apis_example.secrets import APP_ID, APP_KEY


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
    return requests.get(url.update_query(get_id_key())).text


API_ENDPOINT = URL("https://api.tfl.gov.uk/")


class LineStopPointInfo(BaseModel):
    name: str
    lat: float
    lon: float
    connections: int


def parse_result(result) -> LineStopPointInfo:
    return LineStopPointInfo(
        name=result["commonName"],
        lat=result["lat"],
        lon=result["lon"],
        connections=len(result.get("lines", [])),
    )


def line_stop_points(line_id: str) -> List[LineStopPointInfo]:
    return [
        parse_result(result)
        for result in json.loads(
            call_get(API_ENDPOINT / "Line" / line_id / "StopPoints")
        )
    ]


def line_stop_df(line_id: str) -> pd.DataFrame:
    return pd.DataFrame([item.dict() for item in line_stop_points(line_id)])


print(line_stop_points("victoria"))
