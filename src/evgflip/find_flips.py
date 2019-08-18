from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor as Executor
from datetime import datetime
from typing import Dict, List

from boltons.iterutils import windowed_iter
from evergreen.api import EvergreenApi
from evergreen.build import Build
from evergreen.task import Task
from evergreen.version import Version
from structlog import get_logger

LOGGER = get_logger(__name__)

DEFAULT_THREADS = 16

FlipList = namedtuple("FlipList", [
    "revision",
    "flipped_tasks",
])

WorkItem = namedtuple("WorkItem", [
    "version",
    "version_prev",
    "version_next",
])


def _filter_empty_values(d: Dict) -> Dict:
    """
    Filter any empty items out of the given dictionary.
    :param d: dictionary to filter.
    :return: dictionary with empty values filtered out.
    """
    return {k: v for k, v in d.items() if v}


def _filter_builds(build: Build) -> bool:
    """
    Determine if build should be filtered.

    :param build: Build to check.
    :return: True if build should not be filtered.
    """
    if build.display_name.startswith("!"):
        return True
    return False


def _create_task_map(tasks: [Task]) -> Dict:
    """
    Create a dictionary of tasks by display_name.

    :param tasks: List of tasks to map.
    :return: Dictionary of tasks by display_name.
    """
    return {task.display_name: task for task in tasks}


def _is_task_a_flip(task: Task, tasks_prev: Dict, tasks_next: Dict) -> bool:
    """
    Determine if given task has flipped to states in this version.

    :param task: Task to check.
    :param tasks_prev: Dictionary of tasks in previous version.
    :param tasks_next: Dictionary of tasks in next version.
    :return: True if task has flipped in this version.
    """
    if task.activated and not task.is_success():
        task_prev = tasks_prev.get(task.display_name)
        if not task_prev or task_prev.status != task.status:
            # this only failed once, don't count it.
            return False
        task_next = tasks_next.get(task.display_name)
        if not task_next or task_next.status == task.status:
            # this was already failing, don't count it.
            return False
        return True
    return False


def _flips_for_build(build: Build, version_prev: Version, version_next: Version) -> List[str]:
    """
    Build a list of tasks that flipped in this build.

    :param build: Build to check.
    :param version_prev: Previous version to check against.
    :param version_next: Next version to check against.
    :return: List of tasks that flipped in given build.
    """
    build_prev = version_prev.build_by_variant(build.build_variant)
    build_next = version_next.build_by_variant(build.build_variant)

    tasks = build.get_tasks()
    tasks_prev = _create_task_map(build_prev.get_tasks())
    tasks_next = _create_task_map(build_next.get_tasks())
    flipped_tasks = [
        task.display_name for task in tasks
        if _is_task_a_flip(task, tasks_prev, tasks_next)
    ]

    return flipped_tasks


def _flips_for_version(work_item: WorkItem):
    """
    Build a dictionary of tasks that flipped for builds in this version.

    :param work_item: Container of work items to analyze.
    :return: FlipList of what tasks flipped.
    """
    version = work_item.version
    version_prev = work_item.version_prev
    version_next = work_item.version_next

    builds = [build for build in version.get_builds() if _filter_builds(build)]

    flipped_tasks = {
        b.build_variant: _flips_for_build(b, version_prev, version_next)
        for b in builds
    }

    return FlipList(version.revision, _filter_empty_values(flipped_tasks))


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

    with Executor(max_workers=n_threads) as exe:
        jobs = []
        for version_prev, version, version_next in windowed_iter(version_iterator, 3):
            log = LOGGER.bind(version=version.version_id)
            log.debug("Starting to look")
            if version.create_time < look_back:
                log.debug("done", create_time=version.create_time)
                break

            work_item = WorkItem(version, version_prev, version_next)
            jobs.append(exe.submit(_flips_for_version, work_item))

        results = [job.result() for job in jobs]

    return {r.revision: r.flipped_tasks for r in results if r.flipped_tasks}
