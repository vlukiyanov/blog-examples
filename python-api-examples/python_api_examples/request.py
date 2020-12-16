import json
from functools import lru_cache
from typing import List

import pandas as pd
import requests
from haversine import haversine
from pydantic import BaseModel
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
    return requests.get(url.update_query(get_id_key())).text


API_ENDPOINT = URL("https://api.tfl.gov.uk/")


@lru_cache()
def tube_line_ids() -> List[str]:
    return [
        item["id"]
        for item in json.loads(
            call_get(API_ENDPOINT / "Line" / "Mode" / "tube" / "Route")
        )
    ]


class LineStopPointInfo(BaseModel):
    name: str
    distance: float
    connections: int


def parse_result(result) -> LineStopPointInfo:
    return LineStopPointInfo(
        name=result["commonName"],
        distance=haversine((51.509865, -0.118092), (result["lat"], result["lon"])),
        connections=len(
            [
                item["id"]
                for item in result.get("lines", [])
                if item["id"] in tube_line_ids()
            ]
        ),
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


df = pd.concat([line_stop_df(line) for line in tube_line_ids()])
