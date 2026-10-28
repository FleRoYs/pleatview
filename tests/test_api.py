"""Tests for the TV API client."""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from custom_components.pleatview.api import (
    CannotConnect,
    InvalidAuth,
    InvalidPin,
    PleatViewClient,
    RequestRejected,
)

from .fake_tv import FakeTV


async def test_pair_and_commands(fake_tv: FakeTV) -> None:
    async with aiohttp.ClientSession() as session:
        client = PleatViewClient(session, "127.0.0.1", fake_tv.port)
        assert (await client.get_info())["id"] == "tv-1"
        with pytest.raises(InvalidPin):
            await client.pair("000000", "test")
        token = await client.pair(fake_tv.pin, "test")
        assert token in fake_tv.tokens
        await client.command("show_dashboard", path="/lovelace/1", duration=None)
        assert fake_tv.commands == [{"command": "show_dashboard", "path": "/lovelace/1"}]
        with pytest.raises(RequestRejected, match="explode"):
            await client.command("explode")


async def test_errors(fake_tv: FakeTV) -> None:
    async with aiohttp.ClientSession() as session:
        with pytest.raises(InvalidAuth):
            await PleatViewClient(session, "127.0.0.1", fake_tv.port, "forged").get_state()
        with pytest.raises(CannotConnect):
            await PleatViewClient(session, "127.0.0.1", 1).get_info()


async def test_event_stream(fake_tv: FakeTV) -> None:
    received: list[dict] = []
    async with aiohttp.ClientSession() as session:
        client = PleatViewClient(session, "127.0.0.1", fake_tv.port, fake_tv.issue_token())
        task = asyncio.create_task(client.listen(received.append))
        await fake_tv.wait_for_stream()
        await fake_tv.push(power="standby")
        async with asyncio.timeout(5):
            while len(received) < 2:
                await asyncio.sleep(0.01)
        assert received[0]["power"] == "on"
        assert received[1]["power"] == "standby"
        fake_tv.close_streams()
        await asyncio.wait_for(task, 5)  # returns when the TV closes the stream


async def test_event_stream_rejects_bad_token(fake_tv: FakeTV) -> None:
    async with aiohttp.ClientSession() as session:
        with pytest.raises(InvalidAuth):
            await PleatViewClient(session, "127.0.0.1", fake_tv.port, "forged").listen(lambda _: None)
