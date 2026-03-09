from asyncstdlib._lrucache import MemoizedLRUAsyncCallable
from pydantic import BaseModel, ConfigDict


class AlfredBaseModel(BaseModel):
    """BaseModel with arbitrary_types_allowed for anyio.Path and async cache support."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        ignored_types=(MemoizedLRUAsyncCallable,),
    )
