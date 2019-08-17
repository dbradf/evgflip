from collections import defaultdict, namedtuple
from datetime import datetime
from itertools import tee
from typing import Iterable, Dict

from evergreen.api import EvergreenApi
from evergreen.build import Build
from evergreen.task import Task
from structlog import get_logger

from evgflip.worker import WorkerResults, ThreadWorker

LOGGER = get_logger(__name__)

DEFAULT_THREADS = 16

FlipList = namedtuple("FlipList", [
    "revision",
    "flipped_tasks",
])


class FoundFlips(WorkerResults):
    def __init__(self):
        self.flips = defaultdict(list)

    def add_result(self, result: FlipList):
        if result.flipped_tasks:
            self.flips[result.revision] = result.flipped_tasks


class WorkItem:
    def __init__(self, version, version_prev, version_next):
        self.version = version
        self.version_prev = version_prev
        self.version_next = version_next


def threewise(iterable: Iterable) -> Iterable:
    """
    Iterate over each item in iterable with the next two items in the list.

    See: https://docs.python.org/3/library/itertools.html#itertools-recipes

    :param iterable: Iterable to iterate over.
    :return: Threewise iterator.
    """
    a, b, c = tee(iterable, 3)
    next(b, None)
    next(c, None)
    next(c, None)
    return zip(a, b, c)


def _filter_builds(build: Build) -> bool:
    """
    Determine if build should be filtered.

    :param build: Build to check.
    :return: True if build should not be filtered.
    """
    if build.display_name.startswith("!"):
        return True
    return False


def _find_task(tasks: [Task], task_name: str):
    task_list = [task for task in tasks if task.display_name == task_name]
    if task_list:
        return task_list[0]
    return None


def _flips_for_version(work_item: WorkItem):
    version = work_item.version
    version_prev = work_item.version_prev
    version_next = work_item.version_next

    log = LOGGER.bind(version=version.version_id)
    builds = [build for build in version.get_builds() if _filter_builds(build)]

    flipped_tasks = defaultdict(list)
    for b in builds:
        log.debug("checking build", build=b.build_variant)
        b_prev = version_prev.build_by_variant(b.build_variant)
        b_next = version_next.build_by_variant(b.build_variant)
        tasks = b.get_tasks()
        tasks_prev = b_prev.get_tasks()
        tasks_next = b_next.get_tasks()
        for task in tasks:
            if task.activated and not task.is_success():
                task_prev = _find_task(tasks_prev, task.display_name)
                if not task_prev or task_prev.status != task.status:
                    # this only failed once, don't count it.
                    continue
                task_next = _find_task(tasks_next, task.display_name)
                if not task_next or task_next.status == task.status:
                    # this was already failing, don't count it.
                    continue

                # This is a new failure introduction.
                flipped_tasks[b.build_variant].append(task.display_name)

    return FlipList(version.revision, flipped_tasks)


def find(project: str, look_back: datetime, evg_api: EvergreenApi,
         n_threads: int = DEFAULT_THREADS) -> Dict:
    """
    Find test flips in the evergreen project.

    :param project: Evergreen project to analyze.
    :param look_back: Look at commits until the given project.
    :param evg_api: Evergreen API.
    :param n_threads: Number of threads to use.
    :return: Dictionary of commits that introduced task flips.
    """
    LOGGER.debug("Starting find_flips iteration")
    version_iterator = evg_api.versions_by_project(project)
    worker = ThreadWorker(n_threads, _flips_for_version, FoundFlips())

    for version_prev, version, version_next in threewise(version_iterator):
        log = LOGGER.bind(version=version.version_id)
        log.debug("Starting to look")
        if version.create_time < look_back:
            log.info("done", create_time=version.create_time)
            break

        work_item = WorkItem(version, version_prev, version_next)
        worker.queue_work(work_item)

    worker.start()
    worker.block()

    flipped_tasks = worker.results
    return flipped_tasks.flips
