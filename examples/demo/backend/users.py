from enum import Enum

from fastapi import FastAPI, HTTPException

app = FastAPI()


class Repository:
    async def fetch(self, user_id: str):
        raise NotImplementedError


repository = Repository()


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = await load_user(user_id)
    if user is None:
        raise HTTPException(status_code=404)
    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(status_code=403)
    return user


async def load_user(user_id: str):
    return await repository.fetch(user_id)
