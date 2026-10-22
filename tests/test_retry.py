from unittest.mock import call

from retry import MAX_ATTEMPTS, backoff_sleep


def test_backoff_sleep_basic_case(no_sleep):
    for attempt in range(MAX_ATTEMPTS):
        backoff_sleep(attempt)

    assert no_sleep.call_args_list == [call(1), call(2), call(4), call(8)]
