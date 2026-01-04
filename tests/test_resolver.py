import asyncio
import unittest
from unittest.mock import MagicMock

from cortex.resolver import DependencyResolver


class TestDependencyResolver(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.resolver = DependencyResolver(api_key="test", provider="ollama")
        # Mock the handler's ask method
        self.resolver.handler.ask = MagicMock()

    async def test_basic_conflict_resolution(self):
        """Ensure coroutines are awaited to fix TypeError."""
        conflict_data = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"},
        }

        self.resolver.handler.ask.return_value = (
            '[{"id": 1, "type": "Recommended", "action": "Update", "risk": "Low"}]'
        )

        # AWAIT the result to fix "coroutine has no len()"
        strategies = await self.resolver.resolve(conflict_data)
        self.assertEqual(len(strategies), 1)

    async def test_missing_keys_raises_error(self):
        bad_data = {"dependency": "lib-x"}
        with self.assertRaises(KeyError):
            await self.resolver.resolve(bad_data)
