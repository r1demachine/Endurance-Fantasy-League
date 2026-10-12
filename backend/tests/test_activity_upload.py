"""Tests for uploaded activity parsing, calculated HR load and preview-token integrity."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from pydantic import ValidationError

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/efl-upload-tests.db")
os.environ.setdefault("JWT_SECRET", "unit-test-jwt-secret-value-longer-than-32-characters")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("REDIS_URL", "")

from app.services.xp_v6 import UPLOAD_TSS_FACTOR, resolve_training_load

from app.routers.upload import (
    HeartRateSettingsUpdate,
    InvalidActivityFile,
    UnsupportedActivityFile,
    _decode_preview,
    _encode_preview,
    _finalise_file_metrics,
    _parse_activity_file,
    _decode_xml_utf8,
)


class ActivityFileParsingTests(unittest.TestCase):
    def test_tcx_extracts_duration_distance_hr_and_hard_time(self):
        tcx = b"""<?xml version="1.0"?>
        <TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
          <Activities><Activity Sport="Biking"><Id>2026-10-01T10:00:00Z</Id><Lap StartTime="2026-10-01T10:00:00Z">
            <TotalTimeSeconds>20</TotalTimeSeconds><DistanceMeters>200</DistanceMeters>
            <Track><Trackpoint><Time>2026-10-01T10:00:00Z</Time><AltitudeMeters>100</AltitudeMeters><HeartRateBpm><Value>170</Value></HeartRateBpm></Trackpoint>
            <Trackpoint><Time>2026-10-01T10:00:10Z</Time><AltitudeMeters>102</AltitudeMeters><HeartRateBpm><Value>175</Value></HeartRateBpm></Trackpoint>
            <Trackpoint><Time>2026-10-01T10:00:20Z</Time><AltitudeMeters>101</AltitudeMeters><HeartRateBpm><Value>180</Value></HeartRateBpm></Trackpoint></Track>
          </Lap></Activity></Activities>
        </TrainingCenterDatabase>"""
        parsed = _parse_activity_file(tcx, ".tcx", 165, 195)
        self.assertEqual(parsed["sport_type"], "RIDE")
        self.assertEqual(parsed["moving_time"], 20)
        self.assertEqual(parsed["distance"], 200)
        self.assertEqual(parsed["elevation_gain"], 2)
        self.assertEqual(parsed["hard_secs"], 20)
        self.assertGreater(parsed["training_load"], 0)
        self.assertEqual(parsed["start_date"], "2026-10-01T10:00:00")

    def test_hrss_is_100_for_one_hour_at_lthr(self):
        start = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 180, "ele": None}
            for seconds in range(0, 3601, 10)
        ]
        parsed = _finalise_file_metrics(
            start=start,
            moving_time=3600,
            elapsed_time=3600,
            distance=10000,
            elevation_gain=0,
            average_hr=180,
            maximum_hr=180,
            sport_type="RIDE",
            samples=samples,
            lthr=180,
            user_max_hr=190,
            resting_hr=50,
        )
        self.assertAlmostEqual(parsed["training_load"], 100.0, delta=0.5)
        self.assertEqual(parsed["load_method"], "hrss")

    def test_hrss_reference_ride_is_near_60_load_points(self):
        start = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 141, "ele": None}
            for seconds in range(0, 5351, 10)
        ]
        samples[-1]["hr"] = 175
        parsed = _finalise_file_metrics(
            start=start,
            moving_time=5350,
            elapsed_time=5350,
            distance=37010,
            elevation_gain=161,
            average_hr=141,
            maximum_hr=175,
            sport_type="RIDE",
            samples=samples,
            lthr=180,
            user_max_hr=190,
            resting_hr=50,
        )
        self.assertGreater(parsed["training_load"], 50)
        self.assertLess(parsed["training_load"], 70)
        self.assertEqual(parsed["load_method"], "hrss")

    def test_local_start_time_uses_user_timezone_when_file_timestamp_is_utc(self):
        from zoneinfo import ZoneInfo

        start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=3)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 150, "ele": None}
            for seconds in range(0, 61, 10)
        ]
        parsed = _finalise_file_metrics(
            start=start,
            moving_time=60,
            elapsed_time=60,
            distance=500,
            elevation_gain=0,
            average_hr=150,
            maximum_hr=160,
            sport_type="RIDE",
            samples=samples,
            lthr=160,
            user_max_hr=190,
            resting_hr=50,
            user_timezone="Asia/Krasnoyarsk",
        )
        self.assertEqual(parsed["start_date"], start.replace(tzinfo=None).isoformat())
        expected_local = start.astimezone(ZoneInfo("Asia/Krasnoyarsk")).replace(tzinfo=None)
        self.assertEqual(parsed["start_date_local"], expected_local.isoformat())

    def test_nonzero_file_offset_is_preserved_as_local_wall_time(self):
        offset = timezone(timedelta(hours=2))
        start = datetime.now(timezone.utc).astimezone(offset).replace(microsecond=0) - timedelta(minutes=3)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 150, "ele": None}
            for seconds in range(0, 61, 10)
        ]
        parsed = _finalise_file_metrics(
            start=start,
            moving_time=60,
            elapsed_time=60,
            distance=500,
            elevation_gain=0,
            average_hr=150,
            maximum_hr=160,
            sport_type="RIDE",
            samples=samples,
            lthr=160,
            user_max_hr=190,
            resting_hr=50,
            user_timezone="UTC",
        )
        self.assertEqual(parsed["start_date_local"], start.replace(tzinfo=None).isoformat())
        self.assertEqual(parsed["start_date"], start.astimezone(timezone.utc).replace(tzinfo=None).isoformat())

    def test_rejects_future_and_older_than_thirty_days(self):
        for start in (
            datetime.now(timezone.utc) + timedelta(days=1),
            datetime.now(timezone.utc) - timedelta(days=31),
        ):
            samples = [
                {"time": start + timedelta(seconds=seconds), "hr": 150, "ele": None}
                for seconds in range(0, 61, 10)
            ]
            with self.subTest(start=start), self.assertRaises(InvalidActivityFile):
                _finalise_file_metrics(
                    start=start, moving_time=60, elapsed_time=60, distance=100,
                    elevation_gain=0, average_hr=150, maximum_hr=160,
                    sport_type="RIDE", samples=samples, lthr=160,
                    user_max_hr=190, resting_hr=50,
                )

    def test_requires_heart_rate_stream_covering_half_duration(self):
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 150, "ele": None}
            for seconds in (0, 10, 100, 200)
        ]
        with self.assertRaisesRegex(InvalidActivityFile, "не менее 50%"):
            _finalise_file_metrics(
                start=start, moving_time=200, elapsed_time=200, distance=100,
                elevation_gain=0, average_hr=150, maximum_hr=160,
                sport_type="RIDE", samples=samples, lthr=160,
                user_max_hr=190, resting_hr=50,
            )

    def test_duration_cannot_exceed_sample_span_by_more_than_twenty_percent(self):
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 150, "ele": None}
            for seconds in range(0, 61, 10)
        ]
        with self.assertRaisesRegex(InvalidActivityFile, "более чем на 20%"):
            _finalise_file_metrics(
                start=start, moving_time=100, elapsed_time=100, distance=100,
                elevation_gain=0, average_hr=150, maximum_hr=160,
                sport_type="RIDE", samples=samples, lthr=160,
                user_max_hr=190, resting_hr=50,
            )

    def test_elapsed_duration_cannot_exceed_sample_span_by_more_than_twenty_percent(self):
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 150, "ele": None}
            for seconds in range(0, 61, 10)
        ]
        with self.assertRaisesRegex(InvalidActivityFile, "более чем на 20%"):
            _finalise_file_metrics(
                start=start, moving_time=50, elapsed_time=100, distance=100,
                elevation_gain=0, average_hr=150, maximum_hr=160,
                sport_type="RIDE", samples=samples, lthr=160,
                user_max_hr=190, resting_hr=50,
            )

    def test_xml_rejects_non_utf8_declaration(self):
        with self.assertRaisesRegex(InvalidActivityFile, "UTF-8"):
            _decode_xml_utf8(b'<?xml version="1.0" encoding="ISO-8859-1"?><gpx></gpx>')

    def test_extension_must_match_content(self):
        with self.assertRaises(UnsupportedActivityFile):
            _parse_activity_file(b"<TrainingCenterDatabase></TrainingCenterDatabase>", ".gpx", None, None)

    def test_archive_and_short_files_are_rejected(self):
        with self.assertRaises(InvalidActivityFile):
            _parse_activity_file(b"tiny", ".tcx", None, None)
        with self.assertRaises(UnsupportedActivityFile):
            _parse_activity_file(b"PK\x03\x04" + b"\0" * 32, ".fit", None, None)

    def test_gpx_extracts_recorded_heart_rate(self):
        gpx = b"""<?xml version="1.0"?>
        <gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
          <trk><name>not persisted</name><trkseg>
            <trkpt lat="55.0" lon="37.0"><ele>100</ele><time>2026-10-01T10:00:00Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>170</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>
            <trkpt lat="55.001" lon="37.001"><ele>103</ele><time>2026-10-01T10:00:10Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>175</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>
            <trkpt lat="55.002" lon="37.002"><ele>101</ele><time>2026-10-01T10:00:20Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>180</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>
          </trkseg></trk>
        </gpx>"""
        parsed = _parse_activity_file(gpx, ".gpx", 165, 195)
        self.assertEqual(parsed["moving_time"], 20)
        self.assertGreater(parsed["distance"], 0)
        self.assertEqual(parsed["hard_secs"], 20)
        self.assertEqual(parsed["average_heartrate"], 175)

    def test_doctype_and_entity_declarations_are_rejected(self):
        gpx = b'<!DOCTYPE gpx [<!ENTITY x "x">]><gpx></gpx>'
        with self.assertRaises(InvalidActivityFile):
            _parse_activity_file(gpx, ".gpx", None, None)

    def test_auto_calibrates_max_hr_and_lthr_from_recorded_samples(self):
        start = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
        samples = [
            {"time": start + timedelta(seconds=seconds), "hr": 180 if seconds == 3600 else 175, "ele": None}
            for seconds in range(0, 3601, 10)
        ]
        parsed = _finalise_file_metrics(
            start=start,
            moving_time=3600,
            elapsed_time=3600,
            distance=10000,
            elevation_gain=0,
            average_hr=175,
            maximum_hr=180,
            sport_type="RIDE",
            samples=samples,
            lthr=165,
            user_max_hr=175,
        )
        self.assertEqual(parsed["auto_zone_updates"]["max_hr"], 180)
        self.assertEqual(parsed["auto_zone_updates"]["lthr"], 174)


class HeartRateSettingsTests(unittest.TestCase):
    def test_sensible_boundaries(self):
        self.assertEqual(HeartRateSettingsUpdate(lthr=80, max_hr=100).lthr, 80)
        self.assertEqual(HeartRateSettingsUpdate(lthr=220, max_hr=240).max_hr, 240)
        with self.assertRaises(ValidationError):
            HeartRateSettingsUpdate(lthr=79)
        with self.assertRaises(ValidationError):
            HeartRateSettingsUpdate(max_hr=241)
        with self.assertRaises(ValidationError):
            HeartRateSettingsUpdate(resting_hr=101)

    def test_uploaded_training_load_uses_the_configured_attenuation(self):
        load, source = resolve_training_load({
            "training_load": 100,
            "moving_time": 3600,
            "intensity": 0.8,
            "sport_type": "RIDE",
            "is_manual": False,
            "source": "UPLOAD_TELEGRAM",
        })
        self.assertAlmostEqual(UPLOAD_TSS_FACTOR, 0.8)
        self.assertAlmostEqual(load, 80.0)
        self.assertEqual(source, "estimated")

    def test_preview_token_is_signed_and_expiring(self):
        payload = {
            "user_id": 7,
            "nonce": "nonce-test",
            "expires_at": int(datetime.now(timezone.utc).timestamp()) + 60,
            "start_date": "2026-10-01T10:00:00",
        }
        token = _encode_preview(payload)
        self.assertEqual(_decode_preview(token)["user_id"], 7)
        encoded, signature = token.split(".", 1)
        tampered_encoded = ("A" if encoded[0] != "A" else "B") + encoded[1:]
        altered = tampered_encoded + "." + signature
        with self.assertRaises(Exception):
            _decode_preview(altered)


if __name__ == "__main__":
    unittest.main()
