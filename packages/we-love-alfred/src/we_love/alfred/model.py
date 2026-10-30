from pydantic import BaseModel, ConfigDict


class AlfredBaseModel(BaseModel):
    """Models accepting asynchronous paths."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
