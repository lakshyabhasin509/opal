import asyncio
from typing import List, Optional, Coroutine

from opal.common.logger import logger
from opal.common.git.repo_watcher import RepoWatcher


class RepoWatcherTask:
    """
    Manages the asyncio tasks of the repo watcher
    """
    def __init__(self, repo_watcher: RepoWatcher):
        self._watcher = repo_watcher
        self._tasks: List[asyncio.Task] = []
        self._should_stop: Optional[asyncio.Event] = None

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()

    def start(self):
        """
        starts the repo watcher and registers a failure callback to terminate gracefully
        """
        logger.info("Launching repo watcher")
        self._watcher.on_git_failed(self._fail)
        self._tasks.append(asyncio.create_task(self._watcher.run()))
        self._init_should_stop()

    async def stop(self):
        """
        stops all repo watcher tasks
        """
        logger.info("Stopping repo watcher")
        await self._watcher.stop()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def trigger(self):
        """
        triggers the repo watcher from outside to check for changes (git pull)
        """
        self._tasks.append(asyncio.create_task(self._watcher.check_for_changes()))

    def wait_until_should_stop(self) -> Coroutine:
        """
        waits until self.signal_stop() is called on the watcher.
        allows us to keep the repo watcher context alive until
        signalled to stop from outside.
        """
        self._init_should_stop()
        return self._should_stop.wait()

    def signal_stop(self):
        """
        signal the repo watcher it should stop.
        """
        self._init_should_stop()
        self._should_stop.set()

    def _init_should_stop(self):
        if self._should_stop is None:
            self._should_stop = asyncio.Event()

    async def _fail(self, exc: Exception):
        """
        called when the watcher fails, and stops all tasks gracefully
        """
        logger.error("watcher failed with exception", watcher_exception=exc)
        await self.stop()