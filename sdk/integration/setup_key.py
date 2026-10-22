"""Run inside the server's container (built from glyphh-ai/server's ada-cloud-data): a person and their org made
straight in the database, as the server's own load script does, then an API key made through the Ada API by that
person's sign-in. Prints the key, nothing else. Never against production."""

import asyncio
import os
import sys
import uuid

import httpx
from sqlalchemy import insert

from glyphh_server.config import get_settings
from glyphh_server.db.engine import make_engine
from glyphh_server.models import Install
from glyphh_server.ops.auth import tokens
from glyphh_server.ops.orgs import new_person


async def signed_in() -> str:
    engine = make_engine(get_settings().database_url)
    async with engine.begin() as conn:
        user_id = await new_person(conn, f"sdk-{uuid.uuid4().hex[:8]}@sdk.test", "SDK Test")
        values = {"user_id": user_id, "machine_id": uuid.uuid4().hex, "name": "sdk", "surface": "desktop"}
        values["mod_version"] = "1.0.0"
        install_id = (await conn.execute(insert(Install).values(values).returning(Install.id))).scalar_one()
        token = await tokens.issue(conn, install_id)
    await engine.dispose()
    return token


async def main() -> None:
    url = os.environ.get("ADA_URL", "http://ada:8080")
    token = await signed_in()
    async with httpx.AsyncClient(base_url=url, timeout=30) as http:
        made = await http.post("/v1/keys", json={"name": "sdk integration"}, headers={"authorization": f"Bearer {token}"})
        made.raise_for_status()
    sys.stdout.write(made.json()["key"] + "\n")


if __name__ == "__main__":
    asyncio.run(main())
