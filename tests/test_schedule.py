from datetime import datetime

import pytest

import modules.schedule as schedule_module
from helpers.config import ScheduleConfig
from modules.schedule import ScheduleThread


def make_thread(make_media_server_module, speedrr_config, **overrides):
    """Build a ScheduleThread without starting it.

    ScheduleThread only reads `_config.max_upload` / `_config.max_download`
    off its module, so the media-server module stand-in serves here too.
    """
    kwargs = {
        "start": "08:00",
        "end": "02:00",
        "days": ("all",),
        "upload": 100,
        "download": 50,
    }
    kwargs.update(overrides)
    config = ScheduleConfig(**kwargs)
    return ScheduleThread(config, make_media_server_module(speedrr_config))


def test_all_expands_to_every_weekday(make_media_server_module, speedrr_config):
    thread = make_thread(make_media_server_module, speedrr_config, days=("all",))
    assert thread._days_as_int == list(range(7))


def test_named_days_map_to_weekday_indices(make_media_server_module, speedrr_config):
    thread = make_thread(make_media_server_module, speedrr_config, days=("mon", "wed", "sun"))
    assert thread._days_as_int == [0, 2, 6]


def test_all_short_circuits_other_days(make_media_server_module, speedrr_config):
    # 'all' breaks out of the loop, so anything after it is ignored.
    thread = make_thread(make_media_server_module, speedrr_config, days=("all", "mon"))
    assert thread._days_as_int == list(range(7))


def test_absolute_reduction_values_pass_through(make_media_server_module, speedrr_config):
    thread = make_thread(make_media_server_module, speedrr_config, upload=120, download=90)
    assert thread._upload_reduce_by == 120
    assert thread._download_reduce_by == 90


def test_percentage_reduction_is_relative_to_configured_maximums(
    make_media_server_module, speedrr_config
):
    # speedrr_config has max_upload=500, max_download=400.
    thread = make_thread(make_media_server_module, speedrr_config, upload="100%", download="50%")
    assert thread._upload_reduce_by == 500.0
    assert thread._download_reduce_by == 200.0


def test_unlimited_reduction_is_infinity(make_media_server_module, speedrr_config):
    # Case-insensitive, and the value is the reduction, which main.py reads
    # as "remove the speed limit entirely".
    thread = make_thread(
        make_media_server_module, speedrr_config, upload="unlimited", download="Unlimited"
    )
    assert thread._upload_reduce_by == float("inf")
    assert thread._download_reduce_by == float("inf")


def test_next_occurrence_is_in_the_future_at_the_requested_time(
    make_media_server_module, speedrr_config
):
    thread = make_thread(make_media_server_module, speedrr_config, days=("all",))
    result = thread.calculate_next_occurrence(3, 30)

    assert result > datetime.now(thread.timezone)
    assert (result.hour, result.minute) == (3, 30)
    assert result.weekday() in thread._days_as_int


def test_next_occurrence_only_lands_on_configured_days(make_media_server_module, speedrr_config):
    thread = make_thread(make_media_server_module, speedrr_config, days=("mon",))
    result = thread.calculate_next_occurrence(12, 0)

    assert result.weekday() == 0
    assert result > datetime.now(thread.timezone)


def test_next_occurrence_never_crosses_a_month_boundary_incorrectly(
    make_media_server_module, speedrr_config, monkeypatch
):
    # Regression guard for upstream's "date is out of range for month" bug:
    # the search must use timedelta arithmetic, never day-number addition.
    # Freeze "now" to 31 January so day_offset=1 must land on 1 February; a
    # day-number-addition implementation (date.replace(day=day+offset)) would
    # attempt day=32 on this date and either raise or misbehave, while a
    # timedelta-based implementation rolls over to February correctly.
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 31, 23, 59, tzinfo=tz)

    monkeypatch.setattr(schedule_module, "datetime", FrozenDatetime)

    thread = make_thread(make_media_server_module, speedrr_config, days=("all",))
    result = thread.calculate_next_occurrence(0, 1)

    assert (result.year, result.month, result.day) == (2024, 2, 1)
    assert (result.hour, result.minute) == (0, 1)


def test_no_valid_day_raises(make_media_server_module, speedrr_config):
    thread = make_thread(make_media_server_module, speedrr_config, days=("mon",))
    thread._days_as_int = []
    with pytest.raises(ValueError, match="No valid next occurrence"):
        thread.calculate_next_occurrence(12, 0)
