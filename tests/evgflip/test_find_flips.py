from unittest.mock import MagicMock

import evgflip.find_flips as under_test


class TestFilterEmptyValues:
    def test_empty_dictionary(self):
        filtered_dict = under_test._filter_empty_values({})
        assert {} == filtered_dict

    def test_with_values_no_empty_items(self):
        test_dict = {
            "key1": {},
            "key2": "something",
            "key3": [],
            "key4": {"another things"}
        }
        filtered_dict = under_test._filter_empty_values(test_dict)

        assert "key1" not in filtered_dict
        assert "key3" not in filtered_dict
        assert "key2" in filtered_dict
        assert "key4" in filtered_dict


class TestCreateTaskMap:
    def test_empty_list(self):
        task_map = under_test._create_task_map([])
        assert {} == task_map

    def test_list_of_tasks(self):
        mock_task_list = [MagicMock(display_name=f"task {i}") for i in range(5)]
        task_map = under_test._create_task_map(mock_task_list)

        assert task_map["task 0"] == mock_task_list[0]
        assert len(task_map) == len(mock_task_list)


class TestIsTaskAFlip:
    def test_non_activated_task_is_not_a_flip(self):
        mock_task = MagicMock(activated=False)

        assert not under_test._is_task_a_flip(mock_task, {}, {})

    def test_successful_task_is_not_a_flip(self):
        mock_task = MagicMock(activate=True)
        mock_task.is_success.return_value = True

        assert not under_test._is_task_a_flip(mock_task, {}, {})

    def test_no_previous_task_is_not_a_flip(self):
        mock_task = MagicMock(activate=True)
        mock_task.is_success.return_value = False

        assert not under_test._is_task_a_flip(mock_task, {}, {})

    def test_previous_task_changes_is_not_a_flip(self):
        mock_task = MagicMock(activate=True, status="failed")
        mock_task.is_success.return_value = False

        mock_prev_task = MagicMock()
        tasks_prev = {mock_task.display_name: mock_prev_task}

        assert not under_test._is_task_a_flip(mock_task, tasks_prev, {})

    def test_next_task_does_not_exist(self):
        mock_task = MagicMock(activate=True, status="failed")
        mock_task.is_success.return_value = False

        mock_prev_task = MagicMock(status=mock_task.status)
        tasks_prev = {mock_task.display_name: mock_prev_task}

        assert not under_test._is_task_a_flip(mock_task, tasks_prev, {})

    def test_next_task_does_not_change_status(self):
        mock_task = MagicMock(activate=True, status="failed")
        mock_task.is_success.return_value = False

        mock_prev_task = MagicMock(status=mock_task.status)
        tasks_prev = {mock_task.display_name: mock_prev_task}

        mock_next_task = MagicMock(status=mock_task.status)
        tasks_next = {mock_task.display_name: mock_next_task}

        assert not under_test._is_task_a_flip(mock_task, tasks_prev, tasks_next)

    def test_was_a_flip(self):
        mock_task = MagicMock(activate=True, status="failed")
        mock_task.is_success.return_value = False

        mock_prev_task = MagicMock(status=mock_task.status)
        tasks_prev = {mock_task.display_name: mock_prev_task}

        mock_next_task = MagicMock(status="success")
        tasks_next = {mock_task.display_name: mock_next_task}

        assert under_test._is_task_a_flip(mock_task, tasks_prev, tasks_next)
