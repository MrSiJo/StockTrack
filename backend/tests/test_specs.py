import pytest
from stocktrack.services.specs import parse_watts

@pytest.mark.parametrize("title,expected", [
    ("Uksol 435W All Black Solar Panel", 435),
    ("Longi Hi Mo X10 475W All Black Monofacial Solar Panel", 475),
    ("Longi Solar Hi Mo 5M 410Wp Full Black Pv Module", 410),
    ("Longi Solar Hi Mo X6 Max 620Wp Pv Module", 620),
    ("Some 0.62kW Panel", 620),
    ("Meaco Cirro 12k BTU Cooling Only Air Conditioner", None),
    ("No numbers here", None),
    ("", None),
])
def test_parse_watts(title, expected):
    assert parse_watts(title) == expected
