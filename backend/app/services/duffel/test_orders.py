"""Create a Duffel TEST booking to work with. Owner: Jian.

Searches the given route about a month out and books the cheapest Duffel Airways (ZZ) offer, the only airline
test mode lets us book, paid from the test balance. Passengers are obviously fake. Test mode only: DuffelClient
refuses anything but a duffel_test_ token.
"""
from datetime import date, timedelta

from ..errors import ServiceError
from .client import DuffelApiError, DuffelClient, DuffelTransportError
from .service import UNREACHABLE, DuffelServiceError, _api_error

ROUTES = {"jfk_lax": ("JFK", "LAX"), "lhr_ltn": ("LHR", "LTN")}  # LHR to LTN is where Duffel simulates airline changes
TEST_AIRLINE_IATA = "ZZ"
DAYS_AHEAD = 30


def create_test_booking(client: DuffelClient, route: str, passengers: int = 1, today: date | None = None) -> str:
    """Create a test order and return its id (ord_...)."""
    if route not in ROUTES:
        raise ServiceError(f"Unknown route. Choose from: {', '.join(ROUTES)}")
    if not 1 <= passengers <= 3:
        raise ServiceError("passengers must be between 1 and 3")
    origin, destination = ROUTES[route]
    day = ((today or date.today()) + timedelta(days=DAYS_AHEAD)).isoformat()
    try:
        search = client.search_offers(origin, destination, day, passengers=passengers)["data"]
        offers = [o for o in search.get("offers", []) if (o.get("owner") or {}).get("iata_code") == TEST_AIRLINE_IATA]
        if not offers:
            raise ServiceError(f"No Duffel Airways test offer was available for {origin} to {destination}.")
        offer = min(offers, key=lambda o: float(o["total_amount"]))
        people = [
            {
                "id": passenger["id"], "title": "mr", "gender": "m", "given_name": "Test",
                "family_name": f"Traveler{chr(64 + index)}",  # letters only: Duffel rejects digits in names
                "born_on": "1990-01-01", "email": f"test.traveler{index}@example.com", "phone_number": "+442080160509",
            }
            for index, passenger in enumerate(search["passengers"], start=1)
        ]
        order = client.create_test_order(offer["id"], offer["total_amount"], offer["total_currency"], people)["data"]
    except DuffelApiError as exc:
        raise _api_error(exc) from None
    except DuffelTransportError:
        raise DuffelServiceError(UNREACHABLE) from None
    return order["id"]
